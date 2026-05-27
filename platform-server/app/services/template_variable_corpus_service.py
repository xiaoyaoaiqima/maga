"""Template-variable corpus service.

This service intentionally stores operator-facing prompt variable corpus in the
existing ``nodes`` table, while marking rows with a narrow ``properties.kind``.
That keeps the MVP migration-free and prevents low-level graph nodes from
leaking into the new corpus workspace.
"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.graph import GraphNode
from app.schemas.template_variable_corpus import (
    PromptPreviewRequest,
    PromptPreviewResponse,
    TemplateVariableCorpusCreate,
    TemplateVariableCorpusItem,
    TemplateVariableCorpusUpdate,
    TemplateVariableItem,
)
from app.services.category_service import generate_id


VARIABLE_PATTERN = re.compile(r"{{\s*([^{}\s][^{}]*?)\s*}}")
CORPUS_KIND = "template_variable_corpus"
DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "生文提示词模版.md"
)
DEFAULT_TEMPLATE_TEXT = """{{生文指令}}

{{扰动规则}}

{{人设}}
---

{{标题要求}}
{{内容结构}}
{{文章排版结构}}
{{字数要求}}
{{emoji要求}}
---

{{品牌介绍}}
---
## 品牌违禁词，**100%禁止使用**：
{{品牌合规}}
---

## 产品使用体验
{{产品基本信息}}
{{痛点}}
注意：痛点和使用后观察只作为语义素材，不是正文原句。生成时必须重新组织表达，禁止照搬原句、固定数字、固定时间、固定程度词和原有句式，也不能只做同义词替换。最终表达要像真实用户随手写出来的生活观察
---

{{表达写作规则}}

{{生文输出格式}}"""


def resolve_default_template_path() -> Path:
    """Find the prompt template across local and container layouts."""
    filename = "生文提示词模版.md"
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "prompts" / filename
        if candidate.exists():
            return candidate
    return DEFAULT_TEMPLATE_PATH


class TemplateVariableCorpusService:
    """Manage Markdown corpus snippets keyed by prompt template variable."""

    def __init__(self, db: AsyncSession, template_path: Path | None = None):
        self.db = db
        self.template_path = template_path or resolve_default_template_path()

    async def list_variables(self, tenant_code: str = "default") -> list[TemplateVariableItem]:
        """List variables parsed from the prompt template with corpus counts."""
        variables = self.parse_template_variables()
        items = await self._list_nodes(tenant_code=tenant_code)
        stats: dict[str, dict[str, int]] = {
            variable: {"corpus_count": 0, "active_count": 0, "draft_count": 0}
            for variable in variables
        }

        for node in items:
            variable = node.label
            if variable not in stats:
                stats[variable] = {"corpus_count": 0, "active_count": 0, "draft_count": 0}
                variables.append(variable)
            status = self._node_status(node)
            stats[variable]["corpus_count"] += 1
            if status == "active":
                stats[variable]["active_count"] += 1
            elif status == "draft":
                stats[variable]["draft_count"] += 1

        return [
            TemplateVariableItem(
                name=variable,
                corpus_count=stats[variable]["corpus_count"],
                active_count=stats[variable]["active_count"],
                draft_count=stats[variable]["draft_count"],
            )
            for variable in variables
        ]

    async def list_corpus(
        self,
        *,
        variable_name: str | None = None,
        tenant_code: str = "default",
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TemplateVariableCorpusItem], int]:
        nodes = await self._list_nodes(tenant_code=tenant_code, variable_name=variable_name)
        filtered = []
        keyword_norm = keyword.strip().lower() if keyword else ""
        for node in nodes:
            item = self._to_item(node)
            if status and item.status != status:
                continue
            if keyword_norm and keyword_norm not in f"{item.name}\n{item.markdown}".lower():
                continue
            filtered.append(item)

        total = len(filtered)
        start = (page - 1) * page_size
        return filtered[start : start + page_size], total

    async def create_corpus(self, payload: TemplateVariableCorpusCreate) -> TemplateVariableCorpusItem:
        properties = {
            "kind": CORPUS_KIND,
            "tags": payload.tags,
            "status": payload.status,
            "source": payload.source,
        }
        node = GraphNode(
            id=generate_id(),
            tenant_code=payload.tenant_code,
            label=payload.variable_name,
            name=payload.name,
            corpus=[{"text": payload.markdown, "weight": 1}],
            properties=properties,
            is_active=0 if payload.status == "archived" else 1,
            created_by=payload.created_by,
            updated_by=payload.created_by,
        )
        self.db.add(node)
        await self.db.commit()
        await self.db.refresh(node)
        return self._to_item(node)

    async def update_corpus(
        self,
        item_id: int,
        payload: TemplateVariableCorpusUpdate,
    ) -> TemplateVariableCorpusItem | None:
        node = await self._get_managed_node(item_id)
        if node is None:
            return None

        if payload.name is not None:
            node.name = payload.name
        if payload.markdown is not None:
            node.corpus = [{"text": payload.markdown, "weight": 1}]
        properties = dict(node.properties or {})
        if payload.tags is not None:
            properties["tags"] = payload.tags
        if payload.status is not None:
            properties["status"] = payload.status
            node.is_active = 0 if payload.status == "archived" else 1
        if payload.source is not None:
            properties["source"] = payload.source
        properties["kind"] = CORPUS_KIND
        node.properties = properties
        node.updated_by = payload.updated_by
        flag_modified(node, "properties")
        flag_modified(node, "corpus")

        await self.db.commit()
        await self.db.refresh(node)
        return self._to_item(node)

    async def archive_corpus(self, item_id: int) -> bool:
        node = await self._get_managed_node(item_id)
        if node is None:
            return False
        properties = dict(node.properties or {})
        properties["kind"] = CORPUS_KIND
        properties["status"] = "archived"
        node.properties = properties
        node.is_active = 0
        flag_modified(node, "properties")
        await self.db.commit()
        return True

    async def preview_prompt(self, payload: PromptPreviewRequest) -> PromptPreviewResponse:
        template = self._read_template()
        variables = self.parse_template_variables(template)
        used_items: dict[str, TemplateVariableCorpusItem] = {}
        missing_variables: list[str] = []

        for variable in variables:
            draft_value = payload.draft_values.get(variable)
            if draft_value:
                used_items[variable] = TemplateVariableCorpusItem(
                    id=0,
                    tenant_code=payload.tenant_code,
                    variable_name=variable,
                    name="当前编辑内容",
                    markdown=draft_value,
                    tags=[],
                    status="draft",
                )
                continue

            selected_id = payload.selected_item_ids.get(variable)
            node = await self._get_selected_or_default_node(
                variable_name=variable,
                tenant_code=payload.tenant_code,
                selected_id=selected_id,
                fill_mode=payload.fill_mode,
            )
            if node is None:
                missing_variables.append(variable)
            else:
                used_items[variable] = self._to_item(node)

        def replace(match: re.Match[str]) -> str:
            variable = match.group(1).strip()
            item = used_items.get(variable)
            if item is not None:
                return item.markdown
            return "" if payload.missing_policy == "empty" else match.group(0)

        return PromptPreviewResponse(
            template_path=str(self.template_path),
            rendered_prompt=VARIABLE_PATTERN.sub(replace, template),
            used_items=used_items,
            missing_variables=missing_variables,
        )

    def parse_template_variables(self, template_text: str | None = None) -> list[str]:
        text = template_text if template_text is not None else self._read_template()
        variables: list[str] = []
        seen: set[str] = set()
        for match in VARIABLE_PATTERN.finditer(text):
            variable = match.group(1).strip()
            if variable and variable not in seen:
                variables.append(variable)
                seen.add(variable)
        return variables

    def _read_template(self) -> str:
        if not self.template_path.exists():
            # Dev containers currently mount the backend app without the sibling
            # prompts directory; keep the operator UI usable with the checked-in
            # template content until that directory is mounted.
            return DEFAULT_TEMPLATE_TEXT
        return self.template_path.read_text(encoding="utf-8")

    async def _get_managed_node(self, item_id: int) -> GraphNode | None:
        node = await self.db.get(GraphNode, item_id)
        if node is None or node.is_deleted != 0:
            return None
        if (node.properties or {}).get("kind") != CORPUS_KIND:
            return None
        return node

    async def _get_selected_or_default_node(
        self,
        *,
        variable_name: str,
        tenant_code: str,
        selected_id: str | None,
        fill_mode: str,
    ) -> GraphNode | None:
        if selected_id:
            try:
                node = await self._get_managed_node(int(selected_id))
            except ValueError:
                node = None
            if node is not None and node.tenant_code == tenant_code and node.label == variable_name:
                return node

        if fill_mode == "selected_only":
            return None

        nodes = await self._list_nodes(
            tenant_code=tenant_code,
            variable_name=variable_name,
            active_only=True,
        )
        if not nodes:
            return None
        # Equal-weight random selection gives preview a realistic batch feel,
        # without introducing strategy rules before the strategy page exists.
        return random.choice(nodes)

    async def _list_nodes(
        self,
        *,
        tenant_code: str,
        variable_name: str | None = None,
        active_only: bool = False,
    ) -> list[GraphNode]:
        conditions = [
            GraphNode.tenant_code == tenant_code,
            GraphNode.is_deleted == 0,
        ]
        if variable_name:
            conditions.append(GraphNode.label == variable_name)
        if active_only:
            conditions.append(GraphNode.is_active == 1)

        result = await self.db.execute(
            select(GraphNode)
            .where(and_(*conditions))
            .order_by(GraphNode.updated_at.desc(), GraphNode.id.desc())
        )
        return [
            node
            for node in result.scalars().all()
            if isinstance(node.properties, dict)
            and node.properties.get("kind") == CORPUS_KIND
        ]

    def _to_item(self, node: GraphNode) -> TemplateVariableCorpusItem:
        properties = node.properties or {}
        return TemplateVariableCorpusItem(
            id=node.id,
            tenant_code=node.tenant_code,
            variable_name=node.label,
            name=node.name,
            markdown=self._node_markdown(node),
            tags=self._string_list(properties.get("tags")),
            status=self._node_status(node),
            source=properties.get("source"),
            created_by=node.created_by,
            updated_by=node.updated_by,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )

    def _node_markdown(self, node: GraphNode) -> str:
        corpus = node.corpus or []
        if isinstance(corpus, list) and corpus:
            first = corpus[0]
            if isinstance(first, dict):
                return str(first.get("text") or "")
        return ""

    def _node_status(self, node: GraphNode) -> str:
        status = (node.properties or {}).get("status")
        if status in {"active", "draft", "archived"}:
            return status
        return "active" if node.is_active else "archived"

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
