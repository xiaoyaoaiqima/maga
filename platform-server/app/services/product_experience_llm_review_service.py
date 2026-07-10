"""LLM quality review for Wangyue product-experience UGC articles."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any

from app.services.llm_factory import LLMFactory
from app.services.product_experience_phrase_guard_service import ProductExperiencePhraseReview


@dataclass(slots=True)
class ProductExperienceLLMIssue:
    code: str
    evidence: str
    reason: str
    rewrite_direction: str


@dataclass(slots=True)
class ProductExperienceLLMReview:
    pass_: bool
    rewrite_required: bool
    severity: str
    issues: list[ProductExperienceLLMIssue] = field(default_factory=list)
    business_usability_tier: str = "direct_pool"
    business_usability_reason: str = ""
    product_appearance_naturalness: int = 3
    decision_chain_fit: int = 3
    product_value_strength: int = 3
    human_realness: int = 3
    overall_reason: str = ""
    raw_response: str = ""

    def model_dump(self) -> dict[str, Any]:
        data = asdict(self)
        data["pass"] = data.pop("pass_")
        return data


class ProductExperienceLLMReviewService:
    """Use a model to judge product permission and realism instead of rigid word thresholds."""

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        plan: dict[str, Any] | None,
        phrase_review: ProductExperiencePhraseReview | None = None,
        ai_flavor_review: Any | None = None,
    ) -> ProductExperienceLLMReview:
        plan = plan or {}
        response = await LLMFactory.call_llm(
            config=_review_model_config(plan),
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_user_prompt(
                title=title,
                body=body,
                plan=plan,
                phrase_review=phrase_review,
                ai_flavor_review=ai_flavor_review,
            ),
        )
        review = parse_product_experience_llm_review(str(response or ""))
        return _calibrate_review_with_context(
            review,
            title=title,
            body=body,
            phrase_review=phrase_review,
        )


def parse_product_experience_llm_review(raw_response: str) -> ProductExperienceLLMReview:
    payload = _extract_json_object(raw_response)
    severity = str(payload.get("severity") or "pass").strip().lower()
    if severity not in {"pass", "minor", "rewrite", "hard"}:
        severity = "rewrite" if payload.get("rewrite_required") else "pass"
    issues = [
        ProductExperienceLLMIssue(
            code=str(issue.get("code") or "quality_issue"),
            evidence=str(issue.get("evidence") or "")[:200],
            reason=str(issue.get("reason") or "")[:300],
            rewrite_direction=_sanitize_rewrite_direction(
                code=str(issue.get("code") or "quality_issue"),
                rewrite_direction=str(issue.get("rewrite_direction") or ""),
            ),
        )
        for issue in payload.get("issues") or []
        if isinstance(issue, dict)
    ]
    issues = _drop_concrete_ingredient_brief_translation_issues(issues)
    if _overcomplete_decision_chain_only(issues) and severity in {"rewrite", "hard"}:
        severity = "minor"
    if not issues and severity in {"rewrite", "hard"}:
        severity = "minor"
    rewrite_required = severity in {"rewrite", "hard"} or (
        bool(payload.get("rewrite_required")) and severity != "minor"
    )
    pass_ = bool(payload.get("pass", not rewrite_required)) and not rewrite_required
    business_usability_tier = _business_usability_tier(
        payload.get("business_usability_tier"),
        severity=severity,
        rewrite_required=rewrite_required,
    )
    return ProductExperienceLLMReview(
        pass_=pass_,
        rewrite_required=rewrite_required,
        severity=severity,
        issues=issues,
        business_usability_tier=business_usability_tier,
        business_usability_reason=str(payload.get("business_usability_reason") or "")[:300],
        product_appearance_naturalness=_score(payload.get("product_appearance_naturalness")),
        decision_chain_fit=_score(payload.get("decision_chain_fit")),
        product_value_strength=_score(payload.get("product_value_strength")),
        human_realness=_score(payload.get("human_realness")),
        overall_reason=str(payload.get("overall_reason") or "")[:500],
        raw_response=raw_response[:4000],
    )


def _calibrate_review_with_context(
    review: ProductExperienceLLMReview,
    *,
    title: str | None,
    body: str | None,
    phrase_review: ProductExperiencePhraseReview | None,
) -> ProductExperienceLLMReview:
    """Downgrade known Wangyue false positives that require the actual text context."""
    text = f"{title or ''}\n{body or ''}"
    issues = [
        issue
        for issue in review.issues
        if not _is_false_positive_llm_issue(issue, text=text, phrase_review=phrase_review)
    ]
    if len(issues) == len(review.issues):
        return review
    return _review_with_recalculated_status(review, issues)


def _is_false_positive_llm_issue(
    issue: ProductExperienceLLMIssue,
    *,
    text: str,
    phrase_review: ProductExperiencePhraseReview | None,
) -> bool:
    if issue.code == "ad_like_closure":
        return _is_missing_closure_evidence(issue, text)
    if issue.code == "formula_usage_form_error":
        return _is_safe_adult_cup_action(issue, phrase_review=phrase_review)
    if issue.code == "claim_risk":
        return _is_allowed_protection_feedback(issue)
    return False


def _is_missing_closure_evidence(issue: ProductExperienceLLMIssue, text: str) -> bool:
    closure_markers = ("省心", "安心", "踏实", "放心", "心里有底", "心里有数", "选对", "没选错")
    if not any(marker in issue.evidence or marker in issue.reason for marker in closure_markers):
        return False
    return not any(marker in text for marker in closure_markers)


def _is_safe_adult_cup_action(
    issue: ProductExperienceLLMIssue,
    *,
    phrase_review: ProductExperiencePhraseReview | None,
) -> bool:
    evidence = issue.evidence
    if phrase_review and "formula_usage_form_error" in phrase_review.reasons:
        return False
    if any(marker in evidence for marker in ("自己冲", "自己泡", "奶瓶", "分装", "书包", "背包", "便携", "小条装")):
        return False
    return any(marker in evidence for marker in ("我给他冲一杯", "妈妈冲", "冲一杯", "水杯", "杯子"))


def _is_allowed_protection_feedback(issue: ProductExperienceLLMIssue) -> bool:
    evidence = issue.evidence + issue.reason
    allowed_markers = ("接触多", "状态稳", "一直稳", "出勤", "精神头")
    hard_markers = (
        "医院",
        "高烧",
        "发烧",
        "治疗",
        "医生",
        "体检",
        "备药",
        "不生病",
        "防护",
        "自身防护",
        "保证",
        "全靠",
        "因为旺玥所以",
    )
    return any(marker in evidence for marker in allowed_markers) and not any(
        marker in evidence for marker in hard_markers
    )


def _review_with_recalculated_status(
    review: ProductExperienceLLMReview,
    issues: list[ProductExperienceLLMIssue],
) -> ProductExperienceLLMReview:
    if not issues:
        return ProductExperienceLLMReview(
            pass_=True,
            rewrite_required=False,
            severity="pass",
            issues=[],
            business_usability_tier="direct_pool",
            business_usability_reason=review.business_usability_reason,
            product_appearance_naturalness=review.product_appearance_naturalness,
            decision_chain_fit=review.decision_chain_fit,
            product_value_strength=review.product_value_strength,
            human_realness=review.human_realness,
            overall_reason=review.overall_reason,
            raw_response=review.raw_response,
        )
    severity = review.severity
    if severity == "hard" and all(issue.code in {"claim_risk", "formula_usage_form_error", "ad_like_closure"} for issue in issues):
        severity = "rewrite"
    rewrite_required = severity in {"rewrite", "hard"}
    pass_ = review.pass_ and not rewrite_required
    return ProductExperienceLLMReview(
        pass_=pass_,
        rewrite_required=rewrite_required,
        severity=severity,
        issues=issues,
        business_usability_tier=_business_usability_tier(
            review.business_usability_tier,
            severity=severity,
            rewrite_required=rewrite_required,
        ),
        business_usability_reason=review.business_usability_reason,
        product_appearance_naturalness=review.product_appearance_naturalness,
        decision_chain_fit=review.decision_chain_fit,
        product_value_strength=review.product_value_strength,
        human_realness=review.human_realness,
        overall_reason=review.overall_reason,
        raw_response=review.raw_response,
    )


def _review_model_config(plan: dict[str, Any]) -> dict[str, Any]:
    unified_generation = plan.get("unified_generation") or {}
    expert = unified_generation.get("expert") or {}
    model_config = dict(
        plan.get("model_config")
        or unified_generation.get("model_config")
        or expert.get("model_config")
        or {}
    )
    return {
        **model_config,
        "provider": model_config.get("provider") or model_config.get("provider_code"),
        "model": model_config.get("model") or model_config.get("model_code") or model_config.get("ge_model"),
        "temperature": 0.1,
        "max_tokens": 1200,
    }


def _user_prompt(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any],
    phrase_review: ProductExperiencePhraseReview | None,
    ai_flavor_review: Any | None = None,
) -> str:
    hints = phrase_review.model_dump() if phrase_review else {}
    ai_hints = ai_flavor_review.model_dump() if hasattr(ai_flavor_review, "model_dump") else {}
    compact_plan = {
        key: plan.get(key)
        for key in (
            "asset_key",
            "post_type",
            "ugc_post_type",
            "product_appearance_mode",
            "product_action_surface",
            "scene_motive_bucket",
            "structure_slot",
            "scene_constraint",
            "painpoint",
            "selling_point",
            "corpus",
        )
        if plan.get(key) is not None
    }
    return json.dumps(
        {
            "task": "review_wangyue_ugc_product_naturalness",
            "title": title or "",
            "body": body or "",
            "plan": compact_plan,
            "deterministic_hints": {
                "reasons": hints.get("reasons") or [],
                "decision_chain_hits": hints.get("decision_chain_hits") or {},
                "product_effect_proof_chain_hits": hints.get("product_effect_proof_chain_hits") or {},
                "ai_phrase_hits": hints.get("ai_phrase_hits") or [],
                "skeleton_hits": hints.get("skeleton_hits") or {},
                "child_self_brewing_hits": hints.get("child_self_brewing_hits") or [],
                "child_formula_bottle_hits": hints.get("child_formula_bottle_hits") or [],
                "ingredient_benefit_mismatch_hits": hints.get("ingredient_benefit_mismatch_hits") or [],
                "product_fact_number_drift_hits": hints.get("product_fact_number_drift_hits") or [],
                "effect_scope_drift_hits": hints.get("effect_scope_drift_hits") or [],
                "wangyue_portable_form_hits": hints.get("wangyue_portable_form_hits") or [],
                "wangyue_supplement_replacement_hits": hints.get("wangyue_supplement_replacement_hits") or [],
                "wangyue_explicit_age_hits": hints.get("wangyue_explicit_age_hits") or [],
                "wangyue_article_logic_drift_hits": hints.get("wangyue_article_logic_drift_hits") or [],
                "wangyue_hidden_negative_comparison_hits": hints.get("wangyue_hidden_negative_comparison_hits") or [],
                "ai_flavor_reasons": ai_hints.get("reasons") or [],
                "ai_flavor_title_hits": ai_hints.get("title_hits") or [],
                "ai_flavor_body_hits": ai_hints.get("body_hits") or [],
                "ai_flavor_rewrite_operations": ai_hints.get("rewrite_operations") or [],
            },
        },
        ensure_ascii=False,
    )


def _extract_json_object(raw_response: str) -> dict[str, Any]:
    text = raw_response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM review did not return a JSON object")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM review JSON must be an object")
    return data


def _score(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, number))


def _business_usability_tier(
    value: Any,
    *,
    severity: str,
    rewrite_required: bool,
) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "a": "direct_pool",
        "a_direct_pool": "direct_pool",
        "direct": "direct_pool",
        "direct_pool": "direct_pool",
        "直接入池": "direct_pool",
        "b": "light_fix_usable",
        "b_light_fix_usable": "light_fix_usable",
        "light_fix": "light_fix_usable",
        "light_fix_usable": "light_fix_usable",
        "轻修可用": "light_fix_usable",
        "c": "hold_out",
        "c_hold_out": "hold_out",
        "hold": "hold_out",
        "hold_out": "hold_out",
        "暂不入池": "hold_out",
    }
    if severity == "minor" and not rewrite_required:
        if normalized in {"direct", "direct_pool", "直接入池"}:
            return "direct_pool"
        return "light_fix_usable"
    if normalized in aliases:
        return aliases[normalized]
    if severity == "hard" or (rewrite_required and severity == "rewrite"):
        return "hold_out"
    return "direct_pool"


def _sanitize_rewrite_direction(*, code: str, rewrite_direction: str) -> str:
    text = rewrite_direction.strip()
    if code == "brief_translation_tone":
        text = re.split(r"(?:例如|比如|可以改成|可改成|改成)：?", text, maxsplit=1)[0].strip()
        text = text.rstrip("，,；;。")
    return text[:300]


def _overcomplete_decision_chain_only(issues: list[ProductExperienceLLMIssue]) -> bool:
    return bool(issues) and {issue.code for issue in issues} == {"overcomplete_decision_chain"}


def _drop_concrete_ingredient_brief_translation_issues(
    issues: list[ProductExperienceLLMIssue],
) -> list[ProductExperienceLLMIssue]:
    return [
        issue
        for issue in issues
        if not (
            issue.code == "brief_translation_tone"
            and _is_concrete_ingredient_plain_speech(issue.evidence)
        )
    ]


def _is_concrete_ingredient_plain_speech(text: str) -> bool:
    text = str(text or "")
    if not text:
        return False
    concrete_terms = (
        "钙铁锌",
        "DHA",
        "燕窝酸",
        "乳铁蛋白",
        "HMO",
        "免疫球蛋白",
        "基础营养",
        "关键营养",
        "配方表",
        "成分表",
        "配料表",
    )
    if not any(term in text for term in concrete_terms):
        return False
    abstract_markers = (
        "方向",
        "这个点",
        "这块",
        "会看",
        "重点看",
        "值得",
        "优先",
        "留意",
        "在意",
        "记住",
        "依据",
        "会更顺",
        "安排起来",
        "多一层考虑",
        "让我",
    )
    if any(marker in text for marker in abstract_markers):
        return False
    return len(text) <= 90


_SYSTEM_PROMPT = """你是中文小红书母婴 UGC 内容质检员，专门判断“真实 UGC 帖子里带产品”是否自然。
你的角色不是普通读者，也不是帮内容找理由通过；你是严苛但可校准的后置编辑。你要先分级，再决定是否改写。

核心目标：
1. 内容要正面表达旺玥儿童奶粉的产品价值。
2. 产品出现必须有帖子类型许可，不能像硬塞广告。
3. 真人感来自具体但不必完整的生活链路；不要因为有产品卖点就判差，也不要因为有口语就判好。

重要判断原则：
- 词表命中只是提示，不是扣分规则。你必须按上下文和帖子类型判断。
- deterministic_hints 里的 ai_flavor_* 只是提示，不是自动 rewrite 规则；如果它们和真实帖子语境不冲突，可以判 pass 或 minor。
- 真实帖子可以有决策链，但常常是短的、偏的、不完整的。问题是“链路过满”，不是“不能正面种草”。
- 旺玥正向声量内容允许一个短的种草证明链：生活困扰/使用履历 -> 旺玥在场 -> 一个正向变化。只要没有再叠加完整选购复盘、价格取舍、孩子接受度、妈妈安心收口，就不要因为“产品带来变化”本身判 rewrite。
- 真实 UGC 带产品本来就可能有轻微种草感；只要产品有出现资格、只保留一个生活触发和一个产品依据，可以判 pass 或 minor，不要因为“像种草”本身就判 rewrite。
- 强种草问答、选奶复盘、复购/长期使用里，允许出现“朋友/家人顺口问起 -> 旺玥 -> 一个成分依据 -> 一个或多个自家正向反馈 -> 一点生活毛边/继续用”的完整种草链路。只要语气像真人、产品事实正确、没有医疗治疗或绝对保证，不要仅因节点多或链路完整就判 rewrite；节点密度主要是批次分布问题，不是单篇硬伤。
- 疾病或免疫相关场景要看措辞强度：少请假、没怎么中招、精神头在线、出门不蔫这类自家观察，在使用反馈、选奶复盘、复购/长期使用、求建议后的反馈里可以作为强种草表达；只有写成保证不生病、治疗、医生建议、体检结论、明确因旺玥所以不生病，才判 hard。
- 保护力相关内容可以正面有力，但要区分“自家状态观察”和“公共疾病环境对照”。自家出勤稳、状态稳、精神头还行、活动后不蔫，可以 pass/minor；如果标题或正文主要靠周围孩子中招、班里请假多、好几个没来、倒了一片、这波那波来证明自家状态，必须判 rewrite，issue code 用 claim_risk 或 public_disease_contrast。改写方向是保留旺玥的保护力价值和一个自家状态反馈，删掉公共疾病环境对照，不要新增医疗事实。
- 三天两头跑医院、高烧/发烧、备药成习惯、治疗、医生建议、没再高烧、少跑医院，或把乳铁蛋白/HMO写成“防护/自身防护/肠道”的确定功能，必须判 rewrite 或 hard，business_usability_tier 通常为 hold_out，issue code 用 claim_risk。改写方向是保留一个普通自家状态反馈，例如出勤稳、状态稳、精神头还行，不要新增医疗事实。
- 旺玥成分和好处的承接服从当前业务规则。乳铁蛋白/免疫球蛋白/HMO承接保护力、精神头、状态稳、抱起来沉、长肉、衣服撑起来、跑跳有劲、身形结实等积极观察时，不要仅因“成分-积极结果相连”判 rewrite 或 hard；业务规则如果需要更细的卖点侧重，会在规则语料里控制。
- ingredient_benefit_mismatch 不再作为独立硬判项。只有同时出现医疗治疗、绝对保证、错误产品事实、疾病公共环境对照等更明确风险时，才按 claim_risk、post_type_mismatch 或 other 处理；改写方向也只处理这些明确风险，不要把强正向效果洗弱成不确定表达。
- 必须判 rewrite 的 product_fact_number_drift：旺玥关键营养数字口径不能自行编造。可以写“多种关键营养”或业务规则给出的“30多种关键营养”，不能写成“十几种/十多种/20多种/几十种关键营养”。改写方向是保留正向营养价值，只修数字口径，不要削弱种草。
- 必须判 rewrite 的 effect_scope_drift：如果业务规则不是睡眠/入睡主题，不能把旺玥或喝奶写成让孩子睡得安稳、一整夜不闹、入睡变好、睡眠改善的原因或近因。改写方向是删掉睡眠效果连接，保留本篇痛点对应的正向价值，例如保护力、活动后状态稳、精神头、日常营养或成长阶段营养。
- “满分答案、buff 拉满、成长刚需”这类高商业浓度表达不是绝对禁词；它们在强种草、明确测评、品牌活动稿里可能成立。你要判断的是表达浓度和帖子类型是否匹配：低解释义务的日常记录、选奶轻复盘、轻配方关注里出现这类口号式表达，通常才判 rewrite。
- 参考真实用户写法时，要看发帖动作和表达角色：真实妈妈更常见的是纠结、对比、看成分、问喝过没、记录补货或被别人问起；她们不太会把卖点抽象成“我会关注的方向/这个点值得看/营养这块要优先”这种选品总结。
- brief_translation_tone 只用于“抽象选品总结 + 可复制结构 + 缺少真实发帖动作”同时出现的情况。典型问题是“这个方向我会看/这个点值得关注/营养这块要优先/保护力这块我比较在意/日常口粮里多留意这一块/产品依据我记住的是……”。
- 不要把妈妈大白话里的具体成分/配方事实误判成 brief_translation_tone。在朋友问起、选奶复盘、轻测评里，“钙铁锌这些基础营养看着挺全”“DHA和燕窝酸都写得挺清楚”“乳铁蛋白和HMO我当时看了一眼”“配方表我就看了这几个”“别的参数我也看不太懂，就记住这几个”可以是真人简化说法；如果它有问题，通常应按 post_type_mismatch、ad_like_closure 或明确 claim_risk 判断，不要把 brief_translation_tone 当主罪。
- 如果正文把“生活入口 + 卖点方向”翻译成一段完整、顺滑、可复刻的妈妈选品理由，并继续串上选择结果、持续使用、孩子接受度、安心收口或多个效果证明，才判 rewrite，issue code 用 brief_translation_tone。
- 不要鼓励用“还在观察、不能指望一罐奶粉、每家情况不同”这种合规声明制造真实感；这会削弱业务价值。
- 旺玥内容要保持品牌和产品正面性。不要保留价格取舍，不要写旺玥贵、不便宜、价格高、值不值或拿普通款/低配参照物比较；这类表达会把正向种草拖成隐性负面，通常判 rewrite。
- 如果需要改写，方向是保留一个最强正向产品价值；效果证明是旺玥种草内容的业务核心，不要自动洗成不确定或负面。
- rewrite_direction 必须遵守原业务规则，不要为了让产品出现更自然而新增原文没有的喝奶、冲泡、早晚杯数、早餐搭配、加进牛奶、孩子喝完/接受/不抗拒等产品动作；这些动作会把内容带回广告或错误使用场景。
- rewrite_direction 不能建议删掉所有产品价值。至少保留一个正向依据，例如基础营养覆盖、钙铁锌、关键营养、日常营养补充安排，具体保留哪一个要服从本篇业务规则。
- rewrite_direction 只描述结构方向，不要提供可直接照抄的替换句，也不要用“例如/可以改成”引出半句示例；尤其不要把问题改写成另一套固定话术，例如“记下了/看到了/这个点/这个方向/会看这块”。
- pass 不是“完美”，而是“无需后置改写也能用”。minor 表示有轻微广告感、标题略硬、完整链略满，但改写收益不高、容易洗掉产品价值；minor 不触发改写。节点多、种草强、效果证明多，不应单独触发 rewrite；这类问题应在批量生成侧做比例控制。如果唯一问题是 overcomplete_decision_chain，severity 必须是 minor，rewrite_required=false。rewrite 表示不改会明显像任务广告、模板收口、产品硬塞或事实/功效风险。
- rewrite_direction 也必须克制：不要建议新增孩子爱喝/不排斥、妈妈放心/踏实/省心、眼前一亮、强推荐、太值了、没换别的、一直喝。除非原帖类型就是复购/长期使用且它只保留这一个节点。

旺玥使用场景事实边界：
- 旺玥是 3 周岁以上专用 4 段儿童奶粉，内容可以写妈妈冲好、递给孩子、孩子拿着杯子喝完；这属于正常生活动作，不是错误产品动作。
- 必须判 hard 的 wangyue_age_stage_error：正文或标题明确/隐含孩子低于3周岁时使用、购买、备着、开始喝旺玥，或把旺玥放进断奶、辅食、一两岁、未满三岁、三岁前的使用链路。这个是产品事实硬错误，不是表达风格问题。
- 年龄判断不能只看词表。你要按上下文判断语义：如果“刚断奶那阵、还在辅食阶段、上幼儿园前、一两岁开始、不到三岁就固定喝”等表达和旺玥形成使用/购买/备货关系，即使没有标准年龄词，也要判 hard；如果只是“刚满三岁/满三岁/3岁以后/3岁+阶段/3-6岁/4段/学龄前”且事实正确，不要判年龄错误。
- 改写 wangyue_age_stage_error 时，保留原文正向种草价值，但把年龄关系改到3周岁以后/学龄前阶段；不要把低龄词机械替换成“孩子/这个阶段”造成残句，也不要完整复述成“3岁以上4段儿童奶粉”。
- 必须判 hard 的 child_formula_operation_error：孩子自己开罐、舀粉、倒水、冲泡、兑水、抱着奶粉罐操作，或把“自己拿杯子”写成孩子自己完成奶粉操作。
- 必须判 hard 的 formula_dry_powder_ingestion：把奶粉干粉直接放进孩子嘴里、让孩子干吃/尝粉/吃粉，或妈妈舀粉喂孩子。改写方向是删除相关动作，不要改成新的冲泡、喝奶或试喝情节。
- 必须判 rewrite 或 hard 的 formula_usage_form_error：把旺玥写成分装、冷藏、盒装奶粉、固定时段喝法、孩子抱走产品或自己记得喝这类产品物理使用/存放事实。改写方向是删除相关产品动作，保留原有正向产品价值，不要改成另一套喝奶流程。
- 必须判 hard 的 portable_product_error：把旺玥写成小条装、便携装、奶粉条、分装、书包/背包/侧袋里的随身产品，或写成保温杯/水壶里带着旺玥、出门兑温水随时能喝。
- 书包、侧袋、背包可以只是生活细节。只有它和旺玥/奶粉/冲泡/兑温水/小条装/便携装形成同一产品使用关系时，才判 portable_product_error。
- 必须判 rewrite 的 supplement_replacement_error：旺玥可以正面写基础营养、关键营养、日常营养安排，但不能写成替代营养片、维生素、补剂、钙片或 DHA 胶囊。
- “孩子自己拿着杯子喝完/自己跑去拿杯子”如果前文是妈妈冲好或递过去，通常可 pass 或 minor；不要把它误判为 child_formula_operation_error。
- “孩子愿意喝、喝完、自己拿杯子”可以是接受度或效果证明节点。它可能造成链路偏满，但不是事实错误；除非同时出现错误奶粉操作或便携产品形态，否则不要按 hard 改。
- “拉保护力/把保护力拉上来/孩子自己撑起保护屏障”这类表达可按妈妈口语里的“拉高、提升、往上补”理解；只要没有治疗、保证、不生病承诺或错误奶粉操作，不要单独判 rewrite。

分级规则：
- pass：自然生活入口 + 旺玥有合理在场方式 + 清楚的正向产品价值或效果证明；即使链路较完整，只要像真实强种草帖且没有事实/功效风险，也可 pass。
- minor：略短、略直接、标题略硬、朋友/家人评价略像收口，但产品角色正确，文本真实且业务价值强；记录问题但 rewrite_required=false。
- rewrite：产品突然成为大问题答案、链路堆到像任务广告且伴随帖子类型错配/广告收口/事实风险/强因果风险，安心收口模板明显、合规防守句明显、标题/正文像运营任务。不要只因为链路完整就 rewrite。
- hard：医疗治疗、绝对保证、错误产品动作、明显事实错误、严重帖子类型错配。
- hard 或 rewrite：用医院、高烧、发烧、治疗、医生、备药、少跑医院、没再高烧等医疗化场景证明旺玥有效，或把 HMO/乳铁蛋白直接写成防护/肠道功能结论。
- 强效果证明不是自动 hard。保护力稳了、少请假、没中招、精神变足、注意力变好、长高长肉等表达，在复购/长期使用、使用反馈、求建议后的反馈、阶段复盘、明确强种草内容里可以成立；你要判断的是它是否有使用履历、是否像真人观察、是否和帖子类型匹配、是否过频或形成假闭环。
- 仍需判 hard 的情况：把旺玥写成治疗、保证、不生病承诺、医生/体检结论，或写成加进牛奶、早餐搭配、每天一杯、早晚固定喝等原业务规则未给出的具体产品动作。

必须判 rewrite 的情况：
- 标题像选题说明、攻略标题或卖点归纳，例如“选奶标准/日常营养安排/保护力关注/补营养/取舍/复盘/标准/配方表翻到某栏”。
- 正文把生活问题、选择依据、价格/预算、孩子接受度、持续使用/没换、妈妈安心/不焦虑/保底/省心，串成 4 个以上节点，并且这些节点明显像品牌任务稿、导购话术或虚假证明闭环，同时还出现帖子类型错配、广告收口、事实风险或强因果风险。不要只因为“朋友问起 + 成分依据 + 多个自家反馈 + 一点生活毛边/继续用”就判 rewrite；这类高密度种草单篇可以通过，批次里控制比例即可。只有完整链过满但没有其它问题时，issue code 可以写 overcomplete_decision_chain，但 severity 必须是 minor。
- 使用反馈、问题解决、家庭清单里回填“当时选它/后来看到/对比过/价格/孩子接受/没换别的/一直喝”这类完整选购复盘。
- 用“不敢说有效、不能指望、没指望靠这个、不是光靠这个、每家不一样、还在观察、后面再看、再看看、不是因为它多神奇”来制造真实感。
- 用“心里有数、心里有底、兜底、兜住、有个着落、有谱、省心、踏实、安心”这类词做统一收口。注意：这些词不是绝对禁词，只有当它们在上下文里替代了具体生活判断、把产品价值收成妈妈安心模板时才判 rewrite。
- 产品动作过实：每天喝、每次冲一杯、早上或下午当一顿奶喝、喝下来、不排斥、喝得顺，并接到产品价值或继续使用。
- 产品被写成万能答案或假闭环，比如吃饭不稳/没电/接触多后，继续叠加旺玥补充、孩子接受、价格取舍、复购保留、妈妈安心收口，并把生活问题直接归因成旺玥解决。否则，即使朋友问起后给出一个成分依据和多个自家反馈，也不要按这一条判 rewrite。
- 当前发布时间锚点太实，特指“最近/现在/目前/今天/这几天/这阵”绑定换季、流感、季节、降温、入冬/入夏/入秋、天冷等季节/疾病大环境；不要因为昨天、刚拆快递、刚补货、家里剩半罐、班里请假、最近出勤稳这类生活记录口吻就判 rewrite。
- 正文像在把业务规则翻译成人话：先说一个很薄的生活入口，马上转成“选儿童奶粉会看某方向/这个产品依据我记住/这个营养我会优先考虑”，缺少真实发帖动作里的纠结、问答、对比残缺或记录语境。单独一句具体成分大白话，例如“钙铁锌看着挺全/DHA和燕窝酸写得清楚”，不按这一条判 rewrite。

通常可判 pass 或 minor 的情况：
- 问题解决型里，只写一个吃饭/活动/接触场景，然后带出旺玥作为日常营养补充安排，并给一个正向变化，例如状态稳、精神头足、身子骨扎实；没有继续补孩子接受度、价格、复购、妈妈安心。
- 选奶复盘型里，有生活触发、选择依据和自家反馈；即使反馈不止一个，或有“没换过/朋友觉得还行/饭菜不稳”这种真人毛边或轻收口，只要没有变成品牌式保证，可判 pass 或 minor。
- 复购/长期使用型里，补货、孩子愿意喝、状态反馈可以出现，但不要同时扩成专业对比和妈妈安心模板；轻微完整但真实、有种草力时优先 minor。
- 标题只是普通生活问题短句，哪怕不惊艳，也不用为了更会写而强制改。

按帖子类型判断：
- 对比选择/选奶复盘：允许更多选择依据，但不能同时堆满问题、做功课、配方、价格、孩子接受、继续喝、妈妈安心。
- 复购/长期使用：允许补货、使用履历、一个没断的理由；不需要重新证明为什么买。
- 家庭清单：产品像清单项，解释很少才自然。
- 问题解决：先有生活困扰，产品只是处理链路的一环，不能变成唯一答案。
- 使用反馈：允许当前安排和一个正向感受，不要写完整购买复盘。
- 轻测评：允许一个观察点或一个产品点，不要堆参数。

业务入池三档：
- business_usability_tier 是以后程序统计的唯一人工业务口径，不要再另起一套“人工可用”规则。
- direct_pool：可直接入池。产品事实正确；痛点、卖点、成分、正向证据匹配；文本无明显病句/断句；种草力明确；没有隐性负面、过度安全降调、模板收口或强因果风险。
- light_fix_usable：轻修可用。种草内核成立，产品事实没错，正向价值值得保留；但有局部问题，例如错字、断句、旧模板词、标题一般、篇幅太短、轻微因果过重、少量合规防守句。它不是废稿，也不等于必须整篇重写；优先局部轻修。
- hold_out：暂不入池。产品事实错、低龄使用、产品形态错、季节/流感等禁用锚点、医疗/保证/治疗倾向、隐性负面，或文本断裂到影响理解；机器修复后仍未过也应归入这一档。
- tier 和 severity 相关但不完全相同：minor 通常是 light_fix_usable；rewrite/hard 通常是 hold_out；pass 里如果有明显错字/断句/弱种草，也可以给 light_fix_usable 并在 business_usability_reason 里说明。

输出严格 JSON，不要 Markdown：
{
  "pass": true,
  "rewrite_required": false,
  "severity": "pass|minor|rewrite|hard",
  "business_usability_tier": "direct_pool|light_fix_usable|hold_out",
  "business_usability_reason": "按入池三档解释为什么属于这一档",
  "issues": [
    {
      "code": "overcomplete_decision_chain|brief_translation_tone|unnatural_product_appearance|weak_product_value|ad_like_closure|claim_risk|post_type_mismatch|wangyue_age_stage_error|child_formula_operation_error|formula_dry_powder_ingestion|formula_usage_form_error|portable_product_error|supplement_replacement_error|other",
      "evidence": "原文片段",
      "reason": "为什么这个上下文里不自然",
      "rewrite_direction": "怎么改，必须保留正面产品价值"
    }
  ],
  "product_appearance_naturalness": 1,
  "decision_chain_fit": 1,
  "product_value_strength": 1,
  "human_realness": 1,
  "overall_reason": "一句话总结"
}

打分要求：低分用于解释风险，不自动等于 rewrite。只有产品出现自然度、人味、产品价值或风险项显示“不改不能用”时才 rewrite；decision_chain_fit 单项低分通常只给 minor 或批量分布提醒。不要给明显广告链路打 5 分。
"""
