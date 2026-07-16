"""Focused LLM judge for Wangyue product and post-type fit."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.focused_llm_judge_runtime import call_focused_judge, normalize_focused_judgment


CONTENT_FIT_ISSUE_CODES = {
    "none",
    "abstract_brief_translation",
    "unnatural_product_appearance",
    "post_type_mismatch",
    "ad_like_closure",
}
CONTENT_FIT_MODEL_CODE = "deepseek-v4-flash"
CONTENT_FIT_MAX_TOKENS = 800


@dataclass(slots=True)
class WangyueContentFitJudgment:
    label: str
    issue_code: str
    evidence: str
    raw_response: str = ""
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "issue_code": self.issue_code,
            "evidence": self.evidence,
        }


class WangyueContentFitJudgeService:
    """Judge only whether product entry and requested post type feel coherent."""

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        post_type: str | None,
        model_config: dict[str, Any] | None = None,
    ) -> WangyueContentFitJudgment:
        user_prompt = (
            f"目标帖子类型：{post_type or '未指定'}\n"
            f"标题：{title or ''}\n"
            f"正文：{body or ''}"
        )
        call = await call_focused_judge(
            model_config=model_config,
            system_prompt=CONTENT_FIT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            issue_codes=CONTENT_FIT_ISSUE_CODES,
            max_tokens=CONTENT_FIT_MAX_TOKENS,
        )
        judgment = parse_wangyue_content_fit_judgment(call.raw_response)
        judgment.runtime_metadata = call.runtime_metadata
        return judgment


def parse_wangyue_content_fit_judgment(raw_response: str) -> WangyueContentFitJudgment:
    label, issue_code, evidence = normalize_focused_judgment(
        raw_response,
        issue_codes=CONTENT_FIT_ISSUE_CODES,
        fallback_issue_code="unnatural_product_appearance",
    )
    return WangyueContentFitJudgment(
        label=label,
        issue_code=issue_code,
        evidence=evidence,
        raw_response=raw_response[:2000],
    )


CONTENT_FIT_SYSTEM_PROMPT = """你只审核旺玥文章的内容适配：产品是否自然进入帖子、是否把业务 brief 翻译成抽象妈妈话术、目标帖子类型是否真正成立。你不审核产品事实、疾病宣称、时间逻辑、病句、标题正文矛盾，也不改写。

标签含义：
- pass：无需因内容适配问题改写。
- watch：单篇可用，只观察批量分布，不自动改写。
- block：需要进入 content-fit/fluency 局部改写，不是合规 hard fail。

判断标准：
1. 具体说钙铁锌、DHA、燕窝酸、乳铁蛋白、HMO、配方表或自家反馈，可以 pass。不要因为种草价值强而判差。
2. “保护力方向我会看、这个点值得关注、产品依据我记住的是、营养这块要优先”等抽象选品总结成为主要承接：block，abstract_brief_translation。但正常选择动作不是抽象 brief 翻译：“孩子三岁后活动量大了，我重新看了儿童奶粉，后来选了旺玥。喝了一阵，日常状态还不错。”属于生活阶段触发、直接选择和使用反馈，必须 pass。不能仅因为出现“重新看奶粉、后来选了旺玥”就 block。
3. “把旺玥安排进/放进/加进日常奶粉里”这种产品关系表达必须 block，unnatural_product_appearance，不能因为后面有正向反馈而放过。“家里有这罐旺玥，日常安排会更好接上”缺少具体动作和用途，逻辑不通，也必须 block。最小 pass 对照：“孩子饭量不稳的时候，家里会正常冲一杯旺玥，就当补充一点日常营养。钙铁锌这些也都有。”动作和用途具体，应 pass。
4. “新罐开封/刚开新罐”本身可以是普通生活动作，不能仅凭开罐判问题。但只要同时出现“新罐开封/刚开新罐” + “顺手想/回看/复盘” + “为什么回购/为什么买/购买理由”，就是用开罐动作强行触发产品复盘，必须 block，unnatural_product_appearance；不能因为目标帖子类型是复购/长期使用或后面有正常反馈而放行。最小 pass 对照：“今天刚开一罐新的旺玥，大人照常冲好递给孩子”，没有借开罐复盘产品理由，应 pass。直接说这罐快空了又补一罐也可以 pass。
5. 目标帖子类型主要用于生成多样化和批量分布优化，不能把“类型没有充分展开”自动当成单篇 block。家庭清单只写旺玥、没有其它家庭物件或清单项时，只要正文自身自然、产品内容成立，应 pass 或 watch；标 watch 时可用 post_type_mismatch，但不自动改写。出现米、面、零食等其它清单项时可以直接 pass。求助后的回访只剩纯求助、导致内容任务本身不成立时仍可 block。复购/长期使用明确写到已喝两周或更久即可成立，不要求必须补货；低于两周且没有补货、复购或持续使用关系时才判 block。
6. 省心、踏实、安心、心里有数、选对、不用纠结等词，如果正文已有具体生活反馈，直接 pass，不要仅凭标题或结尾命中这些词标问题。只有正文主要靠这类泛情绪词收口、具体内容很弱时才 watch，ad_like_closure；仍然不能仅凭这些词 block。
7. 朋友问起、成分依据、多个自家反馈、孩子接受和继续使用可以构成完整强种草链。只要各节点自然成立，就必须 pass；不能仅因节点多、链路完整而标 watch 或 block。节点密度和同类链路占比属于批量治理，不是 Content Fit 问题。

issue_code 只能从以下值选择：none、abstract_brief_translation、unnatural_product_appearance、post_type_mismatch、ad_like_closure。label=pass 时 issue_code 必须是 none。

只输出 JSON object：{"label":"pass|watch|block","issue_code":"上述枚举之一","evidence":"原文证据"}。"""
