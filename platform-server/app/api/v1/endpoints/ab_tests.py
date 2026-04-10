"""
AB测试API端点
统一支持 Expert 维度和 Agent/Job 维度
"""
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api.deps import get_db, get_current_user_id
from app.core.database import async_session_factory
from app.schemas.ab_test import (
    ABTestCreateExpert,
    ABTestCreateJob,
    ABTestUpdate,
    ABTestResponse,
    ABTestListResponse,
    ABTestDetailResponse,
    ABTestAnalyzeResponse,
    ABTestExecuteExpert,
    ABTestExecuteResponse,
    AddDebugHistoryRequest,
)
from app.schemas.base import ResponseData
from app.services.ab_test_service import ABTestService

router = APIRouter()


# ========== 执行模式（保留原有流程）==========

async def _execute_ab_test_background(test_id: str, data: ABTestExecuteExpert, username: Optional[str] = None):
    """
    后台异步执行AB测试
    """
    try:
        async with async_session_factory() as db:
            service = ABTestService(db)
            await service.execute_test(test_id, data, username=username)
            logger.info(f"[ABTest] 后台执行完成: {test_id}")
    except Exception as e:
        logger.error(f"[ABTest] 后台执行失败: {test_id}, 错误: {e}")


@router.post("/execute", response_model=ResponseData[ABTestExecuteResponse])
async def execute_ab_test(
    data: ABTestExecuteExpert,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    创建并执行 Expert AB 测试（保留原有流程）
    
    - 创建测试，debug_history_ids 初始为空
    - 后台执行测试，每完成一个 debug 就追加 debug_history_id
    - 全部执行完成后自动分析
    
    - **test_name**: 测试名称
    - **configs**: 配置组列表（至少2个）
    - **traffic_allocation**: 流量分配
    - **execution_count**: 执行次数
    - **auto_execute**: 是否自动执行（默认 true）
    """
    service = ABTestService(db)
    
    try:
        # 创建测试
        test = await service.create_and_execute_expert_test(data, created_by=current_user_id)
        
        # 如果需要自动执行
        if data.auto_execute:
            # 更新状态为 running
            ab_test = await service._get_test_by_id(test.test_id)
            if ab_test:
                ab_test.status = "running"
                await db.commit()
            
            # 后台执行
            asyncio.create_task(
                _execute_ab_test_background(test.test_id, data, username=current_user_id)
            )
            
            logger.info(f"[ABTest] 测试任务已启动: {test.test_id}")
            
            return ResponseData(data=ABTestExecuteResponse(
                test_id=test.test_id,
                status="running",
                message="测试任务已启动，正在后台执行",
                total_runs=data.execution_count,
                completed_runs=0,
            ))
        
        return ResponseData(data=ABTestExecuteResponse(
            test_id=test.test_id,
            status="pending",
            message="测试任务已创建",
            total_runs=data.execution_count,
            completed_runs=0,
        ))
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 创建测试（关联模式）==========

@router.post("/expert", response_model=ResponseData[ABTestResponse])
async def create_expert_test(
    data: ABTestCreateExpert,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    创建 Expert 维度 AB 测试
    
    关联已有的调试历史记录进行对比分析
    
    - **test_name**: 测试名称
    - **debug_history_ids**: 调试历史关联，key 为组名，value 为 debug_history_id 数组
    - **groups**: 对比组信息（至少2个组）
    """
    service = ABTestService(db)
    try:
        result = await service.create_expert_test(data, created_by=current_user_id)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/job", response_model=ResponseData[ABTestResponse])
async def create_job_test(
    data: ABTestCreateJob,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    创建 Job 维度 AB 测试
    
    关联多个 Job 进行对比分析
    
    - **test_name**: 测试名称
    - **job_ids**: Job 关联，key 为组名，value 为 job_id
    - **groups**: 对比组信息（至少2个组）
    """
    service = ABTestService(db)
    try:
        result = await service.create_job_test(data, created_by=current_user_id)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 添加关联 ==========

@router.post("/{test_id}/debug-histories", response_model=ResponseData[ABTestResponse])
async def add_debug_histories(
    test_id: str,
    data: AddDebugHistoryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    向 Expert 测试添加调试历史
    
    支持同一组多次执行的场景，可以追加新的调试历史
    """
    service = ABTestService(db)
    try:
        result = await service.add_debug_histories(test_id, data)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 分析测试 ==========

@router.post("/{test_id}/analyze", response_model=ResponseData[ABTestAnalyzeResponse])
async def analyze_test(
    test_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    分析测试
    
    聚合关联数据的指标，生成对比结论和推荐
    """
    service = ABTestService(db)
    try:
        result = await service.analyze_test(test_id)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ABTest] 分析失败: {test_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ========== 查询测试 ==========

@router.get("", response_model=ResponseData[ABTestListResponse])
async def list_ab_tests(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    test_type: Optional[str] = Query(None, description="测试类型: EXPERT_CONFIG, AGENT_JOB"),
    status: Optional[str] = Query(None, description="状态: pending, analyzing, completed, failed"),
    db: AsyncSession = Depends(get_db),
):
    """获取AB测试列表"""
    service = ABTestService(db)
    result = await service.list_tests(
        page=page,
        page_size=page_size,
        test_type=test_type,
        status=status,
    )
    return ResponseData(data=result)


@router.get("/{test_id}", response_model=ResponseData[ABTestDetailResponse])
async def get_ab_test_detail(
    test_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取AB测试详情（包含各组详细指标）"""
    service = ABTestService(db)
    detail = await service.get_test_detail(test_id)
    if not detail:
        raise HTTPException(status_code=404, detail="测试不存在")
    return ResponseData(data=detail)


# ========== 更新/删除测试 ==========

@router.put("/{test_id}", response_model=ResponseData[ABTestResponse])
async def update_ab_test(
    test_id: str,
    data: ABTestUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新AB测试"""
    service = ABTestService(db)
    result = await service.update_test(test_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="测试不存在")
    return ResponseData(data=result)


@router.delete("/{test_id}", response_model=ResponseData)
async def delete_ab_test(
    test_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除AB测试（软删除）"""
    service = ABTestService(db)
    success = await service.delete_test(test_id)
    if not success:
        raise HTTPException(status_code=404, detail="测试不存在")
    return ResponseData(message="删除成功")
