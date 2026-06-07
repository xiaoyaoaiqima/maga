"""Extract reusable writing-pattern assets from MAGA reference examples.

This is an offline/background utility for the MVP asset-training loop:
MAGA keeps raw `reference_examples` for traceability, and this script turns
them into structured `reference_writing_patterns` candidate assets that can
later be reviewed/promoted and used by the batch planner.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.llm_provider_config import LLMProviderConfig
from app.models.maga_assets import AssetRegistry


PATTERN_ASSET_TYPE = "reference_writing_patterns"
REFERENCE_ASSET_TYPE = "reference_examples"
SYSTEM_PROMPT = """你是小红书母婴种草内容的写法拆解专家。
你的任务是把一篇参考例文拆成可复用的“写法资产”，只抽象结构、语气和表达策略，不复制原文。

要求：
- 不要把例文里的产品效果、事实宣称当成事实来源。
- 识别适配的主题、人群、风格，但不要过度发散。
- 输出的 pattern 要能被后续生文排列组合使用。
- avoid_copy_phrases 只放高辨识度、后续应禁止复用的短语或短句。

只输出合法 JSON，不要 Markdown，不要 JSON 外解释。字段必须包含：
{
  "topic_fit": ["..."],
  "audience_fit": ["..."],
  "style_fit": ["..."],
  "opening_pattern": "...",
  "story_arc": "...",
  "selling_point_placement": "...",
  "proof_style": "...",
  "ending_pattern": "...",
  "voice_traits": ["..."],
  "emotion_intensity": "low|medium|high",
  "avoid_copy_phrases": ["..."],
  "risk_notes": ["..."]
}
"""


@dataclass(frozen=True)
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = 120


async def main() -> None:
    args = build_parser().parse_args()
    engine = create_async_engine(args.database_url or database_url_from_env(), echo=False, future=True)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            config = await resolve_model_config(session, model=args.model)
            source_asset = await latest_asset(session, REFERENCE_ASSET_TYPE, args.asset_key)
            if source_asset is None:
                raise RuntimeError(f"missing {REFERENCE_ASSET_TYPE} asset for {args.asset_key}")
            examples = content_items(source_asset.content_json)
            if args.limit:
                examples = examples[: args.limit]
            if not examples:
                raise RuntimeError(f"empty {REFERENCE_ASSET_TYPE} asset for {args.asset_key}")

            print(
                f"extracting {len(examples)} reference examples from asset #{source_asset.id} "
                f"with model {config.model}",
                flush=True,
            )
            patterns: list[dict[str, Any]] = []
            for index, example in enumerate(examples, start=1):
                pattern = await extract_pattern_with_retry(config, example, index=index)
                patterns.append(pattern)
                write_checkpoint(args.checkpoint_path, patterns)
                print(
                    f"[{index}/{len(examples)}] {pattern.get('pattern_id')} "
                    f"{pattern.get('opening_pattern')}",
                    flush=True,
                )

            if args.dry_run:
                print(json.dumps({"items": patterns}, ensure_ascii=False, indent=2), flush=True)
                return

            target = await upsert_candidate_asset(
                session,
                asset_key=args.asset_key,
                source_asset=source_asset,
                patterns=patterns,
                created_by=args.created_by,
            )
            await session.commit()
            print(
                f"created {PATTERN_ASSET_TYPE} candidate asset #{target.id} "
                f"v{target.version_no}, items={len(patterns)}",
                flush=True,
            )
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract reference writing patterns into asset_registry.")
    parser.add_argument("--database-url", default=None, help="Async SQLAlchemy database URL")
    parser.add_argument("--asset-key", default="yuanyue")
    parser.add_argument("--model", default=None, help="Override model code/name")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--created-by", default="background-pattern-extractor")
    parser.add_argument(
        "--checkpoint-path",
        default=".local/logs/reference-writing-patterns.checkpoint.json",
        help="Write extracted patterns after each item so long jobs can be inspected/resumed manually.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def database_url_from_env() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "maga")
    password = os.getenv("MYSQL_PASSWORD", "maga123456")
    database = os.getenv("MYSQL_DATABASE", "maga")
    return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"


async def resolve_model_config(session: AsyncSession, *, model: str | None = None) -> ModelConfig:
    result = await session.execute(
        select(LLMProviderConfig)
        .where(
            LLMProviderConfig.enabled == 1,
            LLMProviderConfig.is_deleted == 0,
            LLMProviderConfig.api_key.is_not(None),
            LLMProviderConfig.api_key != "",
        )
        .order_by(LLMProviderConfig.priority.desc(), LLMProviderConfig.id.asc())
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if provider:
        return ModelConfig(
            api_key=provider.api_key or "",
            base_url=provider.base_url,
            model=model or provider.default_model or os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash",
            timeout=provider.timeout or 120,
        )

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AIHUBMIX_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("AIHUBMIX_API_URL") or "https://aihubmix.com/v1"
    if not api_key:
        raise RuntimeError("missing model api key: configure model management or OPENAI_API_KEY/AIHUBMIX_API_KEY")
    return ModelConfig(
        api_key=api_key,
        base_url=base_url,
        model=model or os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash",
    )


async def latest_asset(session: AsyncSession, asset_type: str, asset_key: str) -> AssetRegistry | None:
    result = await session.execute(
        select(AssetRegistry)
        .where(
            AssetRegistry.asset_type == asset_type,
            AssetRegistry.asset_key == asset_key,
            AssetRegistry.asset_stage == "production",
            AssetRegistry.status == "active",
        )
        .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def content_items(content: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = (content or {}).get("items")
    return [item for item in items or [] if isinstance(item, dict)]


async def extract_pattern(config: ModelConfig, example: dict[str, Any], *, index: int) -> dict[str, Any]:
    prompt = json.dumps(
        {
            "source_example_id": example.get("example_id") or f"reference_example_{index}",
            "title": example.get("title") or "",
            "body": example.get("body") or example.get("content") or "",
            "metadata": {
                "direction": example.get("direction"),
                "painpoint": example.get("painpoint"),
                "post_format": example.get("post_format"),
                "style_tags": example.get("style_tags"),
            },
        },
        ensure_ascii=False,
    )
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1800,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.post(
            normalize_chat_completions_url(config.base_url),
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    parsed = parse_json_object(raw)
    return normalize_pattern(example, parsed, index=index)


async def extract_pattern_with_retry(config: ModelConfig, example: dict[str, Any], *, index: int) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return await extract_pattern(config, example, index=index)
        except Exception as exc:  # noqa: BLE001 - background jobs should keep moving per item.
            last_error = exc
            print(f"[{index}] extract attempt {attempt} failed: {exc}", flush=True)
            await asyncio.sleep(min(attempt * 1.5, 5))

    fallback = fallback_pattern(example, index=index)
    fallback["risk_notes"].append(f"AI拆解失败，使用规则兜底：{last_error}")
    return fallback


def normalize_pattern(example: dict[str, Any], parsed: dict[str, Any], *, index: int) -> dict[str, Any]:
    source_example_id = str(example.get("example_id") or f"reference_example_{index}")
    return {
        "pattern_id": f"wp_{source_example_id}",
        "source_example_id": source_example_id,
        "source_title": example.get("title") or "",
        "topic_fit": ensure_list(parsed.get("topic_fit")),
        "audience_fit": ensure_list(parsed.get("audience_fit")),
        "style_fit": ensure_list(parsed.get("style_fit")),
        "opening_pattern": str(parsed.get("opening_pattern") or "").strip(),
        "story_arc": str(parsed.get("story_arc") or "").strip(),
        "selling_point_placement": str(parsed.get("selling_point_placement") or "").strip(),
        "proof_style": str(parsed.get("proof_style") or "").strip(),
        "ending_pattern": str(parsed.get("ending_pattern") or "").strip(),
        "voice_traits": ensure_list(parsed.get("voice_traits")),
        "emotion_intensity": str(parsed.get("emotion_intensity") or "medium").strip(),
        "avoid_copy_phrases": ensure_list(parsed.get("avoid_copy_phrases"))[:8],
        "risk_notes": ensure_list(parsed.get("risk_notes")),
        "review_status": "pending",
        "pattern_source": "ai_extracted",
    }


def fallback_pattern(example: dict[str, Any], *, index: int) -> dict[str, Any]:
    source_example_id = str(example.get("example_id") or f"reference_example_{index}")
    title = str(example.get("title") or "").strip()
    body = str(example.get("body") or example.get("content") or "").strip()
    first_sentence = first_text_unit(body)
    return {
        "pattern_id": f"wp_{source_example_id}",
        "source_example_id": source_example_id,
        "source_title": title,
        "topic_fit": ensure_list(example.get("painpoint")),
        "audience_fit": [],
        "style_fit": ensure_list(example.get("style_tags")),
        "opening_pattern": f"以“{first_sentence[:36]}”这类具体场景开头" if first_sentence else "以具体妈妈场景开头",
        "story_arc": "痛点场景 -> 个人观察 -> 选择逻辑 -> 轻建议",
        "selling_point_placement": "正文中段结合选择逻辑自然带出",
        "proof_style": "日常观察记录",
        "ending_pattern": "给同类妈妈一个轻建议",
        "voice_traits": ["口语", "真实", "妈妈视角"],
        "emotion_intensity": "medium",
        "avoid_copy_phrases": distinctive_phrases(title, body),
        "risk_notes": ["规则兜底拆解，需要人工复核"],
        "review_status": "pending",
        "pattern_source": "fallback_extracted",
    }


def first_text_unit(text: str) -> str:
    compact = " ".join(text.split())
    parts = re.split(r"[。！？!?；;\n]", compact)
    return next((part.strip() for part in parts if part.strip()), compact[:60])


def distinctive_phrases(title: str, body: str) -> list[str]:
    phrases: list[str] = []
    if title:
        phrases.append(title[:24])
    for sentence in re.split(r"[。！？!?；;\n]", body):
        sentence = sentence.strip()
        if 8 <= len(sentence) <= 30:
            phrases.append(sentence)
        if len(phrases) >= 6:
            break
    return phrases


async def upsert_candidate_asset(
    session: AsyncSession,
    *,
    asset_key: str,
    source_asset: AssetRegistry,
    patterns: list[dict[str, Any]],
    created_by: str,
) -> AssetRegistry:
    result = await session.execute(
        select(AssetRegistry)
        .where(
            AssetRegistry.asset_type == PATTERN_ASSET_TYPE,
            AssetRegistry.asset_key == asset_key,
            AssetRegistry.asset_stage == "candidate",
        )
        .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
        .limit(1)
    )
    previous = result.scalar_one_or_none()
    version_no = (previous.version_no + 1) if previous else 1
    asset = AssetRegistry(
        asset_type=PATTERN_ASSET_TYPE,
        asset_key=asset_key,
        display_name="参考例文写法资产",
        version_no=version_no,
        status="active",
        asset_stage="candidate",
        source_name=f"{REFERENCE_ASSET_TYPE}:{source_asset.id}",
        source_uri=None,
        source_hash=source_asset.source_hash,
        content_json={
            "items": patterns,
            "source_asset_id": source_asset.id,
            "source_asset_version": source_asset.version_no,
        },
        metadata_json={"extractor": "reference_writing_patterns_v1"},
        created_by=created_by,
    )
    session.add(asset)
    await session.flush()
    return asset


def normalize_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response is not a JSON object")
    return value


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def write_checkpoint(path: str | None, patterns: list[dict[str, Any]]) -> None:
    if not path:
        return
    checkpoint = Path(path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps({"items": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
