"""Resolved prompt profiles for bounded comment-generation experiments."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


MAGA_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ResolvedCommentExperimentProfile:
    profile_code: str
    profile_version: str
    label: str
    asset_key: str
    prompt_path: str
    prompt_text: str
    output_format_mode: str
    output_count: int
    model_config: dict[str, Any]

    def snapshot(self) -> dict[str, Any]:
        return {
            "profile_code": self.profile_code,
            "profile_version": self.profile_version,
            "label": self.label,
            "asset_key": self.asset_key,
            "prompt_path": self.prompt_path,
            "prompt_sha256": sha256(self.prompt_text.encode("utf-8")).hexdigest(),
            "output_format_mode": self.output_format_mode,
            "output_count": self.output_count,
            "model_config": dict(self.model_config),
        }

    def generation_rule(self) -> dict[str, Any]:
        return {
            "rule_id": f"experiment:{self.profile_code}:{self.profile_version}",
            "business_rule": self.label,
            # ContentCommentBatchService only accepts usable rules with a non-empty corpus.
            # The complete prompt below is the actual model-visible instruction.
            "corpus": self.label,
            "prompt_mode": "complete_comment_prompt",
            "complete_comment_prompt": self.prompt_text,
            "output_format_mode": self.output_format_mode,
            "expansion_count": self.output_count,
            "experiment_profile": self.snapshot(),
            "model_config": dict(self.model_config),
        }


@dataclass(frozen=True)
class CommentExperimentProfileDefinition:
    profile_code: str
    profile_version: str
    label: str
    asset_key: str
    prompt_path: str
    output_format_mode: str
    output_count: int
    model_config: dict[str, Any]

    def resolve(self) -> ResolvedCommentExperimentProfile:
        absolute_path = MAGA_ROOT / self.prompt_path
        prompt_text = absolute_path.read_text(encoding="utf-8").strip()
        if not prompt_text:
            raise ValueError(f"comment experiment prompt is empty: {self.prompt_path}")
        return ResolvedCommentExperimentProfile(
            profile_code=self.profile_code,
            profile_version=self.profile_version,
            label=self.label,
            asset_key=self.asset_key,
            prompt_path=self.prompt_path,
            prompt_text=prompt_text,
            output_format_mode=self.output_format_mode,
            output_count=self.output_count,
            model_config=dict(self.model_config),
        )


COMMENT_EXPERIMENT_PROFILES: tuple[CommentExperimentProfileDefinition, ...] = (
    CommentExperimentProfileDefinition(
        profile_code="a2_stock_comment_batch10_v1",
        profile_version="1",
        label="A2有货评论一次生成10条",
        asset_key="a2_sentiment_comment_activity",
        prompt_path="prompts/a2舆情改善评论-批量生成-提示词.md",
        output_format_mode="json_object_items",
        output_count=10,
        model_config={
            "temperature": 0.9,
            "max_tokens": 1200,
            "system_prompt": "你是严格遵守批次约束的中文社区评论写手。",
        },
    ),
)


class CommentExperimentProfileService:
    def __init__(self) -> None:
        self._profiles = {profile.profile_code: profile for profile in COMMENT_EXPERIMENT_PROFILES}

    def require_profile(self, profile_code: str) -> ResolvedCommentExperimentProfile:
        normalized = str(profile_code or "").strip()
        definition = self._profiles.get(normalized)
        if not definition:
            raise ValueError(f"unknown comment experiment profile: {profile_code}")
        return definition.resolve()
