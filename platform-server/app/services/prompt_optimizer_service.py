"""
Prompt optimizer workbench service.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_optimizer import (
    PromptAsset,
    PromptIssue,
    PromptOptimizerRun,
    PromptPatch,
    PromptVersion,
)
from app.schemas.prompt_optimizer import (
    PromptAssetCreate,
    PromptAssetUpdate,
    PromptOptimizerRunCreate,
    PromptPatchApplyRequest,
    PromptPatchApplyResponse,
    PromptPatchApplyConflict,
    PromptPatchUpdate,
    PromptVersionCreate,
    PromptVersionResponse,
)


DEFAULT_BASE_URL = "https://aihubmix.com/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 8000
DEFAULT_TIMEOUT_SECONDS = 90


LOCAL_PATCH_SYSTEM_PROMPT = """你是一个资深小红书内容生产与提示词优化专家。
你需要根据原始生文提示词、生成结果和运营审查问题，反推出提示词设计上的缺陷，并给出可执行的修改方案。
优先修改规则指令，尽量不修改痛点描述/卖点描述这类纯描述类提示词。

优化原则：
- 只提出能被“生成结果 + 运营审查问题”直接支持的最小必要修改，避免把单个问题扩展成更宽、更硬的禁令。
- 对单篇 badcase 的局部问题，优先把“生成原文 + 具体问题”写成提示词中的反例/违规示例，不要改写成“可能让读者困惑、不符合常识”等抽象禁令。
- 如果原提示词已有相近的违规示例或反例位置，优先在该位置补充一条具体 badcase，格式必须包含原文和问题，例如：`- 违规示例：`原文片段`\n- 问题：具体说明这句为什么不成立/不可理解/会误导`。
- 修改前必须先检查原提示词是否已经存在同义或近义规则；如果已有规则覆盖该要求，不要重复新增同义规则，应诊断为已有规则作用范围不够明确、被局部规则稀释或表达不够可执行。
- 禁止过度泛化：如果问题是某个固定句式或表达方式违规，只禁止该句式/表达方式，不要额外禁止关键词在其他合理语境中出现。
- 不要新增位置类、开场类、结构类限制，除非运营审查问题明确指出位置、开场或结构本身有问题。
- 新增规则应尽量贴近原提示词已有规则的颗粒度，一次只解决当前证据能解释的问题。
- 同一个根因只能输出一个最小 patch；不要把同一要求同时写进总规则和子规则，也不要同时 replace 两段来表达同一个修改意图。
- 如果需要增强一条已有要求，优先修改最贴近生成失败位置的局部规则；只有当局部规则缺失时，才修改更上层的总规则。
- 若运营审查问题指向“同质化、模板化、固定句式复用”，优先把原规则里的模板短语库、固定推荐句式改成“可变化维度 + 禁用固定套话”的生成约束；不要继续追加更多同类示例句或可选短语。
- 对结尾权益、福利、礼包类规则，patch 必须同时保留业务边界和表达多样性：明确权益触发动作、权益位置、福利感表达和句式结构中至少变化 2 处；禁止把“安排上 / 解锁 / 诚意很足 / 实用又惊喜”等促销套话写成推荐表达。
- 如果某条建议属于“可能有帮助但证据不足”，不要写入 added_content 或 patches，可在 modify_suggestion 中弱提示。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 原提示词的问题在哪里
- modify_suggestion: 应该怎么修改，要求具体可执行
- added_content: 建议新增到原提示词里的内容，只写新增片段；如果没有新增则返回空字符串
- removed_content: 建议从原提示词中删除或弱化的内容，只写删除片段；如果没有删除则返回空字符串
- patches: 数组，给出可直接人工替换的修改块。每个元素必须包含 operation、old_text、new_text、reason。
  - operation 只能是 replace、delete、insert_after、insert_before 之一。
  - old_text 必须是原提示词中可以直接搜索定位的连续原文片段；如果是新增，请填写插入位置附近的原文锚点。
  - new_text 是替换后或新增后的内容；如果是删除则返回空字符串。
  - reason 用一句话说明为什么这样改。
  - patches 之间不得语义重复；如果两个 patch 的 new_text 在解决同一件事，只保留更贴近问题位置、改动更小的一个。
- revised_prompt: 默认返回空字符串，不要输出完整修改后提示词，避免超长截断
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度
"""


GLOBAL_REFACTOR_SYSTEM_PROMPT = """你是一个资深提示词架构师，擅长整理冗长、重复、矛盾的内容生成提示词。
你需要根据“原始提示词”和“人类优化意见”，从全局视角诊断提示词结构问题，并给出可执行的整理方案。

这个任务不是根据某一篇生成内容做局部修补，而是根据人类意见优化整份提示词。常见背景包括：
- 提示词太长，规则重复，模型注意力被分散。
- 不同章节存在同义重复、强弱不一致或互相矛盾。
- 上层规则和局部规则边界不清，导致执行优先级混乱。
- 禁止项、允许项、示例、卖点、结构要求混在一起，导致模型误读。
- 人类希望保留核心控制力，同时降低冗余和冲突。

优化原则：
- 以人类意见为最高依据；不要引入人类意见没有要求的新创作方向、新品牌规则或新内容策略。
- 优先做全局整理：去重、合并同义规则、消除矛盾、明确优先级、把规则放回更合适的章节。
- 不要为了简洁删除关键红线、品牌限制、合规限制、输入变量约束和必须完成的任务目标。
- 如果两条规则语义相同但强度不同，保留更清晰、更可执行的一条，并在 reason 中说明取舍。
- 如果两条规则冲突，优先保留更贴近任务目标、合规红线或人类意见的一条；不要简单并列保留。
- patches 应服务于全局结构整理，可以包含 delete、replace、insert_after、insert_before，但每个 patch 都必须能被人工直接定位。
- 同一处问题只输出一个 patch；不要用多个 patch 重复表达同一个整理意图。
- 如果需要大段重组，优先输出少量“replace 整段”的 patch，而不是很多碎片化 patch。
- 若人类意见是新增或调整某条业务规则，优先将其整理成“适用条件、必须保留的业务边界、禁止项、表达变化要求”四类信息；不要把人类意见原文机械追加到提示词末尾。
- 若人类意见指向“同质化、模板化、固定句式复用”，优先删除或弱化原规则里的模板短语库、固定推荐句式，改成变量维度约束；不要继续追加更多同类示例句或可选短语。
- 对结尾权益、福利、礼包类规则，必须保留触发动作边界，且要求权益触发动作、权益位置、福利感表达和句式结构中至少变化 2 处；禁止把“安排上 / 解锁 / 诚意很足 / 实用又惊喜”等促销套话写成推荐表达。
- 如果人类意见不足以支持直接修改，只在 risk_notes 或 modify_suggestion 中提示，不要写入 patches。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 从全局视角说明原提示词的主要问题。
- modify_suggestion: 具体整理策略，说明应该删什么、合并什么、保留什么。
- added_content: 建议新增到原提示词里的内容，只写新增片段；如果没有新增则返回空字符串。
- removed_content: 建议删除或弱化的原文片段摘要；如果没有删除则返回空字符串。
- patches: 数组，给出可直接人工替换的修改块。每个元素必须包含 operation、old_text、new_text、reason。
  - operation 只能是 replace、delete、insert_after、insert_before 之一。
  - old_text 必须是原提示词中可以直接搜索定位的连续原文片段；如果是新增，请填写插入位置附近的原文锚点。
  - new_text 是替换后或新增后的内容；如果是删除则返回空字符串。
  - reason 用一句话说明这条 patch 如何解决重复、矛盾、冗长或优先级问题。
- revised_prompt: 默认返回空字符串，不要输出完整修改后提示词，避免超长截断。
- risk_notes: 说明本次整理可能影响的约束或需要人工复核的点；如果没有则返回空字符串。
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度。
"""


CRITIC_PATCH_SYSTEM_PROMPT = """你是一个资深内容审核规则与提示词优化专家。
你需要根据原始审核提示词、被审核内容和人类指出的问题，反推出审核提示词设计上的缺陷，并给出可执行的修改方案。

优化原则：
- 优先修正审核边界、证据要求、误判/漏判防护，不要改写成生文提示词。
- 只提出能被“内容 + 人类问题”直接支持的最小必要修改。
- 如果问题是误判，重点收窄规则、增加证据要求或排除合理语境。
- 如果问题是漏判，重点补充必要判定条件和可验证证据。
- 同一个根因只能输出一个最小 patch，不要重复表达同一修改意图。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 原审核提示词的问题在哪里
- modify_suggestion: 应该怎么修改，要求具体可执行
- added_content: 建议新增到原审核提示词里的内容，只写新增片段；如果没有新增则返回空字符串
- removed_content: 建议从原审核提示词中删除或弱化的内容，只写删除片段；如果没有删除则返回空字符串
- patches: 数组，给出可直接人工替换的修改块。每个元素必须包含 operation、old_text、new_text、reason。
- revised_prompt: 默认返回空字符串，不要输出完整修改后提示词，避免超长截断
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度
"""


class PromptOptimizerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_prompts(self, *, prompt_type: Optional[str] = None, skip: int = 0, limit: int = 50) -> list[PromptAsset]:
        stmt = select(PromptAsset).where(PromptAsset.is_deleted == 0)
        if prompt_type:
            stmt = stmt.where(PromptAsset.prompt_type == prompt_type)
        stmt = stmt.order_by(PromptAsset.update_time.desc(), PromptAsset.id.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_prompt(self, prompt_id: int) -> Optional[PromptAsset]:
        result = await self.db.execute(
            select(PromptAsset).where(PromptAsset.id == prompt_id, PromptAsset.is_deleted == 0)
        )
        return result.scalar_one_or_none()

    async def get_version(self, version_id: int) -> Optional[PromptVersion]:
        result = await self.db.execute(select(PromptVersion).where(PromptVersion.id == version_id))
        return result.scalar_one_or_none()

    async def list_versions(self, prompt_id: int) -> list[PromptVersion]:
        result = await self.db.execute(
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt_id)
            .order_by(PromptVersion.version_no.desc(), PromptVersion.id.desc())
        )
        return list(result.scalars().all())

    async def create_prompt(self, data: PromptAssetCreate) -> tuple[PromptAsset, PromptVersion]:
        prompt = PromptAsset(
            tenant_code=data.tenant_code,
            name=data.name,
            prompt_type=data.prompt_type,
            description=data.description,
            tags=data.tags,
        )
        self.db.add(prompt)
        await self.db.flush()

        version = PromptVersion(
            prompt_id=prompt.id,
            version_no=1,
            content=data.content,
            change_summary="初始版本",
            created_by=data.created_by,
        )
        self.db.add(version)
        await self.db.flush()
        prompt.current_version_id = version.id
        await self.db.commit()
        await self.db.refresh(prompt)
        await self.db.refresh(version)
        return prompt, version

    async def update_prompt(self, prompt_id: int, data: PromptAssetUpdate) -> Optional[PromptAsset]:
        prompt = await self.get_prompt(prompt_id)
        if not prompt:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(prompt, key, value)
        await self.db.commit()
        await self.db.refresh(prompt)
        return prompt

    async def create_version(self, prompt_id: int, data: PromptVersionCreate) -> PromptVersion:
        prompt = await self.get_prompt(prompt_id)
        if not prompt:
            raise ValueError("提示词不存在")

        result = await self.db.execute(
            select(func.max(PromptVersion.version_no)).where(PromptVersion.prompt_id == prompt_id)
        )
        next_version_no = (result.scalar_one_or_none() or 0) + 1
        version = PromptVersion(
            prompt_id=prompt_id,
            version_no=next_version_no,
            content=data.content,
            parent_version_id=data.parent_version_id,
            source_run_id=data.source_run_id,
            change_summary=data.change_summary,
            created_by=data.created_by,
        )
        self.db.add(version)
        await self.db.flush()
        if data.set_current:
            prompt.current_version_id = version.id
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def create_run(self, request: PromptOptimizerRunCreate) -> PromptOptimizerRun:
        prompt, version = await self._resolve_prompt_and_version(request)
        issue = PromptIssue(
            prompt_id=prompt.id,
            prompt_version_id=version.id,
            issue_type=request.issue_type or self._default_issue_type(request.mode),
            problem_text=request.problem_text,
            generated_content=request.generated_content,
            generated_title=request.generated_title,
            issue_metadata=request.issue_metadata,
        )
        self.db.add(issue)
        await self.db.flush()

        model = request.model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
        base_url = request.base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("AIHUBMIX_API_URL") or DEFAULT_BASE_URL
        input_snapshot = self._build_input_snapshot(request, version.content, model, base_url)
        run = PromptOptimizerRun(
            prompt_id=prompt.id,
            prompt_version_id=version.id,
            issue_id=issue.id,
            mode=request.mode,
            model=model,
            base_url=self._mask_url(base_url),
            temperature=str(request.temperature),
            max_tokens=request.max_tokens,
            status="running",
            input_snapshot=input_snapshot,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        try:
            system_prompt, user_prompt = self._build_optimizer_messages(
                mode=request.mode,
                prompt=version.content,
                problem=request.problem_text,
                generated_content=request.generated_content,
                generated_title=request.generated_title,
                include_revised_prompt=request.include_revised_prompt,
            )
            raw_output = await self._call_openai_compatible(
                api_key=request.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("AIHUBMIX_API_KEY") or "",
                base_url=base_url,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout=request.timeout,
                json_mode=request.json_mode,
            )
            run.raw_output = raw_output
            parsed = self._normalize_result(self._extract_json_object(raw_output))
            run.parsed_output = parsed
            run.status = "succeeded"
            await self._create_patches(run.id, parsed.get("patches") or [])
            await self.db.commit()
            await self.db.refresh(run)
        except Exception as exc:
            run.status = "failed"
            run.error_message = f"{type(exc).__name__}: {exc}"
            await self.db.commit()
            await self.db.refresh(run)

        return run

    async def get_run(self, run_id: int) -> Optional[PromptOptimizerRun]:
        result = await self.db.execute(select(PromptOptimizerRun).where(PromptOptimizerRun.id == run_id))
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        *,
        prompt_id: Optional[int] = None,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[PromptOptimizerRun]:
        stmt = select(PromptOptimizerRun)
        if prompt_id:
            stmt = stmt.where(PromptOptimizerRun.prompt_id == prompt_id)
        if mode:
            stmt = stmt.where(PromptOptimizerRun.mode == mode)
        if status:
            stmt = stmt.where(PromptOptimizerRun.status == status)
        stmt = stmt.order_by(PromptOptimizerRun.id.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_patches(self, run_id: int) -> list[PromptPatch]:
        result = await self.db.execute(
            select(PromptPatch).where(PromptPatch.run_id == run_id).order_by(PromptPatch.patch_index)
        )
        return list(result.scalars().all())

    async def update_patch(self, patch_id: int, data: PromptPatchUpdate) -> Optional[PromptPatch]:
        result = await self.db.execute(select(PromptPatch).where(PromptPatch.id == patch_id))
        patch = result.scalar_one_or_none()
        if not patch:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(patch, key, value)
        await self.db.commit()
        await self.db.refresh(patch)
        return patch

    async def apply_patches(self, run_id: int, request: PromptPatchApplyRequest) -> PromptPatchApplyResponse:
        run = await self.get_run(run_id)
        if not run:
            raise ValueError("优化任务不存在")
        version = await self.get_version(run.prompt_version_id)
        if not version:
            raise ValueError("提示词版本不存在")

        patches = await self.list_patches(run_id)
        selected_ids = set(request.patch_ids or [])
        if selected_ids:
            patches = [patch for patch in patches if patch.id in selected_ids]
        else:
            patches = [patch for patch in patches if patch.status in ("accepted", "edited")]

        content = version.content
        applied: list[int] = []
        conflicts: list[PromptPatchApplyConflict] = []
        for patch in sorted(patches, key=lambda item: item.patch_index):
            new_content, error = self._apply_one_patch(content, patch)
            if error:
                conflicts.append(PromptPatchApplyConflict(patch_id=patch.id, reason=error))
                continue
            content = new_content
            applied.append(patch.id)

        new_version = None
        if request.save_version and applied:
            new_version_model = await self.create_version(
                run.prompt_id,
                PromptVersionCreate(
                    content=content,
                    parent_version_id=version.id,
                    source_run_id=run.id,
                    change_summary=request.change_summary or "应用提示词优化 patches",
                    created_by=request.created_by,
                    set_current=True,
                ),
            )
            new_version = PromptVersionResponse.model_validate(new_version_model)

        return PromptPatchApplyResponse(
            applied_patch_ids=applied,
            conflicts=conflicts,
            candidate_content=content,
            new_version=new_version,
        )

    async def _resolve_prompt_and_version(self, request: PromptOptimizerRunCreate) -> tuple[PromptAsset, PromptVersion]:
        if request.prompt_version_id:
            version = await self.get_version(request.prompt_version_id)
            if not version:
                raise ValueError("prompt_version_id 不存在")
            prompt = await self.get_prompt(version.prompt_id)
            if not prompt:
                raise ValueError("prompt_id 不存在或已删除")
            return prompt, version

        if request.prompt_id:
            prompt = await self.get_prompt(request.prompt_id)
            if not prompt:
                raise ValueError("prompt_id 不存在或已删除")
            version_id = prompt.current_version_id
            if not version_id:
                raise ValueError("提示词没有 current_version_id")
            version = await self.get_version(version_id)
            if not version:
                raise ValueError("current_version_id 不存在")
            return prompt, version

        if not request.prompt_content:
            raise ValueError("必须传入 prompt_version_id、prompt_id 或 prompt_content")

        prompt_name = request.prompt_name or "临时提示词"
        return await self.create_prompt(
            PromptAssetCreate(
                name=prompt_name,
                content=request.prompt_content,
                prompt_type=request.prompt_type,
                tenant_code=request.tenant_code,
                description="通过提示词优化工作台自动创建",
            )
        )

    async def _create_patches(self, run_id: int, patches: list[Any]) -> None:
        for index, item in enumerate(patches, start=1):
            if not isinstance(item, dict):
                continue
            operation = str(item.get("operation") or "").strip()
            old_text = str(item.get("old_text") or "").strip()
            if operation not in {"replace", "delete", "insert_after", "insert_before"} or not old_text:
                continue
            patch = PromptPatch(
                run_id=run_id,
                patch_index=index,
                operation=operation,
                old_text=old_text,
                new_text=str(item.get("new_text") or ""),
                reason=str(item.get("reason") or ""),
                status="pending",
            )
            self.db.add(patch)

    def _build_optimizer_messages(
        self,
        *,
        mode: str,
        prompt: str,
        problem: str,
        generated_content: Optional[str],
        generated_title: Optional[str],
        include_revised_prompt: bool,
    ) -> tuple[str, str]:
        if mode == "global_refactor":
            system_prompt = GLOBAL_REFACTOR_SYSTEM_PROMPT
            user_prompt = (
                "# 背景信息\n"
                f"## 原始提示词:\n{prompt}\n\n"
                f"## 人类优化意见 / 问题描述:\n{problem}\n\n"
                "# 你的任务\n"
                "请直接根据人类意见，从全局视角优化这份提示词。\n"
                "重点检查重复、矛盾、冗长、规则散落、优先级不清、示例污染和局部规则覆盖全局规则等问题。"
            )
        elif mode == "critic_patch":
            system_prompt = CRITIC_PATCH_SYSTEM_PROMPT
            user_prompt = (
                "# 背景信息\n"
                f"## 原始审核提示词:\n{prompt}\n\n"
                f"## 被审核内容:\n{generated_content or ''}\n\n"
                f"## 人类指出的问题:\n{problem}\n\n"
                "# 你的任务\n输出审核提示词的问题在哪里，怎么修改。"
            )
        else:
            system_prompt = LOCAL_PATCH_SYSTEM_PROMPT
            title_block = f"\n## 生成的标题：\n{generated_title}\n" if generated_title else ""
            user_prompt = (
                "# 背景信息\n"
                f"## 生文用到的提示词:\n{prompt}\n"
                f"{title_block}\n"
                f"## 生成的内容：\n{generated_content or ''}\n\n"
                f"## 运营审查发现的问题：\n{problem}\n\n"
                "# 你的任务\n输出生文提示词的问题在哪里，怎么修改。"
            )

        if include_revised_prompt:
            user_prompt += "\n\n# 输出要求补充\n可以输出完整 revised_prompt，但必须保证 JSON 完整闭合。同时必须输出 patches 数组，便于人工定位替换。"
        else:
            user_prompt += (
                "\n\n# 输出要求补充\n"
                "不要输出完整 revised_prompt，请将 revised_prompt 返回为空字符串。"
                "请重点输出 patches 数组，便于人工按 old_text 搜索定位并替换。"
                "如果不能找到可直接搜索的原文片段，不要编造 old_text，请选择最接近的原文锚点并使用 insert_after 或 insert_before。"
                "输出 patches 前先做一次去重检查：同一根因、同一修改意图只保留一个 patch。"
            )
        return system_prompt, user_prompt

    async def _call_openai_compatible(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        timeout: int,
        json_mode: bool,
    ) -> str:
        if not api_key:
            raise ValueError("未配置 API Key，请设置 OPENAI_API_KEY / AIHUBMIX_API_KEY，或在请求中传入 api_key")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        token_param = "max_completion_tokens" if model.lower().startswith("gpt-5") else "max_tokens"
        payload[token_param] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._normalize_chat_completions_url(base_url),
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                raise ValueError(f"HTTP {response.status_code}: {detail}") from exc
            result = response.json()
        choices = result.get("choices") or [{}]
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            usage = json.dumps(result.get("usage") or {}, ensure_ascii=False)
            finish_reason = choice.get("finish_reason") or "unknown"
            raise ValueError(
                "模型返回了空 content，无法解析 JSON。"
                f"finish_reason={finish_reason}，usage={usage}。"
                "如果 finish_reason=length 且 reasoning_tokens 接近 max_tokens，"
                "请提高 max_tokens，或缩短输入提示词。",
            )
        return content

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if not match:
                raise
            value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise ValueError("模型输出不是 JSON object")
        return value

    @staticmethod
    def _normalize_result(parsed: dict[str, Any]) -> dict[str, Any]:
        parsed.setdefault("prompt_issue", "")
        parsed.setdefault("modify_suggestion", "")
        parsed.setdefault("added_content", "")
        parsed.setdefault("removed_content", "")
        parsed.setdefault("revised_prompt", "")
        parsed.setdefault("risk_notes", "")
        parsed.setdefault("confidence", "")
        if not isinstance(parsed.get("patches"), list):
            parsed["patches"] = []
        return parsed

    @staticmethod
    def _normalize_chat_completions_url(url: str) -> str:
        value = (url or "").strip().rstrip("/")
        if value.endswith("/chat/completions"):
            return value
        if value.endswith("/v1"):
            return f"{value}/chat/completions"
        return value

    @staticmethod
    def _default_issue_type(mode: str) -> str:
        if mode == "global_refactor":
            return "human_opinion"
        if mode == "batch_patch":
            return "batch_case"
        return "review_problem"

    @staticmethod
    def _mask_url(url: str) -> str:
        return (url or "").strip()

    def _build_input_snapshot(
        self,
        request: PromptOptimizerRunCreate,
        prompt_content: str,
        model: str,
        base_url: str,
    ) -> dict[str, Any]:
        return {
            "mode": request.mode,
            "prompt_content": prompt_content,
            "problem_text": request.problem_text,
            "generated_title": request.generated_title,
            "generated_content": request.generated_content,
            "issue_metadata": request.issue_metadata,
            "model_params": {
                "model": model,
                "base_url": self._mask_url(base_url),
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "timeout": request.timeout,
                "json_mode": request.json_mode,
            },
        }

    @staticmethod
    def _apply_one_patch(content: str, patch: PromptPatch) -> tuple[str, Optional[str]]:
        old_text = patch.old_text or ""
        replacement = patch.edited_new_text if patch.status == "edited" else patch.new_text
        replacement = replacement or ""
        occurrences = content.count(old_text)
        if occurrences == 0:
            return content, "old_text/锚点未命中"
        if occurrences > 1:
            return content, "old_text/锚点命中多次，需要人工处理"

        if patch.operation == "replace":
            return content.replace(old_text, replacement, 1), None
        if patch.operation == "delete":
            return content.replace(old_text, "", 1), None
        if patch.operation == "insert_after":
            return content.replace(old_text, f"{old_text}{replacement}", 1), None
        if patch.operation == "insert_before":
            return content.replace(old_text, f"{replacement}{old_text}", 1), None
        return content, f"不支持的 operation: {patch.operation}"
