"""Royal Friso UGC structure guard.

This guard catches business-risky structures that are too contextual for a
plain forbidden-word list: child self-handling formula, cup-as-milk quantity,
growth/nutrition attribution, sleep-result claims, and milk-residual claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


ROYAL_FRISO_ASSET_KEY = "royal_friso_ugc_post_rules_v1"


@dataclass(frozen=True)
class RoyalFrisoUGCStructureIssue:
    code: str
    evidence: str
    reason: str


@dataclass(frozen=True)
class RoyalFrisoUGCStructureReview:
    pass_: bool
    rewrite_required: bool
    issues: list[RoyalFrisoUGCStructureIssue]

    def model_dump(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pass"] = payload.pop("pass_")
        payload["reasons"] = [issue.code for issue in self.issues]
        payload["hits"] = [issue.evidence for issue in self.issues if issue.evidence]
        return payload


class RoyalFrisoUGCStructureGuardService:
    """Deterministic Royal Friso UGC post-structure review."""

    @staticmethod
    def applies_to(plan: dict[str, Any] | None) -> bool:
        return str((plan or {}).get("asset_key") or "") == ROYAL_FRISO_ASSET_KEY

    def review(
        self,
        *,
        title: str | None,
        body: str | None,
        plan: dict[str, Any] | None,
    ) -> RoyalFrisoUGCStructureReview | None:
        if not self.applies_to(plan):
            return None
        text = _normalize_text(f"{title or ''}\n{body or ''}")
        issues: list[RoyalFrisoUGCStructureIssue] = []
        _append_if_match(
            issues,
            code="child_self_handling_formula",
            reason="孩子自己拿、接、抱、放奶具，容易变成低龄自操作奶粉。",
            text=text,
            patterns=(
                r"接过.{0,8}(奶瓶|杯子|水杯)",
                r"递过去.{0,12}(接住|接过|拿住)",
                r"(接住|接过|拿住).{0,6}喝着",
                r"(自己|他|她|小家伙|娃|孩子|宝宝).{0,12}(跑去|主动|自己)?.{0,4}拿.{0,4}(奶瓶|杯子|水杯)",
                r"(自己|他|她|小家伙|娃|孩子|宝宝).{0,8}(拿着|抱着|捧着|端着|握着|攥着|抓着).{0,8}(奶瓶|杯子|水杯)",
                r"(他|她|小家伙|娃|孩子|宝宝).{0,8}手里.{0,8}(奶瓶|杯子|水杯|皇家美素佳儿)",
                r"(他|她|小家伙|娃|孩子|宝宝).{0,8}(放下|递过来).{0,4}(奶瓶|杯子|水杯)",
                r"把(奶瓶|杯子|水杯)递过来",
                r"(自己|他|她|小家伙|娃|孩子|宝宝).{0,24}(把)?(奶瓶|杯子|水杯|空瓶).{0,12}(放|递|搁|摆)",
                r"端起来就喝",
            ),
        )
        _append_if_match(
            issues,
            code="formula_container_form_error",
            reason="奶粉场景不能写成碗、水杯、杯子等错误奶具形态。",
            text=text,
            patterns=(
                r"(冲奶|喝奶|皇家美素佳儿|奶粉).{0,40}(碗|水杯|杯子).{0,12}(放|喝|接|递)",
                r"(碗|水杯|杯子).{0,12}(往床|往桌|喝着|这一顿)",
            ),
        )
        _append_if_match(
            issues,
            code="cup_quantity_for_formula",
            reason="奶量表达不能写成杯类量词，需要改成这顿/那顿。",
            text=text,
            patterns=(
                r"(喝|递|端|冲|泡|接)了?[一二两几0-9]+杯",
                r"[一二两几0-9]+杯奶",
                r"[一二两几0-9]+杯.{0,8}(递|端|喝|泡|冲)",
                r"(冲|泡)了?杯",
                r"(杯子|水杯).{0,10}(奶|喝)",
            ),
        )
        _append_if_match(
            issues,
            code="growth_or_nutrition_attribution",
            reason="成长、外观、营养或舒适感不能接成皇家美素佳儿的效果证明。",
            text=text,
            patterns=(
                r"营养跟不上",
                r"从断奶",
                r"(长高|又重|重了|脚长|长得真快|短了一截|穿不下|长肉|肉多|沉了|裤子都短|衣服.*小|衣服.*穿不下)",
                r"(气色|发干|奶养人|喝得舒服|喝着舒服)",
            ),
        )
        _append_if_match(
            issues,
            code="season_context",
            reason="皇家UGC当前内容不写季节、冷暖或天气节点。",
            text=text,
            patterns=(
                r"按季节",
                r"季节性",
                r"天气变化",
                r"(天冷|降温|着凉)",
            ),
        )
        _append_if_match(
            issues,
            code="current_negative_then_product",
            reason="不能用当前负面喂养状态开头后直接接皇家美素佳儿，容易变成产品负面语境。",
            text=text,
            patterns=(
                r"(下午|早上|午睡|这顿|那顿|最近|这段时间).{0,12}(磨蹭|费劲|不顺|折腾|哄半天).{0,24}皇家美素佳儿",
                r"皇家美素佳儿.{0,24}(磨蹭|费劲|不顺|(?<!没)折腾|哄半天)",
            ),
        )
        _append_if_match(
            issues,
            code="sleep_result_claim",
            reason="夜里内容只能写动作少一点，不能写产品后的睡眠结果。",
            text=text,
            patterns=(
                r"(直接|马上|翻身|自己|慢慢)?.{0,4}(睡着|睡过去|睡回笼|接着睡)",
                r"翻身就睡",
                r"安静了.{0,8}(睡|走开)",
                r"不用.{0,8}(哄睡|来回哄)",
            ),
        )
        _append_if_match(
            issues,
            code="milk_residual_or_drinking_claim",
            reason="不要把喝完、剩少、喝大半这类奶量残留写成改善证明。",
            text=text,
            patterns=(
                r"没怎么剩",
                r"剩下",
                r"喝了大半",
                r"边喝边",
                r"喝奶喝得认真",
            ),
        )
        _append_if_match(
            issues,
            code="negative_or_low_seed_tone",
            reason="语气不能变成拔草、嫌弃或低种草。",
            text=text,
            patterns=(r"懒得管", r"没一个省心", r"真不好弄", r"磨叽"),
        )
        return RoyalFrisoUGCStructureReview(
            pass_=not issues,
            rewrite_required=bool(issues),
            issues=issues,
        )


def royal_friso_structure_rewrite_instructions(review: RoyalFrisoUGCStructureReview) -> list[str]:
    issue_codes = {issue.code for issue in review.issues}
    instructions = [
        "只局部修正 Royal Friso UGC 结构问题，不要整篇重写成广告。",
        "保留皇家美素佳儿正文出现一次；产品仍是当前口粮或补货清单里的生活物件。",
        "改写后不要新增具体年龄、段数、专业成分、季节疾病、医疗诊断或新的产品事实。",
    ]
    if "child_self_handling_formula" in issue_codes:
        instructions.append(
            "删除孩子自己接过/拿着/抱着/递回奶瓶或杯子的动作；可改成大人喂完、这一顿喝着还顺，或直接删掉奶具动作。"
        )
    if "formula_container_form_error" in issue_codes:
        instructions.append("删除碗、水杯、杯子等错误奶具形态；奶粉相关动作只保留大人冲奶/喂完/收拾奶瓶，不能写孩子拿着容器喝。")
    if "cup_quantity_for_formula" in issue_codes:
        instructions.append("奶量一律改成这顿/那顿/这一顿，不用杯、杯奶、杯子来指代奶。")
    if "growth_or_nutrition_attribution" in issue_codes:
        instructions.append(
            "删除营养跟不上、断奶、长高长肉、气色、舒服、奶养人等效果归因；如果标题或开头是衣服小了、又长个、长高长肉，改成整理衣柜/换衣间隙/日常收纳这类中性入口，不保留尺码变小或成长变化。"
        )
    if "season_context" in issue_codes:
        instructions.append("删除按季节、季节性、天气变化、天冷、降温、着凉等时间/天气节点，改成普通收纳、进门、补货或带娃现场。")
    if "current_negative_then_product" in issue_codes:
        instructions.append("删除当前这顿磨蹭、费劲、不顺、折腾等负面开头；如需保留只能明确写成之前背景，皇家美素佳儿出现后只接轻正向或回到生活动作。")
    if "sleep_result_claim" in issue_codes:
        instructions.append("夜里场景只保留冲奶、拍嗝、抱一会儿、放回小床等动作；不要写睡着、接着睡、睡回笼或明显睡眠结果。")
    if "milk_residual_or_drinking_claim" in issue_codes:
        instructions.append("删除喝完、喝大半、没怎么剩、剩下、夸张喝光等奶量结果；可以轻写这一顿还顺。")
    if "negative_or_low_seed_tone" in issue_codes:
        instructions.append("删除嫌弃、拔草或低种草口吻，保留普通生活记录和轻正向口粮观察。")
    instructions.extend(
        [
            "优先删问题短句；只有语义断裂时补一句很短的生活动作。",
            "标题保持生活口吻，不写测评、攻略、推荐购买或产品总结。",
            "只输出 JSON：title, body。",
        ]
    )
    return instructions


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _append_if_match(
    issues: list[RoyalFrisoUGCStructureIssue],
    *,
    code: str,
    reason: str,
    text: str,
    patterns: tuple[str, ...],
) -> None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            issues.append(
                RoyalFrisoUGCStructureIssue(
                    code=code,
                    evidence=match.group(0),
                    reason=reason,
                )
            )
            return
