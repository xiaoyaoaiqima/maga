"""
文件上传 API
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.base import ResponseData
from app.services.cos_service import get_cos_service

router = APIRouter()

# 允许的图片类型
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
}

# 最大文件大小 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/upload/image", response_model=ResponseData[dict])
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
) -> ResponseData[dict]:
    """
    上传图片到 COS

    支持格式：jpg, png, gif, webp, bmp
    最大大小：10MB
    """
    # 验证文件类型
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片类型: {file.content_type}，支持: jpg, png, gif, webp, bmp",
        )

    # 读取文件内容
    file_data = await file.read()

    # 验证文件大小
    if len(file_data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB",
        )

    # 上传到 COS
    cos_service = get_cos_service()
    file_url = cos_service.upload_file(
        file_data=file_data,
        file_name=file.filename or "image.jpg",
        prefix="test-case/images",
    )

    if not file_url:
        raise HTTPException(status_code=500, detail="图片上传失败，请稍后重试")

    return ResponseData(
        data={
            "url": file_url,
            "filename": file.filename,
            "size": len(file_data),
            "content_type": file.content_type,
        }
    )


@router.post("/upload/images", response_model=ResponseData[dict])
async def upload_images(
    files: list[UploadFile] = File(..., description="图片文件列表"),
) -> ResponseData[dict]:
    """
    批量上传图片到 COS

    最多一次上传 20 张
    """
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="一次最多上传 20 张图片")

    cos_service = get_cos_service()
    results = []
    errors = []

    for i, file in enumerate(files):
        # 验证类型
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            errors.append({"index": i, "filename": file.filename, "error": "不支持的图片类型"})
            continue

        # 读取内容
        file_data = await file.read()

        # 验证大小
        if len(file_data) > MAX_FILE_SIZE:
            errors.append({"index": i, "filename": file.filename, "error": "文件过大"})
            continue

        # 上传
        file_url = cos_service.upload_file(
            file_data=file_data,
            file_name=file.filename or f"image_{i}.jpg",
            prefix="test-case/images",
        )

        if file_url:
            results.append({
                "index": i,
                "filename": file.filename,
                "url": file_url,
            })
        else:
            errors.append({"index": i, "filename": file.filename, "error": "上传失败"})

    return ResponseData(
        data={
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
        }
    )

