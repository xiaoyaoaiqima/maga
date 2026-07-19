"""Focused LLM judge for Wangyue temporal logic evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.focused_llm_judge_runtime import (
    call_focused_judge,
    has_valid_focused_judgment_contract,
    merge_focused_runtime_metadata,
    normalize_focused_judgment,
)


TEMPORAL_ISSUE_CODES = {
    "none",
    "same_period_state_contradiction",
    "immediate_rescue_causality",
    "insufficient_effect_duration",
    "publication_time_anchor",
    "mixed_state_same_period",
    "past_public_disease_reference",
    "short_period_hard_reversal",
    "missing_transition_duration",
    "decision_execution_stage_conflict",
    "recent_problem_long_usage_conflict",
    "continuous_use_baseline_conflict",
    "pre_usage_effect_evidence",
}
TEMPORAL_LOGIC_MODEL_CODE = "deepseek-v4-flash"
TEMPORAL_LOGIC_MAX_TOKENS = 800


@dataclass(slots=True)
class WangyueTemporalLogicJudgment:
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


class WangyueTemporalLogicJudgeService:
    """Judge timeline coherence inside the Wangyue focused-review pipeline."""

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        model_config: dict[str, Any] | None = None,
        review_date: date | None = None,
    ) -> WangyueTemporalLogicJudgment:
        effective_review_date = review_date or date.today()
        user_prompt = (
            f"审核日期：{effective_review_date.isoformat()}\n"
            f"标题：{title or ''}\n正文：{body or ''}"
        )
        call = await call_focused_judge(
            model_config=model_config,
            system_prompt=TEMPORAL_LOGIC_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            issue_codes=TEMPORAL_ISSUE_CODES,
            max_tokens=TEMPORAL_LOGIC_MAX_TOKENS,
        )
        judgment = parse_wangyue_temporal_logic_judgment(call.raw_response)
        judgment.runtime_metadata = call.runtime_metadata
        return judgment


def parse_wangyue_temporal_logic_judgment(raw_response: str) -> WangyueTemporalLogicJudgment:
    label, issue_code, evidence = normalize_focused_judgment(
        raw_response,
        issue_codes=TEMPORAL_ISSUE_CODES,
        fallback_issue_code="mixed_state_same_period",
    )
    return WangyueTemporalLogicJudgment(
        label=label,
        issue_code=issue_code,
        evidence=evidence,
        raw_response=raw_response[:2000],
    )


def _has_valid_judgment_contract(raw_response: str) -> bool:
    return has_valid_focused_judgment_contract(
        raw_response,
        issue_codes=TEMPORAL_ISSUE_CODES,
    )


def _merge_runtime_metadata(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return merge_focused_runtime_metadata(first, second)


TEMPORAL_LOGIC_SYSTEM_PROMPT = """你只审核旺玥文章的时间逻辑，不审核产品事实、违禁词、人味、种草强弱，也不改写。

这是严格的文章内部时间关系审核。只使用原文已经写出的时间、阶段、行为和结果，不替文章脑补适应过程、自然恢复或更早的发生时间。以下任一 block 规则命中时，不要因为“现实中也有可能”而放行。

判断标准：
1. 同一时间窗口同时写持续不好和持续稳定，且没有“以前/前段时间/前阵子/后来/换后”等阶段转换：block，same_period_state_contradiction。“这段时间他容易中招、三天两头不舒服”后又写“回看这段时间状态挺稳”，两处“这段时间”属于同一窗口，必须 block，不得降成 watch。“总是/一直/三天两头/频繁不舒服”属于持续负面；“好像特别容易中招”后面只要明确接“三天两头不舒服”，仍是持续负面，不得因为“好像”判成轻微波动。最小 pass 对照：如果前文明确改成“前段时间他容易中招”，后文写“家里现在喝旺玥，回看这段时间状态挺稳”，旧阶段与当前阶段已经分开，应 pass。
2. 单次打喷嚏、疾病症状后，只要立刻出现“马上换旺玥/赶紧补保护力/把保护力补回来”等产品补救行为或意图，就必须 block / immediate_rescue_causality；不要求原文已经宣称产品生效，“想着、打算、希望赶紧补回来”也属于即时补救意图，不得 pass。硬判组合：“昨天刚换/刚换一天/才喝一两次”后面用“今天就/马上/一下”承接“不请假、保护力稳住、状态稳定或产品生效”，明确表示产品在不超过一天或极短期内生效，必须 block / insufficient_effect_duration，不得判 watch。普通一顿饭没吃好后正常冲泡旺玥补充日常营养，不属于立即补救，必须 pass。
3. 昨晚、凌晨、当天、第二天、刚喝或才喝几次仍有严重问题，马上写彻底稳定、完全不闹或多方面明显变好，且没有合理观察跨度：block，short_period_hard_reversal。即使出现“后来”，也不能把几个小时或一两次使用写成累计效果。issue code 优先级：原文明确有“刚换/刚喝/才喝几次”并直接证明产品累计效果，但前面没有严重负面状态时，优先用 insufficient_effect_duration；只有前面已有严重负面、后面又短时间彻底反转时，才用 short_period_hard_reversal。
4. 只写问题状态，随后直接写奶量、便便、睡眠、精神等多方面明显改善，却没有换奶、适应、观察或时间跨度：block，missing_transition_duration。“后来”单独出现只表示叙述顺序，不等于改善过程或时间跨度，不能因此 pass。硬判示例：“前面还肚肚不舒服、喝奶不顺。后来奶量上来了、便便顺了、睡觉也好了。”必须 block。只有原文明写“适应了几天/观察了一个月/慢慢/逐渐”等过程才可以 pass。
5. “还在纠结/考虑/犹豫要不要换”表示尚未执行；同一当前阶段又写“已经换了/喝了一周/转奶后”：block，decision_execution_stage_conflict。“之前纠结过，后来换了”阶段清楚，可以 pass。
6. 时间词业务定义：“前阵子”固定表示距今15-45天，不得解释为45天以前或数月前。用“最近/前阵子/这段时间”描述当前或近期问题，随后写“后来换了旺玥，现在已经喝了几个月”，却没有说明问题实际发生在几个月前：block，recent_problem_long_usage_conflict。硬判示例：“前阵子还焦虑。后来换了旺玥，现在已经喝了四个月。”其中前阵子是15-45天，四个月约120天，换奶实际早于前阵子，无法由“后来”承接，必须 block。只有原文明写“几个月前/四个月前”等旧阶段才可以 pass。
7. 一边说“一直喝旺玥/从小一直喝”，一边用“现在不像以前那样/终于稳定了”暗示产品带来前后变化，却不解释以前属于刚开始、适应期或另一阶段：block，continuous_use_baseline_conflict。有明确阶段说明可以 pass。
8. 发布时间锚点是独立硬规则，不要求文章内部存在时间矛盾，也不判断审核当天是否真的处于对应季节或天气。只要正文用“现在/最近/目前”断言当前正值流感季、换季、入冬、降温等动态环境，就必须 block / publication_time_anchor。即使正文没有疾病、群体请假、产品效果、前后反转或其它时间矛盾，也不得 pass。硬判示例：“最近降温挺明显，我开始多留意孩子每天的状态。家里旺玥一直喝着，日常安排没怎么变。”必须 block / publication_time_anchor。旺玥内容中的“流感”另属于确定性硬禁词，正式硬审应直接 ban，不依赖 LLM；不含硬禁词时，明确过去式的季节或天气环境可以保留。
9. “偶尔/有点”这类局部小状况与整体状态稳定可以共存，但标 watch，mixed_state_same_period。
10. 过去的周围孩子生病只作背景、不依赖当前环境成立：pass 或 watch；没有公共疾病对照且时间阶段清楚、效果有观察跨度：pass。
11. 审核输入会提供明确的“审核日期”。如果文章写明产品已经使用的时长，又把早于产品开始使用时间的历史事件当作使用后的正面效果证据，必须 block / pre_usage_effect_evidence。必须根据审核日期、自然时间锚点和使用时长核对事件是否落在使用周期内。硬判示例：审核日期为2026-07-17，正文写“喝旺玥小半年”，却用“去年秋天孩子中招后两天就恢复”证明喝后的状态，去年秋天距今约9至10个月，早于最长约6个月的使用周期，必须 block。正常对照：“去年秋天总请假，今年开始喝旺玥，小半年回看下来最近状态稳了些”，去年秋天明确是使用前负面基线，当前状态才是使用后的观察，应 pass。不要因为两个阶段都写得清楚，就忽略历史效果证据发生在产品使用前。

issue_code 只能从以下值选择：none、same_period_state_contradiction、immediate_rescue_causality、insufficient_effect_duration、publication_time_anchor、mixed_state_same_period、past_public_disease_reference、short_period_hard_reversal、missing_transition_duration、decision_execution_stage_conflict、recent_problem_long_usage_conflict、continuous_use_baseline_conflict、pre_usage_effect_evidence。label=pass 时 issue_code 必须是 none。

只输出 JSON object：{"label":"pass|watch|block","issue_code":"上述枚举之一","evidence":"原文证据"}。"""
