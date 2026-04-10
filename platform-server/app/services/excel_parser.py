"""
Excel 解析服务 - 根据 CorpusTemplate 定义解析 Excel 文件
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import openpyxl

from app.models.corpus_template import CorpusTemplate
from app.schemas.node_pending_audit import NodePendingAuditCreate

logger = logging.getLogger(__name__)


class ExcelParser:
    """Excel 解析器"""

    SUPPORTED_TYPES = {"excel", "xlsx", "xls"}

    @classmethod
    def is_supported(cls, file_type: str) -> bool:
        """检查文件类型是否支持"""
        return file_type.lower() in cls.SUPPORTED_TYPES

    @classmethod
    async def parse_file(
        cls,
        file_path: str,
        template: CorpusTemplate,
        knowledge_base_file_id: int,
        tenant_code: str = "default",
    ) -> tuple[list[NodePendingAuditCreate], int]:
        """
        根据 CorpusTemplate 解析 Excel 文件

        Args:
            file_path: Excel 文件路径
            template: 语料模板定义
            knowledge_base_file_id: 关联的知识库文件 ID
            tenant_code: 租户编码

        Returns:
            (解析成功的记录列表, 文件总行数)
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        workbook = openpyxl.load_workbook(file_path, read_only=True)
        sheet = workbook.active

        # 获取表头
        headers = []
        for cell in sheet[1]:
            headers.append(cell.value)

        logger.info(f"Excel 表头: {headers}")

        # 构建列索引映射（key -> column_index）
        col_mapping = {}
        for field_def in template.fields:
            key = field_def.get("key")
            label = field_def.get("label")
            # 优先用 key 匹配，其次用 label 匹配
            if key in headers:
                col_mapping[key] = headers.index(key)
            elif label in headers:
                col_mapping[key] = headers.index(label)
            else:
                logger.warning(f"字段 {key}({label}) 在 Excel 中未找到")

        if not col_mapping:
            raise ValueError("无法映射任何字段，请检查 Excel 表头与模板定义")

        # 解析数据行
        records = []
        row_number = 2  # Excel 数据行从第 2 行开始

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(row):  # 跳过空行
                row_number += 1
                continue

            try:
                record = cls._parse_row(
                    row=row,
                    headers=headers,
                    col_mapping=col_mapping,
                    template=template,
                    knowledge_base_file_id=knowledge_base_file_id,
                    tenant_code=tenant_code,
                    row_number=row_number,
                )
                records.append(record)
            except Exception as e:
                logger.warning(f"解析第 {row_number} 行失败: {e}, 行数据: {row}")

            row_number += 1

        workbook.close()

        total_rows = row_number - 2  # 减去表头
        logger.info(f"解析完成: 总行数={total_rows}, 成功={len(records)}")

        return records, total_rows

    @classmethod
    def _parse_row(
        cls,
        row: tuple,
        headers: list,
        col_mapping: dict,
        template: CorpusTemplate,
        knowledge_base_file_id: int,
        tenant_code: str,
        row_number: int,
    ) -> NodePendingAuditCreate:
        """解析单行数据"""
        # 提取各字段值
        field_values = {}
        for key, col_idx in col_mapping.items():
            if col_idx < len(row):
                value = row[col_idx]
                if value is not None:
                    field_values[key] = str(value).strip()

        # 检查必填字段
        for field_def in template.fields:
            key = field_def.get("key")
            required = field_def.get("required", False)
            if required and key not in field_values:
                raise ValueError(f"必填字段 {key} 缺失")

        # 构建节点数据
        # name 是必需的，通常从第一个字段或专门的 name 字段获取
        name = field_values.get("name") or cls._get_first_non_empty_value(field_values)

        # corpus 构建逻辑：根据模板定义组装
        corpus = cls._build_corpus(field_values, template)

        # properties 存储所有字段值
        properties = {"raw_fields": field_values}

        return NodePendingAuditCreate(
            tenant_code=tenant_code,
            file_pool_id=knowledge_base_file_id,
            label=template.category_type,  # 使用 category_type 作为 label
            name=name,
            description=field_values.get("description"),
            corpus=corpus,
            properties=properties,
            row_number=row_number,
        )

    @classmethod
    def _build_corpus(cls, field_values: dict, template: CorpusTemplate) -> Optional[list]:
        """
        根据模板定义构建 corpus

        规则：
        1. 如果有 corpus/corpus_text 字段，直接使用
        2. 否则将非特殊字段组合成 corpus
        """
        # 优先使用专门的 corpus 字段
        if "corpus" in field_values:
            text = field_values["corpus"]
            return [{"text": text, "weight": 1.0}]

        if "corpus_text" in field_values:
            text = field_values["corpus_text"]
            weight = float(field_values.get("weight", 1.0))
            return [{"text": text, "weight": weight}]

        # 自动构建：排除元数据字段，将内容字段合并
        exclude_keys = {"name", "description", "weight", "id"}
        content_parts = []

        for key, value in field_values.items():
            if key not in exclude_keys:
                content_parts.append(f"{key}:{value}")

        if content_parts:
            return [{"text": " ".join(content_parts), "weight": 1.0}]

        return None

    @classmethod
    def _get_first_non_empty_value(cls, field_values: dict) -> str:
        """获取第一个非空字段值作为 name"""
        exclude_keys = {"id", "weight"}
        for key, value in field_values.items():
            if key not in exclude_keys and value:
                return value
        return "未命名"


class CsvParser:
    """CSV 解析器（预留，当前主要处理 Excel）"""

    SUPPORTED_TYPES = {"csv"}

    @classmethod
    def is_supported(cls, file_type: str) -> bool:
        """检查文件类型是否支持"""
        return file_type.lower() in cls.SUPPORTED_TYPES

    # TODO: 实现 CSV 解析逻辑
