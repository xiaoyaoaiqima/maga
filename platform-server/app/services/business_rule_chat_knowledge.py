"""Business-rule knowledge injected into realtime Chat."""

from __future__ import annotations

from typing import Any

from app.schemas.chat import ChatContext


COMMENT_ANGLE_COPILOT_PROMPT = """
你现在是 MAGA 的评论切角 by-case 语料副驾，只服务当前选中的一条评论切角子方向。

工作方式：
- 必须基于页面传入的 asset_key、rule_id、source_row_no、comment_angle、正式语料、草稿语料、examples、supplements 和测试报告摘要回答。
- 只优化当前单条子方向，不扩展新子方向，不整包编辑；同名评论切角下可能有多个子方向，优先以 rule_id/source_row_no 为准。
- 优先改当前子方向的示例池和松规则，不把规则写成重审核清单。
- 草稿建议只用于前端填入文本框；保存草稿、试跑 10/50 条、发布新版本都必须让用户点击现有按钮完成。
- 不联网检索真人素材，不补充未出现在当前上下文里的品牌、剧情、竞品、功效、检测、活动机制等业务事实。

语料格式：
子方向标题：

像……。语气……。可以……，但别……。

示例：
- 真人感示例1
- 真人感示例2
- 真人感示例3
- 真人感示例4
- 真人感示例5

注意：示例只作为语义素材，不是正文原句，生成时换一种自然说法。

质量检查：
- 标题是否明确说明当前子方向在聊什么。
- 规则是否太硬，是否堆叠“必须/只写/可写方向/固定数字/生成重点”等词。
- 示例是否像真实评论区表达，是否有生活碎片、短问句、犹豫感、顺手聊天感。
- 示例句式是否重复，是否都沿着同一个开头和结构。
- 已购/未购、体验身份、宝宝阶段等身份边界是否一致。
- 过敏、生病、消化、长高长肉、检测等功效/医疗表达是否过确定。
""".strip()

LOOSENER_PROMPT = """
用户正在要求放松或修正 AI 味/同质化：
- 先指出硬规则、重复句式、生活感弱、边界过窄的位置。
- 把“必须/只写/可写方向/固定数字/生成重点”改成“像在聊/可以带一点/别都写成”。
- 保留必要合规边界，但写轻；不要为了放松删除身份或安全边界。
- 多样性优先靠示例横向扩展承担，不新增一串规则。
""".strip()


def is_comment_angle_context(context: ChatContext | None) -> bool:
    """Return whether the request should activate comment-angle copilot behavior."""

    if context is None:
        return False
    return context.page == "business_rules" and context.asset_type == "comment_angle_rule_set"


def should_inject_loosener(message: str) -> bool:
    """Detect user wording that asks for loosening a rigid corpus."""

    keywords = ("太硬", "同质", "AI味", "ai味", "太像AI", "太像 ai", "不真人", "死板", "放松", "模板")
    return any(keyword in message for keyword in keywords)


def build_business_rule_system_prompt(base_prompt: str, context: ChatContext | None, message: str) -> str:
    """Append business-rule copilot knowledge to the selected REALTIME_CHAT Agent prompt."""

    if not is_comment_angle_context(context):
        return base_prompt

    parts = [base_prompt.strip(), COMMENT_ANGLE_COPILOT_PROMPT]
    if should_inject_loosener(message):
        parts.append(LOOSENER_PROMPT)
    parts.append(
        """
如果你给出可直接填入草稿文本框的完整语料，请在回复最后追加一个 JSON fenced block：
```json
{"actions":[{"type":"fill_comment_angle_draft","label":"填入草稿","payload":{"draft_corpus":"完整草稿语料"}}]}
```
不要返回保存、试跑、发布等动作。
""".strip()
    )
    return "\n\n".join(part for part in parts if part)


def build_business_rule_context_block(context: ChatContext | None) -> str:
    """Serialize the current page state into a compact, auditable prompt block."""

    if not is_comment_angle_context(context):
        return ""

    lines = [
        "当前页面上下文：业务规则页 / 评论切角单条草稿 Drawer",
        f"asset_key: {_text(context.asset_key)}",
        f"asset_type: {_text(context.asset_type)}",
        f"asset_version: {_text(context.asset_version)}",
        f"rule_id: {_text(context.rule_id)}",
        f"source_row_no: {_text(context.source_row_no)}",
        f"comment_angle: {_text(context.comment_angle)}",
        "正式语料:",
        _text(context.corpus),
        "当前草稿语料:",
        _text(context.draft_corpus),
        "examples:",
        _list_block(context.examples),
        "supplements:",
        _list_block(context.supplements),
        "最近测试报告摘要:",
        _format_report_summary(context.test_report_summary),
    ]
    # 重要逻辑：副驾必须只看当前 rule_id/source_row_no，避免把同名评论切角下多个子方向混在一起。
    return "\n".join(lines)


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "-"


def _list_block(values: list[str]) -> str:
    cleaned = [str(item).strip() for item in values if str(item or "").strip()]
    if not cleaned:
        return "-"
    return "\n".join(f"- {item}" for item in cleaned[:12])


def _format_report_summary(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "-"
    lines = [
        f"batch_id: {_text(summary.get('batch_id'))}",
        f"batch_code: {_text(summary.get('batch_code'))}",
        f"status: {_text(summary.get('status'))}",
        f"generated_count: {_text(summary.get('generated_count'))}",
        f"failed_count: {_text(summary.get('failed_count'))}",
        f"risk_count: {_text(summary.get('risk_count'))}",
    ]
    samples = summary.get("samples")
    if isinstance(samples, list) and samples:
        lines.append("samples:")
        for item in samples[:5]:
            if isinstance(item, dict):
                body = _text(item.get("body"))
                risks = item.get("risks")
                risk_text = "、".join(str(risk) for risk in risks) if isinstance(risks, list) else _text(risks)
                lines.append(f"- #{_text(item.get('item_no'))} {body} 风险: {risk_text}")
    return "\n".join(lines)
