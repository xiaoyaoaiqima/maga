"""Focused LLM judge for Wangyue Chinese fluency and coherence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.focused_llm_judge_runtime import call_focused_judge, normalize_focused_judgment


FLUENCY_ISSUE_CODES = {
    "none",
    "unnatural_collocation",
    "semantic_discontinuity",
    "title_body_contradiction",
    "instruction_leak",
    "incomplete_sentence",
    "generic_but_readable",
}

FLUENCY_JUDGE_MODEL_CODE = "qwen-plus"


@dataclass(slots=True)
class WangyueFluencyJudgment:
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


class WangyueFluencyJudgeService:
    """Judge only whether title/body form coherent, understandable Chinese."""

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        model_config: dict[str, Any] | None = None,
    ) -> WangyueFluencyJudgment:
        call = await call_focused_judge(
            model_config=model_config,
            system_prompt=FLUENCY_SYSTEM_PROMPT,
            user_prompt=f"标题：{title or ''}\n正文：{body or ''}",
            issue_codes=FLUENCY_ISSUE_CODES,
            max_tokens=300,
        )
        judgment = parse_wangyue_fluency_judgment(call.raw_response)
        judgment.runtime_metadata = call.runtime_metadata
        return judgment


def parse_wangyue_fluency_judgment(raw_response: str) -> WangyueFluencyJudgment:
    label, issue_code, evidence = normalize_focused_judgment(
        raw_response,
        issue_codes=FLUENCY_ISSUE_CODES,
        fallback_issue_code="semantic_discontinuity",
    )
    return WangyueFluencyJudgment(
        label=label,
        issue_code=issue_code,
        evidence=evidence,
        raw_response=raw_response[:2000],
    )


FLUENCY_SYSTEM_PROMPT = """你只审核旺玥文章的中文流畅性：标题和正文是否是成立、可理解、前后连续的自然中文。你不审核产品事实、功效、时间逻辑、产品出现方式、内容方向、种草强弱，也不改写。

标签含义：
- pass：表达成立，无需因流畅性改写。
- watch：意思清楚但略泛或略生硬，单篇可用，不自动改写。
- block：存在病句、残句、语义断裂、标题正文冲突或指令泄露，需要局部说人话改写。

判断标准：
1. 只判断原句是否成立，不要替作者脑补意思。饭量不稳定、吃饭看心情可以 pass；“饭菜经常不稳定、饭菜吃得不稳”必须 block，unnatural_collocation。
2. semantic_discontinuity 只用于相邻句子无法组成可理解事件，例如缺主语、缺宾语、指代悬空或模型压缩后读不懂。真实 UGC 可以跳着写，不要求补齐旧状态、参照系、时间点或完整因果链。“放学回来照样能吃饭、玩会儿乐高”把两个动作压成不自然并列，可以 block；不能仅因为“照样”没有明确参照就 block。
3. “他整个人不会一下子就掉下去、状态不会一下掉下去”缺少可理解的状态落点，必须 block，unnatural_collocation。“之前时候交替、时候交替”也必须 block，unnatural_collocation。
4. 标题写当前负面状态，正文却写相反的正面状态，且没有以前/之前等阶段提示：block，title_body_contradiction。
5. 输出出现“你来发挥、本篇灵感线索、请继续写、具体怎么写”等生成指令或提示词残留：block，instruction_leak。
6. 句子停在“主要是看它、后来因为这个”等未完成关系，缺宾语或后文：block，incomplete_sentence。
7. 真实 UGC 可以口语化、有毛边。蔫蔫的、精神头足、省心——不对是开心、狗都嫌的年纪，都可以 pass。不要因为不正式、比喻化或带吐槽感而判差。
8. “保护力撑起来”和“保护屏障撑起来”是已经人工确认可用的口语化比喻。只要句子完整，必须 pass，不得因为比喻抽象或不够专业降为 watch。
9. 状态在线、家里安排没那么乱等表达如果意思清楚，pass 或 watch；标 watch 时用 generic_but_readable，不能自动 block。
10. 不要把内容适配问题当流畅性问题。“安排进日常奶粉里”由 content-fit Judge 处理；本 Judge 不重复审核产品出现自然度。
11. 不审核论证是否充分、功效因果是否成立、卖点是否有证据，也不要求标题里的每个概念都在正文逐项解释。状态比以前稳、长得快、小脸圆了、旺玥是日常营养补充等句子，只要读得懂就 pass 或 watch，不能因缺少参照数据或因果证明而 block。
12. 不要要求旺玥必须改善前文生活问题，也不要要求正文交代孩子何时实际喝下。正餐吃得少或饭量不稳之后写旺玥作为日常营养补充，只要句子通顺、意思清楚就 pass；不能因为没有解释如何改善食欲而判语义断裂。
13. 中文正文中用独立的 ta/Ta/TA 指代孩子或人物，属于中英文混写代词，必须 block，unnatural_collocation；不能因为网络上偶尔有人这样写就判 pass。

决策优先级：只有句子本身不成立、读不懂，或命中第3至第6条、第13条明确问题时才 block。逻辑不完整、因果偏松、参照不足都不是流畅性 block。第8条的人工通过判例优先于一般风格判断。watch 只用于第9条这类句子成立、意思清楚但略泛的表达。

issue_code 只能从以下值选择：none、unnatural_collocation、semantic_discontinuity、title_body_contradiction、instruction_leak、incomplete_sentence、generic_but_readable。label=pass 时 issue_code 必须是 none。

只输出 JSON object：{"label":"pass|watch|block","issue_code":"上述枚举之一","evidence":"原文证据"}。"""
