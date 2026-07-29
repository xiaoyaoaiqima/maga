"""Deterministic fact guard for a2 礼遇 batch-detection wording."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


A2_REIYU_ARTICLE_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"

_SENTENCE_SPLIT_RE = re.compile(r"[\n。！？!?；;]+")
_PER_CAN_DETECTION_PATTERNS = (
    re.compile(r"每(?:一)?罐(?:都|也)?(?:有|做|经过|要做)?(?:严格)?(?:的)?(?:检测|检验|质检)"),
    re.compile(r"每(?:一)?罐(?:都|也)?(?:会|要)?查(?!到|询)"),
    re.compile(r"(?:一罐一检|逐罐(?:检测|检验|质检)|罐罐(?:检测|检验|质检))"),
    re.compile(r"从[^，。！？；;\n]{1,10}到[^，。！？；;\n]{1,10}(?:都|全)(?:查|检)"),
)
_BATCH_DETECTION_CUE = re.compile(
    r"(?:每(?:一)?批[^，。！？；;\n]{0,6}(?:检测|检验|质检)|批次(?:检测|检验|质检)|批批检)"
)
_CAUSAL_CONNECTOR = re.compile(r"所以|因此|怪不得|难怪|说明|证明|这下(?:就)?")
_BABY_EFFECT_CUE = re.compile(
    r"长肉|长势|肉嘟嘟|小脸(?:圆|胖)|吸收|消化|肚肚|肠胃|胃口|爱喝|喝得香|接受度|"
    r"睡眠|睡得|抵抗力|体质|少生病|少中招|不容易感冒"
)
_ALLOWED_RECOGNITION_BRIDGE = re.compile(
    r"安心|放心|踏实|心里有底|品质|品控|质量|标准|透明|认真|靠谱|品牌|a2"
)


@dataclass(frozen=True)
class A2ReiyuBatchDetectionGuardReview:
    pass_: bool
    hits: list[str]
    issue_code: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "rewrite_required": False,
            "severity": "pass" if self.pass_ else "hard",
            "business_usability_tier": "direct_pool" if self.pass_ else "hold_out",
            "issue_code": self.issue_code,
            "hits": self.hits,
            "reason": (
                "未发现每批检测事实扩写或检测与宝宝效果的错误因果。"
                if self.pass_
                else (
                    "正文把已确认的每批检测扩写成逐罐检测或未经素材支持的检测流程细节。"
                    if self.issue_code == "batch_detection_fact_error"
                    else "正文用因果连接把每批检测直接解释成宝宝使用效果。"
                )
            ),
        }


def review_a2_reiyu_batch_detection_fact(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any] | None,
) -> A2ReiyuBatchDetectionGuardReview:
    if str((plan or {}).get("asset_key") or "") != A2_REIYU_ARTICLE_ASSET_KEY:
        return A2ReiyuBatchDetectionGuardReview(pass_=True, hits=[])

    text = f"{title or ''}\n{body or ''}"
    sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(text) if sentence.strip()]
    fact_hits = [
        sentence
        for sentence in sentences
        if any(pattern.search(sentence) for pattern in _PER_CAN_DETECTION_PATTERNS)
    ]
    if fact_hits:
        return A2ReiyuBatchDetectionGuardReview(
            pass_=False,
            hits=list(dict.fromkeys(fact_hits)),
            issue_code="batch_detection_fact_error",
        )

    causality_hits: list[str] = []
    for index, sentence in enumerate(sentences):
        detection = _BATCH_DETECTION_CUE.search(sentence)
        if detection is None:
            continue
        for offset, candidate in enumerate(sentences[index : index + 3]):
            search_text = candidate[detection.end() :] if offset == 0 else candidate
            connector = _CAUSAL_CONNECTOR.search(search_text)
            if connector is None:
                continue
            after_connector = search_text[connector.end() :]
            effect = _BABY_EFFECT_CUE.search(after_connector)
            if effect is None:
                continue
            has_recognition_bridge = _ALLOWED_RECOGNITION_BRIDGE.search(
                after_connector[: effect.start()]
            )
            if has_recognition_bridge and (offset == 0 or connector.start() > 0):
                continue
            causality_hits.append("。".join(sentences[index : index + offset + 1]))
            break

    if causality_hits:
        return A2ReiyuBatchDetectionGuardReview(
            pass_=False,
            hits=list(dict.fromkeys(causality_hits)),
            issue_code="batch_detection_effect_causality",
        )
    return A2ReiyuBatchDetectionGuardReview(pass_=True, hits=[])
