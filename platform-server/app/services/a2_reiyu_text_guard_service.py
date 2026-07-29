"""Deterministic brand-case and fabricated-reward guard for a2 礼遇 articles."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


A2_REIYU_ARTICLE_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"

_SENTENCE_SPLIT_RE = re.compile(r"[\n。！？!?；;]+")
_UPPERCASE_BRAND_RE = re.compile(r"A2(?!\s*蛋白)")
_FABRICATED_LOTTERY_WIN_RE = re.compile(
    r"(?:(?:我|本人|这次|居然|竟然|真的|还真|直接)[^，。！？；;\n]{0,6}(?:中奖(?:了)?|中了奖))"
    r"|(?:中奖(?:了|啦|咯|耶)|中了奖)"
    r"|(?:抽中|抽到|中了)[^，。！？；;\n]{0,16}"
    r"(?:旅游|基金|新西兰|手链|手串|夏凉被|奖品|大奖)"
    r"|(?:拿到|领到|收到|获得)[^，。！？；;\n]{0,10}"
    r"(?:旅游基金|新西兰旅游|金手链|黄金手串|夏凉被)"
    r"|(?:旅游基金|新西兰旅游|金手链|黄金手串|夏凉被|[^，。！？；;\n]{0,8}大奖)"
    r"[^，。！？；;\n]{0,8}(?:抽中|抽到|中了|中奖|拿到|领到|收到|获得)"
)
_NON_CLAIMED_LOTTERY_WIN_RE = re.compile(
    r"(?:要是|如果|假如|万一)[^，。！？；;\n]{0,12}(?:中奖|中了奖|抽中|抽到)"
    r"|(?:希望|想|想要|盼着)[^，。！？；;\n]{0,8}(?:中奖|中了奖|抽中|抽到)"
    r"|(?:没|没有|还没|没能|未)[^，。！？；;\n]{0,4}(?:中奖|中了奖|抽中|抽到)"
    r"|(?:听说|听人说|别人|朋友|有人)[^，。！？；;\n]{0,12}(?:中奖|中了奖|抽中|抽到)"
)
_PROMPT_INSTRUCTION_LEAK_RE = re.compile(
    r"(?:再另起一段|最后自然表达|直接说a2|不要用品牌指代|禁止讲在|本条主活动是|"
    r"只输出\s*JSON|正文必须|标题和正文只能)"
)
_BIRTH_PRODUCT_CONTINUITY_RE = re.compile(
    r"(?:从|打从|自)(?:宝宝|宝|娃|小宝)?出生(?:起|开始|以后|后|就)?"
    r"(?:[^，。！？；;\n]{0,16}(?:喝(?:的)?(?:a2|至初)|喝(?:的)?(?:这个|这款|它))"
    r"|[^，。！？；;\n]{0,8}(?:就)?一直喝)"
)
_TRANSFER_HISTORY_RE = re.compile(r"转奶")
_MALFORMED_TEXT_PATTERNS = (
    re.compile(r"我(?:反正)?是值得(?:长期)?回购(?:了)?"),
    re.compile(r"品实用价值感在线"),
    re.compile(r"我自己喝下来(?:的)?(?:感受|感觉)"),
    re.compile(r"老客回去(?:就)?能领"),
)
_CORPORATE_SUMMARY_PATTERNS = (
    re.compile(
        r"(?:品牌|a2|他们?)?[^，。！？；;\n]{0,8}(?:想|想要|是想|为了)"
        r"(?:把|让)?(?:我们这些)?(?:老顾客|老用户|用户)"
        r"[^，。！？；;\n]{0,6}(?:留下来|留住)"
    ),
)
_TWELVE_CAN_EXCHANGE_RE = re.compile(
    r"(?:(?:集|攒|凑)(?:满|够)?|满)?\s*(?:12|十二)\s*(?:个)?罐"
    r"[^。！？\n]{0,16}(?:换|兑)[^。！？\n]{0,8}(?:1|一)?\s*罐"
)
_ONE_BOX_TWELVE_CAN_EQUIVALENCE_RE = re.compile(
    r"(?:一箱|整箱)[^，。！？；;\n]{0,10}"
    r"(?:"
    r"(?:差不多|基本|正好|刚好)(?:就)?够"
    r"|就(?:差不多)?够"
    r"|刚好(?:是)?(?:12|十二)罐"
    r"|(?:差不多|大概|约)(?:就是|是|有)?(?:12|十二)罐"
    r"|能(?:凑|集)(?:够|满)(?:12|十二)罐"
    r")"
    r"(?:了|啦|吧)?(?=[，。！？；;\n]|$)"
)
_UNSUPPORTED_ACTIVITY_BENEFIT_RE = re.compile(
    r"(?:积分(?:翻倍|加倍)|(?:双倍|翻倍|加倍)积分|(?:会员)?专属(?:赠品|礼品|礼物))"
)
_POSITIVE_EXPRESSION_PATTERNS = (
    re.compile(r"(?:品控|品质)(?:这块)?(?:挺|很|真)?在线"),
    re.compile(r"(?:质量|表现)(?:很|挺|真)?稳定"),
    re.compile(r"标准(?:很|挺|真)?高"),
    re.compile(r"细节(?:也|很|挺|真)?到位"),
    re.compile(r"(?:做得|做事)(?:很|挺|真)?认真"),
    re.compile(r"诚意(?:很|挺|真)?满满"),
    re.compile(r"(?:品质(?:更|很|挺)?透明|透明放心)"),
    re.compile(r"让人信服"),
    re.compile(r"经得起(?:考验|比较|研究)"),
    re.compile(r"(?:安心|放心|让人放心)"),
    re.compile(r"踏实"),
    re.compile(r"靠谱"),
    re.compile(r"值得信赖"),
    re.compile(r"心里有(?:底|数)"),
    re.compile(r"有保障"),
    re.compile(r"有底气"),
    re.compile(r"粉质(?:特别|很|挺|真)?细腻"),
    re.compile(r"(?:好冲泡|好冲开|冲泡顺滑)"),
    re.compile(r"不挂壁"),
    re.compile(r"不结块"),
    re.compile(r"(?:淡淡奶香|奶香自然)"),
    re.compile(r"(?:口感清淡|清淡不腥)"),
    re.compile(r"不甜腻"),
    re.compile(r"宝宝[^，。！？；;\n]{0,12}(?:爱喝|喝光|不抗拒|不挑嘴)"),
    re.compile(r"(?:转奶顺利|平稳过渡|转奶成功|无缝衔接)"),
)
_POSITIVE_EXPRESSION_STACK_THRESHOLD = 6
_POSITIVE_EXPRESSION_WINDOW_THRESHOLD = 8
_POSITIVE_EXPRESSION_WINDOW_SIZE = 3


@dataclass(frozen=True)
class A2ReiyuTextGuardReview:
    pass_: bool
    severity: str
    business_usability_tier: str
    issue_code: str | None
    hits: list[str]
    reason: str
    rewrite_required: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "rewrite_required": self.rewrite_required,
            "severity": self.severity,
            "business_usability_tier": self.business_usability_tier,
            "issue_code": self.issue_code,
            "hits": self.hits,
            "reason": self.reason,
        }


def review_a2_reiyu_text_surface(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any] | None,
) -> A2ReiyuTextGuardReview:
    if str((plan or {}).get("asset_key") or "") != A2_REIYU_ARTICLE_ASSET_KEY:
        return _pass_review()

    text = f"{title or ''}\n{body or ''}"
    sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(text) if sentence.strip()]
    reward_hits = [
        sentence
        for sentence in sentences
        if _FABRICATED_LOTTERY_WIN_RE.search(sentence)
        and not _NON_CLAIMED_LOTTERY_WIN_RE.search(sentence)
    ]
    if reward_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="hard",
            business_usability_tier="hold_out",
            issue_code="fabricated_reward_experience",
            hits=list(dict.fromkeys(reward_hits)),
            reason="正文或标题写成自己已经抽中或拿到抽奖奖品。",
        )

    brand_case_hits = [sentence for sentence in sentences if _UPPERCASE_BRAND_RE.search(sentence)]
    if brand_case_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="hard",
            business_usability_tier="hold_out",
            issue_code="brand_case_error",
            hits=list(dict.fromkeys(brand_case_hits)),
            reason="品牌a2或产品a2至初被写成大写A2；A2蛋白成分写法不受影响。",
        )

    if _TWELVE_CAN_EXCHANGE_RE.search(text) and _ONE_BOX_TWELVE_CAN_EQUIVALENCE_RE.search(text):
        quantity_hits = [
            sentence
            for sentence in sentences
            if _TWELVE_CAN_EXCHANGE_RE.search(sentence)
            or _ONE_BOX_TWELVE_CAN_EQUIVALENCE_RE.search(sentence)
        ]
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="hard",
            business_usability_tier="hold_out",
            issue_code="activity_quantity_error",
            hits=list(dict.fromkeys(quantity_hits)),
            reason="正文把一箱奶粉写成差不多等于12罐集罐门槛，这个数量关系没有活动素材承接。",
        )

    unsupported_benefit_hits = [
        sentence for sentence in sentences if _UNSUPPORTED_ACTIVITY_BENEFIT_RE.search(sentence)
    ]
    if unsupported_benefit_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="hard",
            business_usability_tier="hold_out",
            issue_code="fabricated_activity_benefit",
            hits=list(dict.fromkeys(unsupported_benefit_hits)),
            reason="正文自行补出了活动素材未提供的积分翻倍或专属赠品等具体福利。",
        )

    instruction_leak_hits = [sentence for sentence in sentences if _PROMPT_INSTRUCTION_LEAK_RE.search(sentence)]
    if instruction_leak_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="rewrite",
            business_usability_tier="light_fix_usable",
            issue_code="prompt_instruction_leakage",
            hits=list(dict.fromkeys(instruction_leak_hits)),
            reason="正文混入了生文或改写指令，需要删除指令文本并保留原有活动事实。",
            rewrite_required=True,
        )

    if _BIRTH_PRODUCT_CONTINUITY_RE.search(text) and _TRANSFER_HISTORY_RE.search(text):
        conflict_hits = [
            sentence
            for sentence in sentences
            if _BIRTH_PRODUCT_CONTINUITY_RE.search(sentence) or _TRANSFER_HISTORY_RE.search(sentence)
        ]
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="rewrite",
            business_usability_tier="light_fix_usable",
            issue_code="narrative_consistency",
            hits=list(dict.fromkeys(conflict_hits)),
            reason="正文同时写从出生就一直喝a2至初和后续转奶，使用经历冲突。",
            rewrite_required=True,
        )

    malformed_hits = [
        sentence
        for sentence in sentences
        if any(pattern.search(sentence) for pattern in _MALFORMED_TEXT_PATTERNS)
    ]
    if malformed_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="rewrite",
            business_usability_tier="light_fix_usable",
            issue_code="malformed_text",
            hits=list(dict.fromkeys(malformed_hits)),
            reason="正文存在明显病句或文本拼接损坏，需要局部改写后再入池。",
            rewrite_required=True,
        )

    corporate_summary_hits = [
        sentence
        for sentence in sentences
        if any(pattern.search(sentence) for pattern in _CORPORATE_SUMMARY_PATTERNS)
    ]
    if corporate_summary_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="rewrite",
            business_usability_tier="light_fix_usable",
            issue_code="corporate_summary_tone",
            hits=list(dict.fromkeys(corporate_summary_hits)),
            reason="正文站在品牌经营视角解释留住用户，需要改成消费者会说的自然感受。",
            rewrite_required=True,
        )

    body_sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(body or "") if sentence.strip()]
    positive_stack_hits = [
        sentence
        for sentence in body_sentences
        if len(_positive_expression_pattern_indexes(sentence)) >= _POSITIVE_EXPRESSION_STACK_THRESHOLD
    ]
    for start in range(len(body_sentences)):
        window = body_sentences[start : start + _POSITIVE_EXPRESSION_WINDOW_SIZE]
        if len(window) < 2:
            continue
        pattern_indexes = set().union(*(_positive_expression_pattern_indexes(sentence) for sentence in window))
        if len(pattern_indexes) >= _POSITIVE_EXPRESSION_WINDOW_THRESHOLD:
            positive_stack_hits.append("。".join(window))
    if positive_stack_hits:
        return A2ReiyuTextGuardReview(
            pass_=False,
            severity="rewrite",
            business_usability_tier="light_fix_usable",
            issue_code="positive_expression_stacking",
            hits=list(dict.fromkeys(positive_stack_hits)),
            reason="同一句连续堆叠过多正向评价，保留一两处最贴合上下文的表达即可。",
            rewrite_required=True,
        )

    return _pass_review()


def _positive_expression_pattern_indexes(text: str) -> set[int]:
    return {
        index
        for index, pattern in enumerate(_POSITIVE_EXPRESSION_PATTERNS)
        if pattern.search(text)
    }


def _pass_review() -> A2ReiyuTextGuardReview:
    return A2ReiyuTextGuardReview(
        pass_=True,
        severity="pass",
        business_usability_tier="direct_pool",
        issue_code=None,
        hits=[],
        reason="未发现品牌大小写错误、虚构抽奖中奖经历、活动数量或福利事实错误、经历冲突、文本损坏或连续正向词堆叠。",
    )
