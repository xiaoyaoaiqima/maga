"""
知识库文件 API - 文件上传与管理

注意：KnowledgeBaseFile 表示单个上传文件，属于某个 KnowledgeBase
上传文件时需要指定 knowledge_base_id
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import ResponseData
from app.schemas.knowledge_base_file import (
    KnowledgeBaseFileBatchParseRequest,
    KnowledgeBaseFileItem,
    KnowledgeBaseFileUploadRequest,
    KnowledgeBaseFileUploadResponse,
)
from app.models.knowledge_base_file import KnowledgeBaseFile
from app.services.knowledge_base_service import KnowledgeBaseService as KBaseService
from app.services.excel_parser import ExcelParser
from app.services.knowledge_base_file_service import KnowledgeBaseFileService
from app.services.node_pending_audit_service import NodePendingAuditService
from app.services.cos_service import get_cos_service
from sqlalchemy import select

router = APIRouter(prefix="/knowledge-base-files", tags=["知识库文件"])
logger = logging.getLogger(__name__)

# 上传目录配置（本地存储回退方案）
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads/knowledge_base_files")

# 临时目录配置（用于 COS 文件下载后解析）
TEMP_DIR = Path(tempfile.gettempdir()) / "raap_knowledge_base_files"


async def _save_file_locally(file_content: bytes, filename: str) -> str:
    """将文件保存到本地存储"""
    upload_path = Path(UPLOAD_DIR) / "knowledge_base_files"
    upload_path.mkdir(parents=True, exist_ok=True)
    local_path = upload_path / filename
    with open(local_path, "wb") as f:
        f.write(file_content)
    file_path = str(local_path)
    logger.info(f"文件已保存到本地: {file_path}")
    return file_path


@router.get("", summary="获取知识库文件列表")
async def get_knowledge_base_files(
    db: AsyncSessionDep,
    knowledge_base_id: Optional[int] = Query(None, description="知识库ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
):
    """获取知识库文件列表"""
    service = KnowledgeBaseFileService(db)
    items = await service.get_list(
        knowledge_base_id=knowledge_base_id,
        status=status,
    )
    return ResponseData(data={"items": [item.model_dump() for item in items], "total": len(items)})


@router.get("/{file_id}", summary="获取文件详情")
async def get_knowledge_base_file(
    file_id: int,
    db: AsyncSessionDep,
):
    """获取单个文件详情"""
    service = KnowledgeBaseFileService(db)
    item = await service.get_by_id(file_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在")
    return ResponseData(data=item.model_dump())


@router.post("/upload", summary="上传文件")
async def upload_file(
    file: UploadFile,
    knowledge_base_id: int = Query(..., description="所属知识库ID"),
    db: AsyncSessionDep = None,
):
    """
    上传文件到指定知识库

    流程：
    1. 验证知识库是否存在
    2. 上传文件到 COS（如果配置）或本地
    3. 创建 KnowledgeBaseFile 记录
    4. 更新 KnowledgeBase 统计
    """
    # 验证知识库是否存在
    kbase_service = KBaseService(db)
    kbase = await kbase_service.get_by_id(knowledge_base_id)
    if not kbase:
        raise HTTPException(
            status_code=404,
            detail=f"知识库 {knowledge_base_id} 不存在",
        )

    # 验证文件类型
    from app.services.document_parser import DocumentParser

    file_ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if not DocumentParser.is_supported(file_ext):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file_ext}，支持 PDF、Word、PPT、Excel、CSV",
        )

    # 获取文档类型用于存储
    doc_type = DocumentParser.get_doc_type(file_ext)

    # 读取文件内容
    file_content = await file.read()
    file_size = len(file_content)

    # 尝试使用 COS 存储，失败则回退到本地存储
    cos_service = get_cos_service()
    file_path: str

    if cos_service.is_enabled():
        # 使用 COS 存储
        cos_url = cos_service.upload_file(
            file_data=file_content,
            file_name=file.filename,
            prefix="knowledge-base-files",
        )
        if cos_url:
            file_path = cos_url
            logger.info(f"文件已上传到 COS: {cos_url}")
        else:
            # COS 上传失败，回退到本地存储
            logger.warning("COS 上传失败，回退到本地存储")
            file_path = await _save_file_locally(file_content, file.filename)
    else:
        # COS 未配置，使用本地存储
        logger.info("COS 未配置，使用本地存储")
        file_path = await _save_file_locally(file_content, file.filename)

    # 创建 KnowledgeBaseFile 记录
    from app.schemas.knowledge_base_file import KnowledgeBaseFileCreate

    file_service = KnowledgeBaseFileService(db)
    knowledge_base_file = await file_service.create(
        KnowledgeBaseFileCreate(
            knowledge_base_id=knowledge_base_id,
            file_name=file.filename,
            file_path=file_path,
            file_size=file_size,
            file_type=doc_type,
        )
    )

    # 更新知识库文件计数
    await kbase_service.increment_file_count(knowledge_base_id)

    return ResponseData(
        data=KnowledgeBaseFileUploadResponse(
            file_id=knowledge_base_file.id,
            status="uploaded",
            message=f"文件上传成功",
        ).model_dump(),
        message=f"文件上传成功",
    )


@router.delete("/{file_id}", summary="删除文件")
async def delete_knowledge_base_file(
    file_id: int,
    db: AsyncSessionDep,
    delete_file: bool = Query(False, description="是否同时删除物理文件"),
):
    """删除知识库文件记录（软删除，可选删除物理文件）"""
    service = KnowledgeBaseFileService(db)
    knowledge_base_file = await service.get_by_id(file_id)
    if not knowledge_base_file:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在")

    # 如果需要删除物理文件，且文件存储在 COS
    if delete_file and knowledge_base_file.file_path.startswith(("http://", "https://")):
        cos_service = get_cos_service()
        if cos_service.is_enabled():
            cos_service.delete_file(knowledge_base_file.file_path)
            logger.info(f"COS 文件已删除: {knowledge_base_file.file_path}")

    success = await service.delete(file_id, delete_file=delete_file)
    if not success:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在")

    # 更新知识库文件计数
    kbase_service = KBaseService(db)
    await kbase_service.decrement_file_count(knowledge_base_file.knowledge_base_id)

    return ResponseData(message="文件删除成功")


@router.get("/{file_id}/download", summary="下载文件")
async def download_file(
    file_id: int,
    db: AsyncSessionDep,
):
    """下载知识库文件"""
    from fastapi.responses import FileResponse

    service = KnowledgeBaseFileService(db)
    knowledge_base_file = await service.get_by_id(file_id)
    if not knowledge_base_file:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在")

    file_path = knowledge_base_file.file_path

    # 如果是 COS URL，需要先下载到临时目录
    if file_path.startswith(("http://", "https://")):
        cos_service = get_cos_service()
        # 创建临时目录
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"raap_download_{file_id}_{knowledge_base_file.file_name}")

        # 下载文件
        success = await cos_service.download_file(file_path, temp_file_path)
        if not success:
            raise HTTPException(status_code=500, detail="文件下载失败")

        # 返回文件并在发送后删除
        def cleanup():
            try:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
            except Exception:
                pass

        return FileResponse(
            path=temp_file_path,
            filename=knowledge_base_file.file_name,
            media_type='application/octet-stream',
            background=cleanup,
        )

    # 本地文件直接返回
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="物理文件不存在")

    return FileResponse(
        path=file_path,
        filename=knowledge_base_file.file_name,
        media_type='application/octet-stream',
    )


@router.get("/{file_id}/audits", summary="获取文件的待审核记录")
async def get_file_audits(
    file_id: int,
    db: AsyncSessionDep,
):
    """获取文件下的所有待审核记录"""
    service = NodePendingAuditService(db)
    summary = await service.get_audit_summary(file_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在或无待审核记录")
    return ResponseData(data=summary)


@router.post("/{file_id}/parse", summary="解析文件")
async def parse_file(
    file_id: int,
    db: AsyncSessionDep,
):
    """
    解析文件，提取文本内容

    支持 PDF、Word、PPT、Excel、CSV 等格式
    """
    from app.services.document_parser import DocumentParser, parse_knowledge_base_file
    from app.services.knowledge_base_file_service import KnowledgeBaseFileService

    file_service = KnowledgeBaseFileService(db)
    file_item = await file_service.get_by_id(file_id)
    if not file_item:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在")

    # 更新状态为解析中
    await file_service.update_status(file_id, status="parsing")

    # 获取文件记录
    stmt = select(KnowledgeBaseFile).where(KnowledgeBaseFile.id == file_id)
    result = await db.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail=f"文件 {file_id} 不存在")

    # 解析文件
    parse_result = await parse_knowledge_base_file(file, db)

    return ResponseData(
        data={
            "file_id": file_id,
            "parsed_count": parse_result.get("text_length", 0),
            "status": "success" if parse_result.get("success") else "failed",
        },
        message="解析成功" if parse_result.get("success") else parse_result.get("error"),
    )


@router.post("/parse/batch", summary="批量解析文件")
async def parse_files_batch(
    request_data: KnowledgeBaseFileBatchParseRequest,
    db: AsyncSessionDep = None,
):
    """
    批量解析多个文件

    支持 PDF、Word、PPT、Excel、CSV 等格式

    请求体: {"document_ids": [1, 2, 3]} 或 {"file_ids": [1, 2, 3]}
    """
    # 兼容前端发送的 document_ids 和后端原本的 file_ids
    file_ids = request_data.document_ids or request_data.file_ids or []
    if not file_ids:
        raise HTTPException(status_code=400, detail="缺少 file_ids 或 document_ids 参数")
    from app.services.document_parser import parse_knowledge_base_file
    from app.services.knowledge_base_file_service import KnowledgeBaseFileService

    file_service = KnowledgeBaseFileService(db)
    results = []
    success_count = 0
    failed_count = 0

    for file_id in file_ids:
        file_item = await file_service.get_by_id(file_id)
        if not file_item:
            results.append({
                "file_id": file_id,
                "status": "failed",
                "error": "文件不存在",
            })
            failed_count += 1
            continue

        # 更新状态为解析中
        await file_service.update_status(file_id, status="parsing")

        # 获取文件记录
        stmt = select(KnowledgeBaseFile).where(KnowledgeBaseFile.id == file_id)
        result = await db.execute(stmt)
        file = result.scalar_one_or_none()
        if not file:
            results.append({
                "file_id": file_id,
                "status": "failed",
                "error": "文件不存在",
            })
            failed_count += 1
            continue

        # 解析文件
        parse_result = await parse_knowledge_base_file(file, db)

        if parse_result.get("success"):
            results.append({
                "file_id": file_id,
                "status": "success",
                "parsed_count": parse_result.get("text_length", 0),
            })
            success_count += 1
        else:
            results.append({
                "file_id": file_id,
                "status": "failed",
                "error": parse_result.get("error"),
            })
            failed_count += 1

    # 前端期望 {success, failed} 格式
    return ResponseData(
        data={
            "success": success_count,
            "failed": failed_count,
        },
        message=f"批量解析完成: 成功 {success_count}, 失败 {failed_count}",
    )
