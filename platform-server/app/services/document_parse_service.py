"""
文档解析 Expert - 从文档中提取结构化语料数据
"""
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from app.services.document_parser_service import DocumentParser
from app.services.critic_dapr_service import run_critic_http


class ModelCfg(BaseModel):
    temperature: float = 0.3
    max_tokens: int = 4000


class DocumentParseReq(BaseModel):
    """文档解析请求"""
    job_id: str
    sub_job_id: str
    content_id: str
    file_path: str = Field(..., description="文档文件路径")
    file_type: str = Field(..., description="文件类型: pdf/docx/pptx/xlsx")
    category_type: str = Field(..., description="分类类型（对应 keyword-corpus 的 corpus_templates.category_type）")
    template_fields: List[Dict[str, Any]] = Field(..., description="语料模板字段定义")
    tenant_code: str = "default"
    model_code: str = "gpt-4o"
    model_cfg: ModelCfg = Field(alias="model_config")

    # 可选：如果已经有文本内容，直接使用
    pre_extracted_text: Optional[str] = None


class DocumentParseService:
    """文档解析服务"""

    @staticmethod
    async def parse_document(req: DocumentParseReq) -> dict:
        """
        解析文档并提取结构化语料数据

        流程：
        1. 从文档提取文本内容
        2. 根据 template_fields 构建 prompt
        3. 调用 LLM 进行结构化提取
        4. 返回解析结果
        """
        # Step 1: 提取文本内容
        if req.pre_extracted_text:
            extracted_text = req.pre_extracted_text
        else:
            parse_result = await DocumentParser.parse_file(
                file_path=req.file_path,
                file_type=req.file_type,
            )
            if not parse_result["success"]:
                return {
                    "success": False,
                    "message": "文档文本提取失败",
                    "error": parse_result.get("error"),
                    "items": [],
                }
            extracted_text = parse_result["text"]

        if not extracted_text.strip():
            return {
                "success": False,
                "message": "文档内容为空",
                "items": [],
            }

        # Step 2: 构建解析 prompt
        prompt = DocumentParseService._build_extraction_prompt(
            category_type=req.category_type,
            template_fields=req.template_fields,
            document_text=extracted_text,
        )

        # Step 3: 调用 LLM 进行结构化提取
        payload = {
            "job_id": req.job_id,
            "sub_job_id": req.sub_job_id,
            "content_id": req.content_id,
            "content": extracted_text,
            "expert_task_id": 1,  # 占位
            "expert_config_code": f"document_parser_{req.category_type}",
            "expert_service": "document_parser.DocumentParserService",
            "expert_func": "ParseDocument",
            "prompt": prompt,
            "model_code": req.model_code,
            "model_config": {
                "temperature": req.model_cfg.temperature,
                "max_tokens": req.model_cfg.max_tokens,
            },
            "tenant_code": req.tenant_code,
        }

        try:
            llm_response = await run_critic_http(
                request_data=payload,
                stage="document_parser",
                service_method="ParseDocument",
            )
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {
                "success": False,
                "message": f"AI 解析失败: {str(e)}",
                "items": [],
            }

        # Step 4: 解析 LLM 返回结果
        items = DocumentParseService._parse_llm_response(
            llm_response,
            req.template_fields,
            req.category_type,
        )

        return {
            "success": True,
            "message": f"成功解析 {len(items)} 条数据",
            "items": items,
            "document_text_length": len(extracted_text),
            "raw_response": llm_response.get("response", {}),
        }

    @staticmethod
    def _build_extraction_prompt(
        category_type: str,
        template_fields: List[Dict[str, Any]],
        document_text: str,
    ) -> str:
        """构建结构化提取 prompt"""
        # 构建字段描述
        field_descriptions = []
        required_fields = []

        for field in template_fields:
            key = field.get("key", "")
            label = field.get("label", key)
            required = field.get("required", False)
            field_type = field.get("type", "text")

            desc = f"- {label} ({key}, 类型: {field_type}"
            if required:
                desc += ", 必填"
                required_fields.append(label)
            field_descriptions.append(desc + ")")

            # 添加选项说明
            if field.get("options"):
                options = field["options"]
                desc = f"  可选值: {', '.join(options)}"
                field_descriptions.append(desc)

        fields_text = "\n".join(field_descriptions)
        required_text = "、".join(required_fields) if required_fields else "无"

        # 文本截断（避免 prompt 过长）
        max_text_length = 8000
        truncated_text = document_text[:max_text_length]
        if len(document_text) > max_text_length:
            truncated_text += "\n...(文档已截断)"

        prompt = f"""你是一个专业的文档数据提取助手。请从以下文档内容中提取结构化数据。

## 数据类型
{category_type}

## 需要提取的字段
{fields_text}

## 输出要求
1. 必须是有效的 JSON 数组格式
2. 每个对象代表一条数据记录
3. 如果某个字段在文档中找不到，填入 null 或空字符串
4. 必填字段：{required_text}
5. 对于数组/列表类型字段，如果有多条，用逗号分隔或返回数组

## 文档内容
```
{truncated_text}
```

## 输出格式
请直接返回 JSON 数组，不要包含其他说明文字：
[
  {{
    "name": "示例名称",
    "description": "示例描述",
    ...
  }}
]
"""
        return prompt

    @staticmethod
    def _parse_llm_response(
        llm_response: dict,
        template_fields: List[Dict[str, Any]],
        category_type: str,
    ) -> List[Dict[str, Any]]:
        """解析 LLM 返回的结构化数据"""
        import json
        import re

        # 从响应中提取文本
        response_text = llm_response.get("response", {}).get("text", "")
        if not response_text:
            response_text = llm_response.get("text", "")
        if not response_text:
            response_text = str(llm_response.get("response", ""))

        # 尝试提取 JSON 数组
        items = []

        # 方法1: 直接解析
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict) and "items" in parsed:
                items = parsed["items"]
            elif isinstance(parsed, dict) and "data" in parsed:
                data = parsed["data"]
                items = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass

        # 方法2: 提取 JSON 代码块
        if not items:
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                try:
                    items = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

        # 方法3: 提取数组
        if not items:
            array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
            if array_match:
                try:
                    items = json.loads(array_match.group(0))
                except json.JSONDecodeError:
                    pass

        # 标准化字段
        field_keys = {f.get("key"): f for f in template_fields}

        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized_item = {
                "label": category_type,  # 使用 category_type 作为 label
            }

            for key, field_def in field_keys.items():
                value = item.get(key) or item.get(field_def.get("label", ""))

                # 类型转换
                field_type = field_def.get("type", "text")
                if field_type == "textarea" or field_type == "text":
                    normalized_item[key] = str(value) if value else ""
                elif field_type == "number":
                    try:
                        normalized_item[key] = float(value) if value else 0
                    except (ValueError, TypeError):
                        normalized_item[key] = 0
                elif field_type == "checkbox":
                    normalized_item[key] = bool(value)

                # corpus 特殊处理
                if key == "corpus" and isinstance(value, str):
                    normalized_item[key] = [{"text": value, "weight": 1.0}]
                elif key == "corpus" and isinstance(value, list):
                    normalized_item[key] = value
                elif key == "corpus" and not value:
                    normalized_item[key] = None

            # name 必填
            if not normalized_item.get("name"):
                normalized_item["name"] = "未命名"

            normalized_items.append(normalized_item)

        return normalized_items
