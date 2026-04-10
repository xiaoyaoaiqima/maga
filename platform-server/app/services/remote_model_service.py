"""
远程模型获取服务

支持从不同 Provider 获取可用模型列表：
- 智谱 GLM (bigmodel.cn): https://open.bigmodel.cn/api/paas/v4/models
- AiHubMix: https://aihubmix.com/api/v1/models
- OpenAI 兼容: /v1/models
"""
import httpx
from typing import Optional, List, Dict, Any
from decimal import Decimal

from app.core.logger import logger


class RemoteModel:
    """远程模型信息"""
    def __init__(
        self,
        model_id: str,
        model_name: Optional[str] = None,
        description: Optional[str] = None,
        model_type: str = "llm",
        features: Optional[List[str]] = None,
        input_modalities: Optional[List[str]] = None,
        max_output: Optional[int] = None,
        context_length: Optional[int] = None,
        cost_per_1k_input: Optional[Decimal] = None,
        cost_per_1k_output: Optional[Decimal] = None,
    ):
        self.model_id = model_id
        self.model_name = model_name or model_id
        self.description = description
        self.model_type = model_type
        self.features = features or []
        self.input_modalities = input_modalities or ["text"]
        self.max_output = max_output
        self.context_length = context_length
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "description": self.description,
            "model_type": self.model_type,
            "features": self.features,
            "input_modalities": self.input_modalities,
            "max_output": self.max_output,
            "context_length": self.context_length,
            "cost_per_1k_input": float(self.cost_per_1k_input) if self.cost_per_1k_input else None,
            "cost_per_1k_output": float(self.cost_per_1k_output) if self.cost_per_1k_output else None,
        }


class RemoteModelService:
    """远程模型获取服务"""

    # AiHubMix Models API
    AIHUBMIX_MODELS_API = "https://aihubmix.com/api/v1/models"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def get_models(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        provider_type: str = "openai_compatible",
        model_type_filter: Optional[str] = "llm",
    ) -> List[RemoteModel]:
        """
        获取远程模型列表

        Args:
            base_url: Provider 的 API 地址
            api_key: API Key（某些接口不需要）
            provider_type: Provider 类型
            model_type_filter: 过滤模型类型（llm/image_generation/embedding 等）

        Returns:
            远程模型列表

        Raises:
            ValueError: 当 Provider 类型不支持或获取模型失败时
        """
        if not base_url or not base_url.strip():
            raise ValueError("base_url 不能为空")

        base_url = base_url.strip()
        provider_type = provider_type or "openai_compatible"

        # 检测是否是智谱 GLM (bigmodel.cn)
        if "bigmodel.cn" in base_url:
            return await self._get_glm_models(base_url, api_key)

        # 检测是否是 AiHubMix
        if "aihubmix.com" in base_url:
            return await self._get_aihubmix_models(model_type_filter)

        # 其他 OpenAI 兼容 Provider
        if provider_type == "openai_compatible":
            return await self._get_openai_compatible_models(base_url, api_key)

        # 不支持的 Provider 类型
        raise ValueError(f"不支持的 Provider 类型: {provider_type}。当前仅支持: openai_compatible, aihubmix.com, bigmodel.cn")
    
    async def _get_aihubmix_models(
        self,
        model_type_filter: Optional[str] = "llm",
    ) -> List[RemoteModel]:
        """
        从 AiHubMix 获取模型列表
        
        API 文档: https://docs.aihubmix.com/cn/api/Models-API
        """
        try:
            params = {}
            if model_type_filter:
                params["type"] = model_type_filter
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.AIHUBMIX_MODELS_API,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
            
            # 验证响应数据格式
            if not isinstance(data, dict):
                raise ValueError(f"AiHubMix API 返回数据格式错误: 期望字典，实际为 {type(data).__name__}")
            
            # 获取模型列表，确保是列表类型
            models_data = data.get("data", [])
            if not isinstance(models_data, list):
                logger.warning(f"AiHubMix API 返回的 data 字段不是列表类型: {type(models_data).__name__}，尝试转换")
                if models_data is None:
                    models_data = []
                else:
                    models_data = [models_data] if not isinstance(models_data, (str, bytes)) else []
            
            models = []
            for item in models_data:
                # 确保 item 是字典类型
                if not isinstance(item, dict):
                    logger.warning(f"跳过非字典类型的模型项: {type(item).__name__}")
                    continue
                
                model_id = item.get("model_id", "")
                if not model_id:
                    continue
                
                # 解析 features 字符串为列表
                features_str = item.get("features", "")
                if not isinstance(features_str, str):
                    features_str = str(features_str) if features_str else ""
                features = [f.strip() for f in features_str.split(",") if f.strip()] if features_str else []
                
                # 解析 input_modalities 字符串为列表
                modalities_str = item.get("input_modalities", "text")
                if not isinstance(modalities_str, str):
                    modalities_str = str(modalities_str) if modalities_str else "text"
                modalities = [m.strip() for m in modalities_str.split(",") if m.strip()] if modalities_str else ["text"]
                
                # 解析价格信息
                pricing = item.get("pricing", {})
                if not isinstance(pricing, dict):
                    pricing = {}
                cost_input = pricing.get("input")
                cost_output = pricing.get("output")
                
                model = RemoteModel(
                    model_id=str(model_id),
                    model_name=str(model_id),  # AiHubMix 没有单独的 name 字段
                    description=item.get("desc"),
                    model_type=item.get("types", "llm") or "llm",
                    features=features,
                    input_modalities=modalities,
                    max_output=item.get("max_output"),
                    context_length=item.get("context_length"),
                    # 将 aihubmix 的 "每 1M token 价格" 转换为系统要求的 "每 1K token 价格"
                    cost_per_1k_input=Decimal(str(cost_input)) / 1000 if cost_input is not None else None,
                    cost_per_1k_output=Decimal(str(cost_output)) / 1000 if cost_output is not None else None,
                )
                models.append(model)
            
            logger.info(f"从 AiHubMix 获取到 {len(models)} 个模型")
            return models
            
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = f" - {e.response.text[:200]}"
            except:
                pass
            logger.error(f"AiHubMix API HTTP 错误: {e.response.status_code}{error_detail}")
            raise ValueError(f"获取 AiHubMix 模型失败: HTTP {e.response.status_code}")
        except httpx.TimeoutException as e:
            logger.error(f"AiHubMix API 请求超时: {e}")
            raise ValueError(f"获取 AiHubMix 模型失败: 请求超时（{self.timeout}秒）")
        except httpx.RequestError as e:
            logger.error(f"AiHubMix API 请求错误: {e}")
            raise ValueError(f"获取 AiHubMix 模型失败: 网络请求错误 - {str(e)}")
        except ValueError as e:
            # 重新抛出 ValueError，保持原有错误信息
            raise
        except Exception as e:
            logger.error(f"获取 AiHubMix 模型异常: {type(e).__name__}: {e}", exc_info=True)
            raise ValueError(f"获取 AiHubMix 模型失败: {str(e)}")

    async def _get_glm_models(
        self,
        base_url: str,
        api_key: Optional[str] = None,
    ) -> List[RemoteModel]:
        """
        从智谱 GLM (bigmodel.cn) 获取模型列表

        API 文档: https://open.bigmodel.cn/dev/api
        智谱使用 /api/paas/v4/models 端点（注意是 /v4 不是 /v1）
        """
        try:
            # 构建正确的 models 端点 URL
            # 智谱 GLM 的端点格式: https://open.bigmodel.cn/api/paas/v4/models
            models_url = base_url.rstrip("/")
            if not models_url.endswith("/models"):
                # 如果 base_url 是 https://open.bigmodel.cn/api/paas/v4
                # 直接添加 /models，不添加 /v1
                models_url += "/models"

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(models_url, headers=headers)
                response.raise_for_status()
                data = response.json()

            # 验证响应数据格式
            if not isinstance(data, dict):
                raise ValueError(f"GLM API 返回数据格式错误: 期望字典，实际为 {type(data).__name__}")

            # 获取模型列表
            models_data = data.get("data", [])
            if not isinstance(models_data, list):
                logger.warning(f"GLM API 返回的 data 字段不是列表类型: {type(models_data).__name__}")
                if models_data is None:
                    models_data = []
                else:
                    models_data = [models_data] if not isinstance(models_data, (str, bytes)) else []

            models = []
            for item in models_data:
                if not isinstance(item, dict):
                    logger.warning(f"跳过非字典类型的模型项: {type(item).__name__}")
                    continue

                model_id = item.get("id", "")
                if not model_id:
                    continue

                if not isinstance(model_id, str):
                    model_id = str(model_id)

                model = RemoteModel(
                    model_id=model_id,
                    model_name=item.get("name", model_id) or model_id,
                    description=item.get("description"),
                    model_type="llm",
                    features=[],
                    input_modalities=["text"],
                    max_output=item.get("max_output"),
                    context_length=item.get("context_length"),
                    cost_per_1k_input=None,
                    cost_per_1k_output=None,
                )
                models.append(model)

            logger.info(f"从智谱 GLM 获取到 {len(models)} 个模型")
            return models

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = f" - {e.response.text[:200]}"
            except:
                pass
            logger.error(f"GLM API HTTP 错误: {e.response.status_code}{error_detail}")
            raise ValueError(f"获取 GLM 模型失败: HTTP {e.response.status_code}")
        except httpx.TimeoutException as e:
            logger.error(f"GLM API 请求超时: {e}")
            raise ValueError(f"获取 GLM 模型失败: 请求超时（{self.timeout}秒）")
        except httpx.RequestError as e:
            logger.error(f"GLM API 请求错误: {e}")
            raise ValueError(f"获取 GLM 模型失败: 网络请求错误 - {str(e)}")
        except ValueError as e:
            raise
        except Exception as e:
            logger.error(f"获取 GLM 模型异常: {type(e).__name__}: {e}", exc_info=True)
            raise ValueError(f"获取 GLM 模型失败: {str(e)}")

    async def _get_openai_compatible_models(
        self,
        base_url: str,
        api_key: Optional[str] = None,
    ) -> List[RemoteModel]:
        """
        从 OpenAI 兼容 API 获取模型列表
        
        标准端点: GET /v1/models
        """
        try:
            # 构建 models 端点 URL
            models_url = base_url.rstrip("/")
            if not models_url.endswith("/models"):
                if models_url.endswith("/v1"):
                    models_url += "/models"
                else:
                    models_url += "/v1/models"
            
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(models_url, headers=headers)
                response.raise_for_status()
                data = response.json()
            
            # 验证响应数据格式
            if not isinstance(data, dict):
                raise ValueError(f"API 返回数据格式错误: 期望字典，实际为 {type(data).__name__}")
            
            # 获取模型列表，确保是列表类型
            models_data = data.get("data", [])
            if not isinstance(models_data, list):
                logger.warning(f"API 返回的 data 字段不是列表类型: {type(models_data).__name__}，尝试转换")
                if models_data is None:
                    models_data = []
                else:
                    # 如果不是列表，尝试包装成列表
                    models_data = [models_data] if not isinstance(models_data, (str, bytes)) else []
            
            models = []
            for item in models_data:
                # 确保 item 是字典类型
                if not isinstance(item, dict):
                    logger.warning(f"跳过非字典类型的模型项: {type(item).__name__}")
                    continue
                
                model_id = item.get("id", "")
                if not model_id:
                    continue
                
                # 确保 model_id 是字符串
                if not isinstance(model_id, str):
                    model_id = str(model_id)
                
                model = RemoteModel(
                    model_id=model_id,
                    model_name=item.get("name", model_id) or model_id,
                    description=None,
                    model_type="llm",
                    features=[],
                    input_modalities=["text"],
                    max_output=None,
                    context_length=None,
                    cost_per_1k_input=None,
                    cost_per_1k_output=None,
                )
                models.append(model)
            
            logger.info(f"从 OpenAI 兼容 API 获取到 {len(models)} 个模型")
            return models
            
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = f" - {e.response.text[:200]}"
            except:
                pass
            logger.error(f"OpenAI 兼容 API HTTP 错误: {e.response.status_code}{error_detail}")
            raise ValueError(f"获取模型列表失败: HTTP {e.response.status_code}")
        except httpx.TimeoutException as e:
            logger.error(f"OpenAI 兼容 API 请求超时: {e}")
            raise ValueError(f"获取模型列表失败: 请求超时（{self.timeout}秒）")
        except httpx.RequestError as e:
            logger.error(f"OpenAI 兼容 API 请求错误: {e}")
            raise ValueError(f"获取模型列表失败: 网络请求错误 - {str(e)}")
        except ValueError as e:
            # 重新抛出 ValueError，保持原有错误信息
            raise
        except Exception as e:
            logger.error(f"获取 OpenAI 兼容模型异常: {type(e).__name__}: {e}", exc_info=True)
            raise ValueError(f"获取模型列表失败: {str(e)}")


# 单例
remote_model_service = RemoteModelService()

