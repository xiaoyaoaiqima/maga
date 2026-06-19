"""QA guard for repeated article business-rule phrase patterns."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SKELETON_PARTS: dict[str, tuple[str, ...]] = {
    "selection_process": (
        "纠结",
        "犹豫",
        "做功课",
        "翻成分表",
        "看成分表",
        "对比",
        "看评价",
        "问朋友",
        "问店员",
        "选奶",
        "换奶",
        "4段",
    ),
    "price": (
        "贵",
        "不便宜",
        "价格",
        "肉疼",
        "趁活动",
        "不算便宜",
        "闭眼买",
        "心疼",
    ),
    "kid_acceptance": (
        "愿意喝",
        "不排斥",
        "不抗拒",
        "接受",
        "喝完",
        "咕咚",
        "顺口",
        "口味",
        "主动要喝",
        "喝光",
    ),
    "ai_closure": (
        "省心",
        "踏实",
        "固定",
        "固定下来",
        "心里有数",
        "好执行",
        "省得",
        "先这样",
        "继续喝着",
        "不用额外操心",
    ),
}

AI_PHRASES = (
    "省心",
    "踏实",
    "固定下来",
    "这事先这么放着",
    "不用每天临时凑",
    "不用临时凑",
    "不用额外想一堆",
    "不用额外想",
    "孩子愿意喝就好执行",
    "早上冲得快",
    "价格不算友好",
    "心里有数",
    "安心",
    "老母亲",
    "神药",
    "收藏起来",
    "收藏",
    "没那么焦虑",
    "放进日常",
    "固定在日常",
)

STATE_TEMPLATE_PHRASES = (
    "精神头足",
    "精神头十足",
    "精神头一直在线",
    "精神头挺好",
    "精神抖擞",
    "精神满满",
    "精神好",
    "状态一直在线",
    "状态在线",
    "状态一直挺稳",
    "状态挺稳",
    "状态稳得很",
    "状态好",
    "胃口一直在线",
)

HARD_AI_CLOSURE_PHRASES = (
    "老母亲",
    "神药",
    "收藏起来",
    "收藏",
    "固定下来",
    "这事先这么放着",
)

COMMON_AI_CLOSURE_PHRASES = (
    "希望能一直这样省心",
    "一直这样省心",
    "继续观察看看，先这样喂着吧",
    "继续观察看看",
    "继续观察吧",
    "继续观察",
    "后续再观察看看",
    "先这样喝着看看",
    "先这样喝着",
    "先这样喂着吧",
    "先这样喂着",
    "先这么喂着",
    "就这样简单搞定",
    "简单搞定",
    "我也算松了口气",
    "松了口气",
    "暂时满意",
    "先这样记录一下",
    "老母亲",
)

COMMON_AI_CLOSURE_REPLACEMENTS = (
    ("希望能一直这样省心", "希望后面少折腾点"),
    ("一直这样省心", "后面少折腾点"),
    ("继续观察看看，先这样喂着吧", ""),
    ("继续观察看看", ""),
    ("继续观察吧", ""),
    ("继续观察", ""),
    ("后续再观察看看", ""),
    ("先这样喝着看看", ""),
    ("先这样喝着", ""),
    ("先这样喂着吧", ""),
    ("先这样喂着", ""),
    ("先这么喂着", ""),
    ("就这样简单搞定", "就行"),
    ("简单搞定", ""),
    ("我也算松了口气", ""),
    ("松了口气", ""),
    ("暂时满意", ""),
    ("先这样记录一下", "记一笔"),
    ("老母亲", "我"),
)

ODD_PHRASE_REPLACEMENTS = (
    ("体格挺打底", "体格看着挺扎实"),
    ("一杯下去又活过来了", "休息一会儿状态能缓过来"),
    ("也没有动不动就掉状态", "状态也还可以"),
    ("没有动不动就掉状态", "状态看着还可以"),
    ("动不动就掉状态", "状态不太稳"),
    ("营养保险", "日常营养补充"),
    ("缺这缺那", "营养不均衡"),
    ("缺啥补啥", "营养不均衡"),
    ("最近季", "最近"),
    ("先着吧", ""),
    ("我这我算是", ""),
    ("，效果", ""),
)

ODD_PHRASES = tuple(source for source, _replacement in ODD_PHRASE_REPLACEMENTS)

STRONG_REAL_PHRASES = (
    "没再半夜闹腾",
    "不容易中招",
    "精力恢复得快",
    "一直挺稳",
    "可能跟每天那杯旺玥有关系",
    "可能跟每天那杯有关系",
    "坐不住",
    "坐不久",
    "少请假",
    "长个",
    "窜个",
    "抵抗力",
)

HARD_RISK_PHRASES = (
    "保证长高",
    "一定长高",
    "喝了就不生病",
    "不生病了",
    "再也不生病",
    "提高免疫力",
    "增强免疫力",
    "免疫力提高",
    "治疗",
    "改善乳糖不耐受",
    "乳糖不耐受好转",
    "专注力提升",
    "专注力变好",
    "防风全靠",
    "全靠它",
    "全靠旺玥",
    "没白养",
    "没白选",
    "保护力确实",
    "赶紧把旺玥安排上",
    "赶紧安排上",
    "临时补救",
)

ADULT_SELF_DRINKING_PHRASES = (
    "给自己冲了一杯",
    "给自己冲一杯",
    "自己冲了一杯",
    "自己冲一杯",
    "给自己泡了一杯",
    "给自己泡一杯",
    "我喝了一杯旺玥",
    "我也喝旺玥",
    "妈妈自己喝旺玥",
    "我自己也能当早餐奶",
    "自己也能当早餐奶",
    "我自己喝着觉得挺香",
    "自己先喝了一口",
)

CHILD_SELF_BREWING_PHRASES = (
    "每天主动要泡",
    "主动去泡奶喝",
    "自己主动冲奶",
    "自己主动泡奶",
    "自己主动冲",
    "自己主动泡",
    "自己冲旺玥",
    "自己泡旺玥",
    "自己开罐旺玥泡一杯",
    "孩子自己倒水舀粉",
    "娃自己倒水舀粉",
    "自己倒水舀奶粉",
    "自己倒水舀粉",
    "自己舀粉冲奶",
    "自己舀奶粉",
    "自己拿勺子舀了三勺",
    "自己拿勺子舀",
    "自己搬小凳子冲奶",
    "自己洗完澡就去厨房泡旺玥",
    "自己拿勺子挖了两勺",
    "自己偷偷多舀了一勺",
    "自己搬奶粉罐去了",
    "自己搬奶粉罐",
    "自己开柜门拿奶粉罐",
    "开柜门拿奶粉罐",
    "踮脚够奶粉罐",
    "蹬着小凳子去够奶粉罐",
    "自己搬凳子去够柜子上的罐子",
    "搬凳子去够柜子上的罐子",
    "自己搬凳子去够罐子",
    "搬凳子去够罐子",
    "去够奶粉罐",
    "够奶粉罐",
    "去够柜子上的罐子",
    "够柜子上的罐子",
    "抱着空罐子在地上滚",
    "抱着空罐子",
    "扛奶粉",
    "自己主动去冲",
    "主动去倒奶喝",
    "自己到点就去泡一杯",
    "娃自己会去冲",
    "孩子自己会去冲",
    "自己会去冲",
    "自己跑去冲一杯",
    "自己去冲",
    "主动去冲",
    "每天早上主动去冲",
    "每天早上自己跑去冲一杯",
    "自己抱着杯子要冲",
    "自己抱着罐子让冲",
    "他泡好端着",
    "拿勺子舀粉",
    "拿勺子舀奶粉",
    "拿勺子挖奶粉",
    "自己冲杯旺玥",
    "自己冲一杯旺玥",
    "自己泡一杯旺玥",
    "自己冲奶",
    "自己泡奶",
    "主动冲奶",
    "主动泡奶",
    "主动要泡",
)

CHILD_FORMULA_BOTTLE_PHRASES = (
    "抱着奶瓶",
    "奶瓶一递过去",
    "奶瓶",
)

WANGYUE_WRONG_BRAND_PHRASES = (
    "源悦",
)

WANGYUE_EXPLICIT_AGE_PHRASES = (
    "宝宝一岁多",
    "宝宝1岁多",
    "娃一岁多",
    "孩子一岁多",
    "一岁多",
    "1岁多",
    "一岁半",
    "1岁半",
)

WANGYUE_PORTABLE_FORM_PHRASES = (
    "书包侧袋",
    "书包侧兜",
    "塞书包",
    "书包里放旺玥",
    "书包里放一盒旺玥",
    "一盒旺玥",
    "旺玥小条装",
    "便携装",
    "分装",
    "两条旺玥",
    "两条",
    "小双肩包",
    "出门背的小双肩包",
    "随身包",
    "外出随身包",
    "奶粉条",
    "小条装",
    "几袋",
    "三根",
    "奶粉盒",
    "兑点温水摇匀",
    "兑温水",
)

CHILD_SELF_BREWING_REPLACEMENT_VARIANTS = (
    "冲好后喝得挺顺",
    "那杯奶喝得还算顺",
    "到喝奶时间还挺积极",
    "递过去能慢慢喝完",
    "奶香味他还挺接受",
    "一杯递过去能慢慢喝完",
)

CHILD_SUBJECT_PATTERN = r"(?:娃|孩子|宝贝|宝宝|小朋友|儿子|闺女|他|她)"
CHILD_SELF_BREWING_PATTERNS = (
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己冲一杯"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己[^。！？；;，,]{{0,12}}(?:冲|泡)一杯"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己冲(?:旺玥|奶|奶粉)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己泡(?:旺玥|奶|奶粉)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己[^。！？；;，,]{{0,12}}(?:冲|泡)(?:旺玥|奶|奶粉)"),
    re.compile(r"自己[^。！？；;，,]{0,12}(?:冲|泡)(?:旺玥|奶|奶粉)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己(?:偷偷)?(?:拿勺子)?(?:倒水)?(?:多)?(?:舀|挖)(?:了?[一二两三]勺|粉|奶粉)(?:冲奶)?"),
)

TEMPORAL_CONTEXT_PHRASES = (
    "换季",
    "春天",
    "寒假",
    "暑假",
    "冬天",
    "夏天",
    "秋天",
    "入秋",
    "开学",
    "放假",
    "学期",
)

TEMPORAL_CONTEXT_REPLACEMENTS = (
    ("换季", "这阵"),
    ("春天", "最近"),
    ("寒假", "这段时间"),
    ("暑假", "这段时间"),
    ("冬天", "最近"),
    ("夏天", "最近"),
    ("秋天", "最近"),
    ("入秋", "最近"),
    ("开学", "最近"),
    ("放假", "这段时间"),
    ("学期", "段时间"),
)


@dataclass(frozen=True)
class ProductExperiencePhraseReview:
    pass_: bool
    rewrite_required: bool
    reasons: list[str]
    skeleton_parts: list[str]
    skeleton_hits: dict[str, list[str]]
    ai_phrase_hits: list[str]
    state_template_hits: list[str]
    odd_phrase_hits: list[str]
    strong_real_expression_hits: list[str]
    hard_risk_hits: list[str]
    adult_self_drinking_hits: list[str]
    child_self_brewing_hits: list[str]
    child_formula_bottle_hits: list[str]
    wangyue_wrong_brand_hits: list[str]
    wangyue_explicit_age_hits: list[str]
    wangyue_portable_form_hits: list[str]
    temporal_context_hits: list[str]
    body_chars: int
    length_target: tuple[str, int, int] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "rewrite_required": self.rewrite_required,
            "reasons": self.reasons,
            "skeleton_parts": self.skeleton_parts,
            "skeleton_hits": self.skeleton_hits,
            "ai_phrase_hits": self.ai_phrase_hits,
            "state_template_hits": self.state_template_hits,
            "odd_phrase_hits": self.odd_phrase_hits,
            "strong_real_expression_hits": self.strong_real_expression_hits,
            "hard_risk_hits": self.hard_risk_hits,
            "adult_self_drinking_hits": self.adult_self_drinking_hits,
            "child_self_brewing_hits": self.child_self_brewing_hits,
            "child_formula_bottle_hits": self.child_formula_bottle_hits,
            "wangyue_wrong_brand_hits": self.wangyue_wrong_brand_hits,
            "wangyue_explicit_age_hits": self.wangyue_explicit_age_hits,
            "wangyue_portable_form_hits": self.wangyue_portable_form_hits,
            "temporal_context_hits": self.temporal_context_hits,
            "body_chars": self.body_chars,
            "length_target": self.length_target,
        }


def should_review_product_experience(plan: dict[str, Any] | None) -> bool:
    plan = plan or {}
    corpus = str(plan.get("corpus") or "")
    return (
        plan.get("rule_type") == "business_rule"
        and (
            str(plan.get("asset_key") or "").startswith("wangyue_")
            or "0705旺玥活动" in corpus
        )
    )


def review_product_experience_phrase(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any] | None,
) -> ProductExperiencePhraseReview:
    plan = plan or {}
    body_text = str(body or "")
    text = f"{title or ''}\n{body_text}"
    is_wangyue = _is_wangyue_plan(plan)
    skeleton_hits = {
        part: _hits(body_text, phrases)
        for part, phrases in SKELETON_PARTS.items()
        if _hits(body_text, phrases)
    }
    skeleton_parts = sorted(skeleton_hits)
    ai_hits = _hits(text, AI_PHRASES)
    state_template_hits = _hits_prefer_longer(text, STATE_TEMPLATE_PHRASES)
    odd_phrase_hits = _hits_prefer_longer(text, ODD_PHRASES)
    strong_real_hits = _hits(text, STRONG_REAL_PHRASES)
    hard_risk_hits = _hits(text, HARD_RISK_PHRASES)
    adult_self_drinking_hits = _hits_prefer_longer(text, ADULT_SELF_DRINKING_PHRASES)
    child_self_brewing_hits = _merge_hits(
        _hits_prefer_longer(text, CHILD_SELF_BREWING_PHRASES),
        _child_self_brewing_regex_hits(text),
    )
    child_formula_bottle_hits = _hits_prefer_longer(text, CHILD_FORMULA_BOTTLE_PHRASES)
    wangyue_wrong_brand_hits = _hits_prefer_longer(text, WANGYUE_WRONG_BRAND_PHRASES) if is_wangyue else []
    wangyue_explicit_age_hits = _hits_prefer_longer(text, WANGYUE_EXPLICIT_AGE_PHRASES) if is_wangyue else []
    wangyue_portable_form_hits = _hits_prefer_longer(text, WANGYUE_PORTABLE_FORM_PHRASES) if is_wangyue else []
    temporal_context_hits = _hits_prefer_longer(text, TEMPORAL_CONTEXT_PHRASES)
    body_chars = _compact_len(body_text)
    length_target = _article_length_target(plan)

    reasons: list[str] = []
    if len(skeleton_parts) >= 3:
        reasons.append("complete_selection_price_acceptance_closure_skeleton")
    if len(ai_hits) >= 2:
        reasons.append("repeated_ai_closure_phrases")
    if _hits(text, HARD_AI_CLOSURE_PHRASES):
        reasons.append("hard_ai_closure_phrase")
    if _hits(text, COMMON_AI_CLOSURE_PHRASES):
        reasons.append("common_ai_closure_phrase")
    if _has_state_template_pattern(state_template_hits, ai_hits):
        reasons.append("state_template_phrase")
    if odd_phrase_hits:
        reasons.append("odd_product_experience_phrase")
    if hard_risk_hits:
        reasons.append("hard_risk_expression")
    if adult_self_drinking_hits:
        reasons.append("adult_self_drinking_child_formula")
    if child_self_brewing_hits:
        reasons.append("child_self_brewing_formula")
    if child_formula_bottle_hits:
        reasons.append("child_formula_bottle_context")
    if wangyue_wrong_brand_hits:
        reasons.append("wangyue_wrong_brand")
    if wangyue_explicit_age_hits:
        reasons.append("wangyue_explicit_age_context")
    if wangyue_portable_form_hits:
        reasons.append("wangyue_portable_form_context")
    if temporal_context_hits:
        reasons.append("explicit_temporal_context")

    rewrite_required = bool(reasons)
    return ProductExperiencePhraseReview(
        pass_=not rewrite_required,
        rewrite_required=rewrite_required,
        reasons=reasons,
        skeleton_parts=skeleton_parts,
        skeleton_hits=skeleton_hits,
        ai_phrase_hits=ai_hits,
        state_template_hits=state_template_hits,
        odd_phrase_hits=odd_phrase_hits,
        strong_real_expression_hits=strong_real_hits,
        hard_risk_hits=hard_risk_hits,
        adult_self_drinking_hits=adult_self_drinking_hits,
        child_self_brewing_hits=child_self_brewing_hits,
        child_formula_bottle_hits=child_formula_bottle_hits,
        wangyue_wrong_brand_hits=wangyue_wrong_brand_hits,
        wangyue_explicit_age_hits=wangyue_explicit_age_hits,
        wangyue_portable_form_hits=wangyue_portable_form_hits,
        temporal_context_hits=temporal_context_hits,
        body_chars=body_chars,
        length_target=length_target,
    )


def sanitize_temporal_context(value: str | None) -> str:
    text = str(value or "")
    for source, replacement in TEMPORAL_CONTEXT_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = text.replace("最近这阵", "最近")
    text = text.replace("最近后", "最近")
    text = text.replace("这阵后", "这阵子")
    text = text.replace("这段时间后", "这段时间")
    text = text.replace("这阵这阵", "这阵")
    text = text.replace("这段时间这段时间", "这段时间")
    text = text.replace("这段时间段时间", "这段时间")
    text = text.replace("这段时间这阵", "这段时间")
    text = re.sub(r"[，,]\s*[，,]", "，", text)
    return text.strip(" ，,")


def sanitize_common_ai_closure(value: str | None) -> str:
    text = str(value or "")
    for source, replacement in COMMON_AI_CLOSURE_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = text.replace("，。", "。")
    text = text.replace("。，", "。")
    text = text.replace("，, ", "，")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = text.replace("，.", "。")
    text = text.replace("。,", "。")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，,。；;\s]*长势$", "", text)
    text = re.sub(r"^[，,。；;]+", "", text)
    return text.strip(" ，,。；;")


def sanitize_odd_product_experience_phrases(value: str | None) -> str:
    text = str(value or "")
    for source, replacement in ODD_PHRASE_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = re.sub(r"[，,。；;\s]*(?:效果|先着吧|我这我算是)$", "", text)
    text = text.replace("，。", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def sanitize_baby_milk_action_phrases(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return text

    text = text.replace("自己搬奶粉罐去了", "我把奶粉罐拿到桌上")
    text = text.replace("自己搬奶粉罐", "我把奶粉罐拿到桌上")
    text = text.replace("自己开柜门拿奶粉罐", "在旁边等我冲奶")
    text = text.replace("开柜门拿奶粉罐", "等我冲奶")
    text = text.replace("蹬着小凳子去够奶粉罐", "搬着小凳子坐过来等")
    text = text.replace("自己搬凳子去够柜子上的罐子", "自己搬凳子坐过来等")
    text = text.replace("搬凳子去够柜子上的罐子", "搬凳子坐过来等")
    text = text.replace("自己搬凳子去够罐子", "自己搬凳子坐过来等")
    text = text.replace("搬凳子去够罐子", "搬凳子坐过来等")
    text = text.replace("踮脚够奶粉罐", "踮脚等着喝奶")
    text = text.replace("去够奶粉罐", "等着喝奶")
    text = text.replace("够奶粉罐", "等着喝奶")
    text = text.replace("去够柜子上的罐子", "坐过来等")
    text = text.replace("够柜子上的罐子", "坐过来等")
    text = text.replace("抱着空罐子在地上滚", "抱着玩具在地上滚")
    text = text.replace("抱着空罐子", "抱着玩具")
    text = text.replace("扛奶粉", "拎奶粉")
    text = text.replace("自己到点就去泡一杯", "到点会过来等我冲")
    text = text.replace("每天早上自己跑去冲一杯", "每天早上会过来等我冲")
    text = text.replace("每天早上主动去冲", "每天早上会过来等我冲")
    text = text.replace("自己跑去冲一杯", "会过来等我冲")
    text = text.replace("主动去冲", "过来等我冲")
    text = text.replace("自己会去冲", "会过来等我冲")
    text = text.replace("自己去冲", "过来等我冲")
    text = text.replace("自己抱着杯子要冲", "抱着杯子等我冲")
    text = text.replace("自己拿勺子挖了两勺", "在旁边看着我冲")
    text = text.replace("自己抱着罐子让冲", "抱着杯子等我冲")
    text = text.replace("他泡好端着", "我冲好递给他")
    text = text.replace("泡好端着", "冲好递过去")
    text = text.replace("主动去倒奶喝", "到喝奶时间还挺积极")
    text = text.replace("自己主动去冲", "到喝奶时间还挺积极")
    for phrase in sorted(CHILD_SELF_BREWING_PHRASES, key=len, reverse=True):
        text = text.replace(phrase, _child_self_brewing_replacement(text, phrase=phrase))
    text = _sanitize_child_self_brewing_patterns(text)

    text = text.replace("奶瓶一递过去", "奶杯一递过去")
    text = text.replace("抱着奶瓶", "抱着杯子")
    text = text.replace("看奶瓶", "看奶量")
    text = text.replace("奶瓶里", "杯子里")
    text = text.replace("奶瓶", "杯子")

    text = text.replace("每天每天", "每天")
    text = text.replace("早上早上", "早上")
    text = text.replace("，。", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def sanitize_adult_self_drinking_phrases(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return text

    text = text.replace("反正喝不完我自己也能当早餐奶", "反正先试一罐")
    text = text.replace("喝不完我自己也能当早餐奶", "先试一罐")
    text = text.replace("我自己也能当早餐奶", "先试一罐")
    text = text.replace("自己也能当早餐奶", "先试一罐")
    text = text.replace("给自己冲了一杯旺玥", "给孩子冲了一杯旺玥")
    text = text.replace("给自己冲一杯旺玥", "给孩子冲一杯旺玥")
    text = text.replace("自己冲了一杯旺玥", "给孩子冲了一杯旺玥")
    text = text.replace("自己冲一杯旺玥", "给孩子冲一杯旺玥")
    text = text.replace("给自己泡了一杯旺玥", "给孩子泡了一杯旺玥")
    text = text.replace("给自己泡一杯旺玥", "给孩子泡一杯旺玥")
    text = text.replace("我喝了一杯旺玥", "孩子喝了一杯旺玥")
    text = text.replace("我也喝旺玥", "孩子也喝旺玥")
    text = text.replace("妈妈自己喝旺玥", "孩子喝旺玥")
    text = text.replace("我自己喝着觉得挺香", "孩子喝着觉得挺香")
    text = text.replace("自己先喝了一口", "先递给孩子喝")
    text = text.replace("先试一罐吧，先试一罐", "先试一罐吧")
    text = text.replace("先试一罐吧，反正先试一罐", "先试一罐吧")
    text = text.replace("，。", "。")
    text = text.replace("。，", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def sanitize_wangyue_context_phrases(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return text

    text = text.replace("源悦", "旺玥")
    for phrase in WANGYUE_EXPLICIT_AGE_PHRASES:
        text = text.replace(phrase, "孩子")
    text = text.replace("孩子开始", "孩子大点开始")
    text = text.replace("孩子之后", "孩子大点之后")

    text = re.sub(
        r"(?:书包侧袋|书包侧兜|书包里|塞书包)[^。！？；;]*?(?:一盒旺玥|旺玥|奶粉盒|旺玥小条装)[^。！？；;]*",
        "家里那罐旺玥",
        text,
    )
    text = text.replace("旺玥小条装", "旺玥奶粉")
    text = text.replace("便携装", "这罐奶粉")
    text = text.replace("分装", "奶粉")
    text = text.replace("两条旺玥", "一杯旺玥")
    text = text.replace("两条", "一杯")
    text = text.replace("出门背的小双肩包", "家里的餐边柜")
    text = text.replace("小双肩包", "餐边柜")
    text = text.replace("外出随身包", "餐边柜")
    text = text.replace("随身包", "餐边柜")
    text = text.replace("奶粉条", "奶粉")
    text = text.replace("小条装", "奶粉")
    text = re.sub(r"干掉了[一二两三0-9]+根", "喝完一杯", text)
    text = text.replace("几袋", "一些")
    text = text.replace("塞奶粉盒兑点温水摇匀", "家里那罐旺玥照常冲好")
    text = text.replace("兑点温水摇匀", "照常冲好")
    text = text.replace("兑温水", "照常冲好")
    text = text.replace("一盒旺玥", "一罐旺玥")
    text = text.replace("奶粉盒", "奶粉罐")

    text = text.replace("孩子孩子", "孩子")
    text = text.replace("，。", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase and phrase in text]


def _hits_prefer_longer(text: str, phrases: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for phrase in sorted((phrase for phrase in phrases if phrase and phrase in text), key=len, reverse=True):
        if any(phrase in existing for existing in hits):
            continue
        hits.append(phrase)
    return hits


def _merge_hits(*groups: list[str]) -> list[str]:
    hits: list[str] = []
    for group in groups:
        for hit in group:
            if hit not in hits:
                hits.append(hit)
    return hits


def _child_self_brewing_regex_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in CHILD_SELF_BREWING_PATTERNS:
        for match in pattern.finditer(text):
            hit = match.group(0)
            if hit not in hits:
                hits.append(hit)
    return hits


def _has_state_template_pattern(state_hits: list[str], ai_hits: list[str]) -> bool:
    if len(state_hits) >= 2:
        return True
    closure_hits = {"省心", "踏实", "安心"}
    return bool(state_hits and closure_hits.intersection(ai_hits))


def _child_self_brewing_replacement(text: str, *, phrase: str | None = None) -> str:
    if phrase and ("舀" in phrase or "挖" in phrase):
        variants = ("那杯奶喝得挺顺", "喝奶还算配合", "喝得还挺顺")
        return variants[sum(ord(char) for char in text) % len(variants)]
    if "早上" in text:
        variants = ("早上那杯喝得还算顺", "早上那杯奶喝得挺顺", "早上冲好后喝得挺顺")
    elif "每天" in text:
        variants = ("每天那杯喝得挺顺", "每天喝奶还算配合", "每天那杯基本能喝完")
    else:
        variants = CHILD_SELF_BREWING_REPLACEMENT_VARIANTS
    return variants[sum(ord(char) for char in text) % len(variants)]


def _sanitize_child_self_brewing_patterns(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        hit = match.group(0)
        prefix = re.sub(
            r"自己(?:[^。！？；;，,]{0,12}(?:冲|泡)一杯|[^。！？；;，,]{0,12}(?:冲|泡)(?:旺玥|奶|奶粉)|冲(?:旺玥|奶|奶粉)|泡(?:旺玥|奶|奶粉)|(?:偷偷)?(?:拿勺子)?(?:倒水)?(?:多)?(?:舀|挖)(?:了?[一二两三]勺|粉|奶粉)(?:冲奶)?).*$",
            "",
            hit,
        )
        if "舀" in hit or "挖" in hit:
            variants = ("那杯奶喝得挺顺", "喝奶还算配合", "喝得还挺顺")
        elif "早上" in prefix:
            variants = ("那杯喝得还算顺", "那杯奶喝得挺顺", "冲好后喝得挺顺")
        elif "每天" in prefix:
            variants = ("那杯喝得挺顺", "喝奶还算配合", "那杯基本能喝完")
        else:
            variants = CHILD_SELF_BREWING_REPLACEMENT_VARIANTS
        return prefix + variants[sum(ord(char) for char in hit) % len(variants)]

    for pattern in CHILD_SELF_BREWING_PATTERNS:
        text = pattern.sub(replace, text)
    return text


def _is_wangyue_plan(plan: dict[str, Any]) -> bool:
    corpus = str(plan.get("corpus") or "")
    return str(plan.get("asset_key") or "").startswith("wangyue_") or "旺玥" in corpus


def _compact_len(value: str | None) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _article_length_target(plan: dict[str, Any]) -> tuple[str, int, int] | None:
    corpus = str(plan.get("corpus") or "")
    if "篇幅类型：中短文" in corpus:
        return "中短文", 120, 150
    if "篇幅类型：短文" in corpus:
        return "短文", 40, 80
    return None
