"""
LLM Provider 管理 API

包含：
- LLM Provider 配置 CRUD
- 模型路由管理
- 熔断状态查看
- 连接测试
"""
from typing import Optional
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.services.llm_provider_service import (
    LLMProviderService,
    LLMModelRouteService,
    LLMCircuitBreakerService,
)
from app.schemas.llm_provider import (
    LLMProviderConfigCreate,
    LLMProviderConfigUpdate,
    LLMProviderConfigResponse,
    LLMProviderConfigDetail,
    LLMProviderConfigList,
    LLMModelRouteCreate,
    LLMModelRouteUpdate,
    LLMModelRouteResponse,
    LLMModelRouteList,
    LLMCircuitBreakerResponse,
    LLMCircuitBreakerList,
    AvailableModel,
    AvailableModelList,
    ConnectionTestRequest,
    ConnectionTestResponse,
    RemoteModelInfo,
    RemoteModelList,
    SyncModelsRequest,
    SyncModelsResponse,
    FetchRemoteModelsRequest,
    mask_api_key,
)
from app.schemas.base import ResponseData
from app.services.remote_model_service import remote_model_service
from app.constants.model_pricing import get_model_price_reference

# 两个路由器：static_router 必须先注册（在 router.py 中）
static_router = APIRouter()  # 用于 /routes, /models 等静态路由
router = APIRouter()  # 用于 /{code} 等动态路由


# ==================== LLM Provider 配置 API ====================

@router.get("", response_model=ResponseData)
async def list_providers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled: Optional[bool] = Query(None, description="筛选启用状态"),
    provider_type: Optional[str] = Query(None, description="筛选提供商类型"),
    db: AsyncSession = Depends(get_db),
):
    """获取 LLM Provider 列表"""
    service = LLMProviderService(db)
    items, total = await service.list(
        skip=skip,
        limit=limit,
        enabled=enabled,
        provider_type=provider_type,
    )
    
    # 转换为响应格式（API Key 脱敏）
    response_items = [
        LLMProviderConfigResponse(
            id=item.id,
            provider_code=item.provider_code,
            provider_name=item.provider_name,
            provider_type=item.provider_type,
            base_url=item.base_url,
            api_key_masked=mask_api_key(item.api_key or ""),
            default_model=item.default_model,
            available_models=item.available_models,
            default_params=item.default_params,
            rate_limit=item.rate_limit,
            timeout=item.timeout,
            priority=item.priority,
            enabled=item.enabled == 1,
            description=item.description,
            create_time=item.create_time,
            update_time=item.update_time,
        )
        for item in items
    ]
    
    return ResponseData(
        data=LLMProviderConfigList(items=response_items, total=total).model_dump()
    )


@router.post("", response_model=ResponseData)
async def create_provider(
    data: LLMProviderConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建 LLM Provider"""
    service = LLMProviderService(db)
    
    try:
        provider = await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return ResponseData(
        data=LLMProviderConfigResponse(
            id=provider.id,
            provider_code=provider.provider_code,
            provider_name=provider.provider_name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            api_key_masked=mask_api_key(provider.api_key or ""),
            default_model=provider.default_model,
            available_models=provider.available_models,
            default_params=provider.default_params,
            rate_limit=provider.rate_limit,
            timeout=provider.timeout,
            priority=provider.priority,
            enabled=provider.enabled == 1,
            description=provider.description,
            create_time=provider.create_time,
            update_time=provider.update_time,
        ).model_dump(),
        message="LLM Provider 创建成功"
    )


@router.get("/{code}", response_model=ResponseData)
async def get_provider(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """获取 LLM Provider 详情"""
    service = LLMProviderService(db)
    provider = await service.get_by_code(code)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    return ResponseData(
        data=LLMProviderConfigResponse(
            id=provider.id,
            provider_code=provider.provider_code,
            provider_name=provider.provider_name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            api_key_masked=mask_api_key(provider.api_key or ""),
            default_model=provider.default_model,
            available_models=provider.available_models,
            default_params=provider.default_params,
            rate_limit=provider.rate_limit,
            timeout=provider.timeout,
            priority=provider.priority,
            enabled=provider.enabled == 1,
            description=provider.description,
            create_time=provider.create_time,
            update_time=provider.update_time,
        ).model_dump()
    )

@router.get("/{code}/internal-config", response_model=ResponseData)
async def get_provider_internal_config(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    service = LLMProviderService(db)
    config = await service.get_with_decrypted_key(code)
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    provider = await service.get_by_code(code)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    return ResponseData(
        data=LLMProviderConfigDetail(
            id=provider.id,
            provider_code=config["provider_code"],
            provider_name=config["provider_name"],
            provider_type=config["provider_type"],
            base_url=config["base_url"],
            api_key_masked=mask_api_key(provider.api_key or ""),
            api_key=config.get("api_key") or "",
            default_model=config.get("default_model"),
            available_models=config.get("available_models"),
            default_params=config.get("default_params"),
            rate_limit=provider.rate_limit,
            timeout=config.get("timeout"),
            priority=config.get("priority"),
            enabled=provider.enabled == 1,
            description=provider.description,
            create_time=provider.create_time,
            update_time=provider.update_time,
        ).model_dump()
    )


@router.put("/{code}", response_model=ResponseData)
async def update_provider(
    code: str,
    data: LLMProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新 LLM Provider"""
    service = LLMProviderService(db)
    provider = await service.update(code, data)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    return ResponseData(
        data=LLMProviderConfigResponse(
            id=provider.id,
            provider_code=provider.provider_code,
            provider_name=provider.provider_name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            api_key_masked=mask_api_key(provider.api_key or ""),
            default_model=provider.default_model,
            available_models=provider.available_models,
            default_params=provider.default_params,
            rate_limit=provider.rate_limit,
            timeout=provider.timeout,
            priority=provider.priority,
            enabled=provider.enabled == 1,
            description=provider.description,
            create_time=provider.create_time,
            update_time=provider.update_time,
        ).model_dump(),
        message="LLM Provider 更新成功"
    )


@router.delete("/{code}", response_model=ResponseData)
async def delete_provider(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """删除 LLM Provider"""
    service = LLMProviderService(db)
    success = await service.delete(code)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    return ResponseData(message="LLM Provider 删除成功")


@router.post("/{code}/enable", response_model=ResponseData)
async def enable_provider(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """启用 LLM Provider"""
    service = LLMProviderService(db)
    provider = await service.toggle_enabled(code, True)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    return ResponseData(message=f"Provider '{code}' 已启用")


@router.post("/{code}/disable", response_model=ResponseData)
async def disable_provider(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """禁用 LLM Provider"""
    service = LLMProviderService(db)
    provider = await service.toggle_enabled(code, False)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    return ResponseData(message=f"Provider '{code}' 已禁用")


@router.post("/{code}/test", response_model=ResponseData)
async def test_connection(
    code: str,
    request: ConnectionTestRequest = ConnectionTestRequest(),
    db: AsyncSession = Depends(get_db),
):
    """测试 LLM Provider 连接
    
    测试流程：
    1. 先尝试使用配置的 default_model
    2. 如果失败且是模型权限问题，自动获取可用模型列表并重试
    3. 返回测试结果
    """
    import time
    import httpx
    
    service = LLMProviderService(db)
    config = await service.get_with_decrypted_key(code)
    
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    # 确定要测试的模型
    test_model = config.get("default_model") or "deepseek-v4-flash"
    base_url = config['base_url']
    api_key = config['api_key']
    
    async def _test_with_model(model_id: str) -> tuple[bool, int, Optional[str], Optional[str], bool]:
        """使用指定模型进行测试，返回 (success, latency_ms, response_preview, error_message, is_model_error)"""
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": request.test_prompt}],
                        "max_tokens": 50,
                    }
                )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return True, latency_ms, content[:100] if content else None, None, False
            else:
                error_text = response.text[:200]
                # 检查是否是模型权限问题
                is_model_error = (
                    response.status_code == 400 and (
                        "model" in error_text.lower() or 
                        "permission" in error_text.lower() or
                        "incorrect model" in error_text.lower()
                    )
                )
                return False, latency_ms, None, f"HTTP {response.status_code}: {error_text}", is_model_error
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return False, latency_ms, None, str(e), False
    
    # 第一次尝试：使用 default_model
    success, latency_ms, response_preview, error_message, is_model_error = await _test_with_model(test_model)
    
    # 如果失败且是模型权限问题，尝试获取可用模型列表并重试
    if not success and is_model_error:
        try:
            # 获取可用模型列表
            models = await remote_model_service.get_models(
                base_url=base_url,
                api_key=api_key,
                provider_type=config.get("provider_type", "openai_compatible"),
                model_type_filter="llm",
            )
            
            if models:
                # 尝试使用第一个可用模型
                fallback_model = models[0].model_id
                success, latency_ms, response_preview, error_message, _ = await _test_with_model(fallback_model)
                
                if success:
                    # 如果备用模型测试成功，在错误信息中提示
                    error_message = None  # 清除错误信息
                    response_preview = (response_preview or "") + f" (使用模型: {fallback_model}, 原配置模型 {test_model} 不可用)"
        except Exception as e:
            # 获取模型列表失败，使用原始错误信息
            pass
    
    return ResponseData(
        data=ConnectionTestResponse(
            success=success,
            latency_ms=latency_ms,
            response_preview=response_preview,
            error_message=error_message,
        ).model_dump()
    )


@router.get("/{code}/remote-models", response_model=ResponseData)
async def get_remote_models(
    code: str,
    model_type: Optional[str] = Query("llm", description="模型类型过滤（llm/image_generation/embedding 等）"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取 Provider 的远程可用模型列表
    
    从 Provider 的 API 获取所有可用模型，支持：
    - AiHubMix: 自动调用 https://aihubmix.com/api/v1/models
    - OpenAI 兼容: 调用 /v1/models 端点
    """
    service = LLMProviderService(db)
    route_service = LLMModelRouteService(db)
    config = await service.get_with_decrypted_key(code)
    
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    # 如果是阿里云，获取官网最新的价格映射表用于显示
    aliyun_pricing_map = {}
    if code == "aliyun":
        aliyun_pricing_map = await route_service.get_aliyun_pricing_map()
    
    try:
        models = await remote_model_service.get_models(
            base_url=config["base_url"],
            api_key=config.get("api_key"),
            provider_type=config.get("provider_type", "openai_compatible"),
            model_type_filter=model_type,
        )
        
        model_list = []
        for m in models:
            input_cost = float(m.cost_per_1k_input) if m.cost_per_1k_input else None
            output_cost = float(m.cost_per_1k_output) if m.cost_per_1k_output else None
            currency = "USD"

            if code == "aliyun":
                currency = "CNY"
                # 尝试匹配官网抓取的价格
                p_info = aliyun_pricing_map.get(m.model_id)
                if not p_info:
                    # 尝试去掉日期后缀进行模糊匹配
                    clean_id = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", m.model_id)
                    p_info = aliyun_pricing_map.get(clean_id)
                
                if p_info:
                    input_cost, output_cost = float(p_info[0]), float(p_info[1])
            
            # 如果依然没价格，尝试查静态价格库
            if input_cost is None or output_cost is None:
                suggested_price = get_model_price_reference(m.model_id)
                if suggested_price:
                    if input_cost is None:
                        input_cost = float(suggested_price["input"])
                    if output_cost is None:
                        output_cost = float(suggested_price["output"])

            model_list.append(
                RemoteModelInfo(
                    model_id=m.model_id,
                    model_name=m.model_name,
                    description=m.description,
                    model_type=m.model_type,
                    features=m.features,
                    input_modalities=m.input_modalities,
                    max_output=m.max_output,
                    context_length=m.context_length,
                    cost_per_1k_input=input_cost,
                    cost_per_1k_output=output_cost,
                    currency=currency,
                ).model_dump()
            )
        
        return ResponseData(
            data=RemoteModelList(
                items=model_list,
                total=len(model_list),
                provider_code=code,
            ).model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取远程模型失败: {str(e)}")


@router.post("/fetch-remote-models", response_model=ResponseData)
async def fetch_remote_models(
    request: FetchRemoteModelsRequest,
):
    """
    获取远程模型列表（用于新增 Provider 时测试）
    
    直接使用 base_url 和 api_key 获取模型列表，无需创建 Provider
    支持：
    - AiHubMix: 自动调用 https://aihubmix.com/api/v1/models
    - OpenAI 兼容: 调用 /v1/models 端点
    """
    from app.core.logger import logger
    
    logger.info(
        f"开始获取远程模型列表: base_url={request.base_url[:50]}..., "
        f"provider_type={request.provider_type}, model_type={request.model_type}"
    )
    
    try:
        models = await remote_model_service.get_models(
            base_url=request.base_url,
            api_key=request.api_key,
            provider_type=request.provider_type,
            model_type_filter=request.model_type,
        )
        
        logger.info(f"成功获取到 {len(models)} 个远程模型")

        # 如果是阿里云地址，尝试获取价格
        aliyun_pricing_map = {}
        is_aliyun = "dashscope.aliyuncs.com" in request.base_url.lower()
        if is_aliyun:
            from app.core.database import async_session_factory
            async with async_session_factory() as db:
                service = LLMModelRouteService(db)
                aliyun_pricing_map = await service.get_aliyun_pricing_map()
        
        model_list = []
        for m in models:
            input_cost = float(m.cost_per_1k_input) if m.cost_per_1k_input else None
            output_cost = float(m.cost_per_1k_output) if m.cost_per_1k_output else None
            currency = "USD"

            if is_aliyun:
                currency = "CNY"
                p_info = aliyun_pricing_map.get(m.model_id)
                if not p_info:
                    clean_id = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", m.model_id)
                    p_info = aliyun_pricing_map.get(clean_id)
                if p_info:
                    input_cost, output_cost = float(p_info[0]), float(p_info[1])

            if input_cost is None or output_cost is None:
                suggested_price = get_model_price_reference(m.model_id)
                if suggested_price:
                    if input_cost is None:
                        input_cost = float(suggested_price["input"])
                    if output_cost is None:
                        output_cost = float(suggested_price["output"])

            model_list.append(
                RemoteModelInfo(
                    model_id=m.model_id,
                    model_name=m.model_name,
                    description=m.description,
                    model_type=m.model_type,
                    features=m.features,
                    input_modalities=m.input_modalities,
                    max_output=m.max_output,
                    context_length=m.context_length,
                    cost_per_1k_input=input_cost,
                    cost_per_1k_output=output_cost,
                    currency=currency,
                ).model_dump()
            )
        
        return ResponseData(
            data=RemoteModelList(
                items=model_list,
                total=len(model_list),
                provider_code="",  # 新增模式下没有 provider_code
            ).model_dump()
        )
    except ValueError as e:
        logger.error(f"获取远程模型失败（参数错误）: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取远程模型失败（服务器错误）: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取远程模型失败: {str(e)}")


@router.post("/{code}/sync-models", response_model=ResponseData)
async def sync_models(
    code: str,
    request: SyncModelsRequest = SyncModelsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    同步远程模型到本地路由表
    
    从 Provider API 获取模型列表，并自动创建对应的模型路由配置。
    """
    from decimal import Decimal
    
    provider_service = LLMProviderService(db)
    route_service = LLMModelRouteService(db)
    
    config = await provider_service.get_with_decrypted_key(code)
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")
    
    # 如果是阿里云，先尝试获取官网最新的价格映射表
    aliyun_pricing_map = {}
    if code == "aliyun":
        aliyun_pricing_map = await route_service.get_aliyun_pricing_map()
    
    try:
        # 获取远程模型列表
        models = await remote_model_service.get_models(
            base_url=config["base_url"],
            api_key=config.get("api_key"),
            provider_type=config.get("provider_type", "openai_compatible"),
            model_type_filter="llm",  # 只同步 LLM 类型
        )
        
        # 过滤指定的模型
        if request.model_ids:
            models = [m for m in models if m.model_id in request.model_ids]
        
        synced_count = 0
        skipped_count = 0
        failed_count = 0
        details = []
        
        for model in models:
            try:
                # 检查是否已存在
                existing_routes, _ = await route_service.list(
                    model_code=model.model_id,
                    provider_code=code,
                    limit=1,
                )
                
                # 确定建议价格和特性
                input_cost = Decimal(str(model.cost_per_1k_input)) if model.cost_per_1k_input else None
                output_cost = Decimal(str(model.cost_per_1k_output)) if model.cost_per_1k_output else None
                currency = "USD"

                # 阿里云特有逻辑：优先使用抓取到的官网价格
                if code == "aliyun":
                    currency = "CNY"
                    # 尝试在 pricing_map 中寻找最匹配的价格
                    # 匹配顺序: 
                    # 1. 精确 ID (qwen-max-2025-01-25)
                    # 2. 移除日期后缀 (qwen-max)
                    # 3. 移除 Batch/latest 后缀 (qwen-max-latestBatch -> qwen-max)
                    # 4. 前缀匹配
                    p_info = aliyun_pricing_map.get(model.model_id)
                    
                    if not p_info:
                        # 尝试去掉日期后缀
                        clean_id = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model.model_id)
                        p_info = aliyun_pricing_map.get(clean_id)
                    
                    if not p_info:
                        # 尝试去掉常见的修饰后缀
                        clean_id = re.sub(r"(Batch|latest|preview)$", "", model.model_id, flags=re.IGNORECASE).strip("-")
                        p_info = aliyun_pricing_map.get(clean_id)

                    if not p_info:
                        # 最后尝试前缀搜索（取最长匹配）
                        matched_keys = [k for k in aliyun_pricing_map.keys() if model.model_id.startswith(k)]
                        if matched_keys:
                            best_key = max(matched_keys, key=len)
                            p_info = aliyun_pricing_map.get(best_key)
                    
                    if p_info:
                        input_cost, output_cost = p_info

                # 如果还没价格，则使用参考价库
                if input_cost is None or output_cost is None:
                    suggested_price = get_model_price_reference(model.model_id)
                    if suggested_price:
                        if input_cost is None:
                            input_cost = suggested_price["input"]
                        if output_cost is None:
                            output_cost = suggested_price["output"]
                        
                        # 阿里云模型强制使用 CNY
                        # 如果使用的是参考价库（USD），则按参考库汇率 (1 CNY ≈ 0.138 USD) 换算回 CNY
                        if code == "aliyun":
                            currency = "CNY"
                            if input_cost is not None:
                                input_cost = (input_cost / Decimal("0.138")).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
                            if output_cost is not None:
                                output_cost = (output_cost / Decimal("0.138")).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)

                # 解析 features 为 dict 格式
                features_dict = {}
                for f in model.features:
                    if f in ["thinking", "tools", "function_calling", "web", "structured_outputs"]:
                        features_dict[f] = True
                    if f == "tools" or f == "function_calling":
                        features_dict["function_calling"] = True
                    if "image" in model.input_modalities:
                        features_dict["vision"] = True

                if existing_routes:
                    # ✅ 逻辑纠正：如果已存在，则自动执行更新（Upsert 模式）
                    await route_service.update(
                        existing_routes[0].id,
                        LLMModelRouteUpdate(
                            model_name=model.model_name,
                            max_context_length=model.context_length,
                            features=features_dict if features_dict else None,
                            cost_per_1k_input=input_cost,
                            cost_per_1k_output=output_cost,
                            currency=currency,
                            description=model.description,
                        )
                    )
                    synced_count += 1
                    details.append({
                        "model_id": model.model_id,
                        "status": "updated",
                    })
                else:
                    # 创建新路由
                    route_data = LLMModelRouteCreate(
                        model_code=model.model_id,
                        model_name=model.model_name,
                        provider_code=code,
                        provider_model=model.model_id,
                        priority=50,
                        enabled=True,
                        max_context_length=model.context_length,
                        features=features_dict if features_dict else None,
                        cost_per_1k_input=input_cost,
                        cost_per_1k_output=output_cost,
                        currency=currency,
                        description=model.description,
                    )
                    await route_service.create(route_data)
                    synced_count += 1
                    details.append({
                        "model_id": model.model_id,
                        "status": "created",
                    })
                    
            except Exception as e:
                failed_count += 1
                details.append({
                    "model_id": model.model_id,
                    "status": "failed",
                    "reason": str(e)
                })
        
        return ResponseData(
            data=SyncModelsResponse(
                synced_count=synced_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                details=details,
            ).model_dump(),
            message=f"同步完成：成功 {synced_count}，跳过 {skipped_count}，失败 {failed_count}"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步模型失败: {str(e)}")


@router.post("/{code}/sync-configured-models", response_model=ResponseData)
async def sync_configured_models(
    code: str,
    request: SyncModelsRequest = SyncModelsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    从 Provider 已配置的 default_model / available_models 生成本地模型路由。

    这条路径不访问远程模型接口，适合运营或管理员已经手动维护好可用模型清单后，
    一键让 Expert 的模型下拉能够选到这些模型。
    """
    provider_service = LLMProviderService(db)
    route_service = LLMModelRouteService(db)

    provider = await provider_service.get_by_code(code)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{code}' not found")

    result = await route_service.sync_configured_models(
        provider=provider,
        model_ids=request.model_ids,
        overwrite=request.overwrite,
    )

    return ResponseData(
        data=SyncModelsResponse(**result).model_dump(),
        message=(
            f"生成完成：成功 {result['synced_count']}，"
            f"跳过 {result['skipped_count']}，失败 {result['failed_count']}"
        ),
    )


# ==================== 模型路由 API ====================

@static_router.get("/routes", response_model=ResponseData)
async def list_routes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    model_code: Optional[str] = Query(None, description="筛选模型编码"),
    provider_code: Optional[str] = Query(None, description="筛选提供商编码"),
    enabled: Optional[bool] = Query(None, description="筛选启用状态"),
    db: AsyncSession = Depends(get_db),
):
    """获取模型路由列表"""
    service = LLMModelRouteService(db)
    items, total = await service.list(
        skip=skip,
        limit=limit,
        model_code=model_code,
        provider_code=provider_code,
        enabled=enabled,
    )
    
    response_items = [
        LLMModelRouteResponse(
            id=item.id,
            model_code=item.model_code,
            model_name=item.model_name,
            provider_code=item.provider_code,
            provider_model=item.provider_model,
            priority=item.priority,
            enabled=item.enabled == 1,
            max_context_length=item.max_context_length,
            features=item.features,
            cost_per_1k_input=item.cost_per_1k_input,
            cost_per_1k_output=item.cost_per_1k_output,
            currency=item.currency,
            timeout_seconds=item.timeout_seconds,
            description=item.description,
            create_time=item.create_time,
            update_time=item.update_time,
        )
        for item in items
    ]
    
    return ResponseData(
        data=LLMModelRouteList(items=response_items, total=total).model_dump()
    )


@static_router.post("/routes", response_model=ResponseData)
async def create_route(
    data: LLMModelRouteCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建模型路由"""
    service = LLMModelRouteService(db)
    
    try:
        route = await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return ResponseData(
        data=LLMModelRouteResponse(
            id=route.id,
            model_code=route.model_code,
            model_name=route.model_name,
            provider_code=route.provider_code,
            provider_model=route.provider_model,
            priority=route.priority,
            enabled=route.enabled == 1,
            max_context_length=route.max_context_length,
            features=route.features,
            cost_per_1k_input=route.cost_per_1k_input,
            cost_per_1k_output=route.cost_per_1k_output,
            currency=route.currency,
            timeout_seconds=route.timeout_seconds,
            description=route.description,
            create_time=route.create_time,
            update_time=route.update_time,
        ).model_dump(),
        message="模型路由创建成功"
    )


@static_router.post("/routes/sync/aliyun", response_model=ResponseData)
async def sync_aliyun_model_prices(
    db: AsyncSession = Depends(get_db),
):
    """从阿里云百炼自动同步模型价格"""
    service = LLMModelRouteService(db)
    result = await service.sync_aliyun_prices()
    
    if not result.get("success", False):
        return ResponseData(message=f"同步失败: {result.get('message')}", data=result)
    
    return ResponseData(
        message=f"阿里云价格同步成功，更新了 {result.get('total_updated')} 条记录",
        data=result
    )


@static_router.put("/routes/{route_id}", response_model=ResponseData)
async def update_route(
    route_id: int,
    data: LLMModelRouteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新模型路由"""
    service = LLMModelRouteService(db)
    route = await service.update(route_id, data)
    
    if not route:
        raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
    
    return ResponseData(
        data=LLMModelRouteResponse(
            id=route.id,
            model_code=route.model_code,
            model_name=route.model_name,
            provider_code=route.provider_code,
            provider_model=route.provider_model,
            priority=route.priority,
            enabled=route.enabled == 1,
            max_context_length=route.max_context_length,
            features=route.features,
            cost_per_1k_input=route.cost_per_1k_input,
            cost_per_1k_output=route.cost_per_1k_output,
            currency=route.currency,
            timeout_seconds=route.timeout_seconds,
            description=route.description,
            create_time=route.create_time,
            update_time=route.update_time,
        ).model_dump(),
        message="模型路由更新成功"
    )


@static_router.delete("/routes/{route_id}", response_model=ResponseData)
async def delete_route(
    route_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除模型路由"""
    service = LLMModelRouteService(db)
    success = await service.delete(route_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
    
    return ResponseData(message="模型路由删除成功")


@static_router.get("/models", response_model=ResponseData)
async def list_available_models(
    db: AsyncSession = Depends(get_db),
):
    """获取所有可用模型（聚合视图）"""
    service = LLMModelRouteService(db)
    models = await service.list_available_models()
    
    return ResponseData(
        data=AvailableModelList(
            items=[AvailableModel(**m) for m in models],
            total=len(models)
        ).model_dump()
    )


# ==================== 熔断状态 API ====================

@static_router.get("/circuit-breakers", response_model=ResponseData)
async def list_circuit_breakers(
    db: AsyncSession = Depends(get_db),
):
    """获取所有熔断状态"""
    service = LLMCircuitBreakerService(db)
    items = await service.list_all()
    
    response_items = [
        LLMCircuitBreakerResponse(
            id=item.id,
            provider_code=item.provider_code,
            state=item.state,
            failure_count=item.failure_count,
            success_count=item.success_count,
            last_failure_time=item.last_failure_time,
            last_failure_reason=item.last_failure_reason,
            open_until=item.open_until,
            update_time=item.update_time,
        )
        for item in items
    ]
    
    return ResponseData(
        data=LLMCircuitBreakerList(items=response_items).model_dump()
    )


class CircuitBreakerReportRequest(BaseModel):
    provider_code: str = Field(..., max_length=64)
    state: str = Field(..., pattern="^(closed|open|half_open)$")
    failure_count: int = 0
    last_failure_reason: str | None = None

@static_router.post("/circuit-breakers/report", response_model=ResponseData)
async def report_circuit_breaker_state(
    data: CircuitBreakerReportRequest,
    db: AsyncSession = Depends(get_db),
):
    service = LLMCircuitBreakerService(db)
    await service.update_state(
        provider_code=data.provider_code,
        state=data.state,
        failure_count=int(data.failure_count or 0),
        last_failure_reason=data.last_failure_reason,
    )
    return ResponseData(message="熔断状态已上报")

@static_router.post("/circuit-breakers/{code}/reset", response_model=ResponseData)
async def reset_circuit_breaker(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """重置熔断状态（手动恢复）"""
    service = LLMCircuitBreakerService(db)
    success = await service.reset(code)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Circuit breaker for '{code}' not found")
    
    return ResponseData(message=f"熔断状态已重置: {code}")


@static_router.post("/circuit-breakers/{code}/force-open", response_model=ResponseData)
async def force_open_circuit_breaker(
    code: str,
    reason: str = Query("Manual intervention", description="熔断原因"),
    db: AsyncSession = Depends(get_db),
):
    """强制熔断（手动禁用）"""
    service = LLMCircuitBreakerService(db)
    await service.force_open(code, reason)
    
    return ResponseData(message=f"已强制熔断: {code}")


# ==================== 统计 API ====================

@static_router.get("/stats/provider", response_model=ResponseData)
async def get_provider_stats(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """获取 Provider 维度统计（从 ExpertCallTrace 原始表查询）"""
    from datetime import datetime, timedelta
    from sqlalchemy import select, func
    from app.models.expert_call_trace import ExpertCallTrace
    from app.models.llm_model_route import LLMModelRoute

    # 默认最近 7 天
    if not end_date:
        end_dt = datetime.now().date()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    if not start_date:
        start_dt = end_dt - timedelta(days=7)
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()

    # 从 ExpertCallTrace 原始表查询并关联 LLMModelRoute 获取币种
    start_datetime = datetime.combine(start_dt, datetime.min.time())
    end_datetime = datetime.combine(end_dt, datetime.max.time())

    result = await db.execute(
        select(
            ExpertCallTrace.provider_code,
            func.coalesce(LLMModelRoute.currency, ExpertCallTrace.currency, "USD").label("currency"),
            func.count().label("total_calls"),
            func.sum(ExpertCallTrace.total_tokens).label("total_tokens"),
            func.sum(ExpertCallTrace.total_cost).label("total_cost"),
            func.sum(ExpertCallTrace.duration_ms).label("total_duration_ms"),
            func.sum(func.if_(ExpertCallTrace.status == "success", 1, 0)).label("success_count"),
            func.sum(func.if_(ExpertCallTrace.status != "success", 1, 0)).label("fail_count"),
        )
        .outerjoin(
            LLMModelRoute,
            LLMModelRoute.provider_code == ExpertCallTrace.provider_code,
        )
        .where(
            ExpertCallTrace.start_time >= start_datetime,
            ExpertCallTrace.start_time <= end_datetime,
            ExpertCallTrace.provider_code.isnot(None),
        )
        .group_by(
            ExpertCallTrace.provider_code,
            LLMModelRoute.currency,
            ExpertCallTrace.currency,
        )
    )

    stats = []
    for row in result.all():
        total = int(row.total_calls or 0)
        success_rate = int(row.success_count or 0) / total if total > 0 else 1.0
        avg_latency = float(row.total_duration_ms or 0) / total if total > 0 else 0.0

        stats.append({
            "provider_code": row.provider_code,
            "currency": row.currency,
            "total_calls": total,
            "total_tokens": int(row.total_tokens or 0),
            "total_cost": float(row.total_cost or 0),
            "avg_latency_ms": avg_latency,
            "success_rate": success_rate,
        })

    return ResponseData(data=stats)


@static_router.get("/stats/model", response_model=ResponseData)
async def get_model_stats(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """获取模型维度统计（从 ExpertCallTrace 原始表查询）"""
    from datetime import datetime, timedelta
    from sqlalchemy import select, func
    from app.models.expert_call_trace import ExpertCallTrace
    from app.models.llm_model_route import LLMModelRoute

    # 默认最近 7 天
    if not end_date:
        end_dt = datetime.now().date()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    if not start_date:
        start_dt = end_dt - timedelta(days=7)
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()

    # 从 ExpertCallTrace 原始表查询并关联 LLMModelRoute 获取币种
    start_datetime = datetime.combine(start_dt, datetime.min.time())
    end_datetime = datetime.combine(end_dt, datetime.max.time())

    result = await db.execute(
        select(
            func.coalesce(ExpertCallTrace.model_code, "deepseek-v4-flash").label("model_code"),
            func.coalesce(LLMModelRoute.currency, ExpertCallTrace.currency, "USD").label("currency"),
            func.count().label("total_calls"),
            func.sum(ExpertCallTrace.total_tokens).label("total_tokens"),
            func.sum(ExpertCallTrace.total_cost).label("total_cost"),
            func.sum(ExpertCallTrace.duration_ms).label("total_duration_ms"),
        )
        .outerjoin(
            LLMModelRoute,
            LLMModelRoute.model_code == ExpertCallTrace.model_code,
        )
        .where(
            ExpertCallTrace.start_time >= start_datetime,
            ExpertCallTrace.start_time <= end_datetime,
        )
        .group_by(
            func.coalesce(ExpertCallTrace.model_code, "deepseek-v4-flash"),
            LLMModelRoute.currency,
            ExpertCallTrace.currency,
        )
    )

    stats = []
    for row in result.all():
        total = int(row.total_calls or 0)
        avg_latency = float(row.total_duration_ms or 0) / total if total > 0 else 0.0

        stats.append({
            "model_code": row.model_code,
            "currency": row.currency,
            "total_calls": total,
            "total_tokens": int(row.total_tokens or 0),
            "total_cost": float(row.total_cost or 0),
            "avg_latency_ms": avg_latency,
        })

    return ResponseData(data=stats)


@static_router.get("/stats/daily", response_model=ResponseData)
async def get_daily_trend(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    provider_code: str = Query(None, description="Provider 编码（可选）"),
    model_code: str = Query(None, description="模型编码（可选）"),
    db: AsyncSession = Depends(get_db),
):
    """获取每日趋势统计（从 ExpertCallTrace 原始表查询）"""
    from datetime import datetime, timedelta
    from sqlalchemy import select, func, and_
    from app.models.expert_call_trace import ExpertCallTrace
    from app.models.llm_model_route import LLMModelRoute

    # 默认最近 7 天
    if not end_date:
        end_dt = datetime.now().date()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    if not start_date:
        start_dt = end_dt - timedelta(days=7)
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()

    # 构建查询条件
    start_datetime = datetime.combine(start_dt, datetime.min.time())
    end_datetime = datetime.combine(end_dt, datetime.max.time())

    conditions = [
        ExpertCallTrace.start_time >= start_datetime,
        ExpertCallTrace.start_time <= end_datetime,
    ]
    if provider_code:
        conditions.append(ExpertCallTrace.provider_code == provider_code)
    if model_code:
        conditions.append(func.coalesce(ExpertCallTrace.model_code, "deepseek-v4-flash") == model_code)

    # 从 ExpertCallTrace 原始表查询并关联 LLMModelRoute 获取币种
    result = await db.execute(
        select(
            func.date(ExpertCallTrace.start_time).label("stat_date"),
            func.coalesce(LLMModelRoute.currency, ExpertCallTrace.currency, "USD").label("currency"),
            func.count().label("total_calls"),
            func.sum(ExpertCallTrace.total_tokens).label("total_tokens"),
            func.sum(ExpertCallTrace.total_cost).label("total_cost"),
        )
        .outerjoin(
            LLMModelRoute,
            LLMModelRoute.model_code == ExpertCallTrace.model_code,
        )
        .where(and_(*conditions))
        .group_by(func.date(ExpertCallTrace.start_time), LLMModelRoute.currency, ExpertCallTrace.currency)
        .order_by(func.date(ExpertCallTrace.start_time))
    )

    stats = []
    for row in result.all():
        date_str = row.stat_date.strftime("%Y-%m-%d") if row.stat_date else ""
        stats.append({
            "date": date_str,
            "currency": row.currency,
            "total_calls": int(row.total_calls or 0),
            "total_tokens": int(row.total_tokens or 0),
            "total_cost": float(row.total_cost or 0),
        })

    return ResponseData(data=stats)
