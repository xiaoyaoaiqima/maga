"""MAGA worker xhs runtime.

The worker code is versioned in the MAGA repo. Profile files under
`worker/profiles/maga-worker` are static inputs; runtime traces are written to
`.local/worker/outputs` or the invocation work_dir.
"""
from __future__ import annotations

import datetime
import json
import os
import random
import re
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI

# ─────────────────── 路径常量 ───────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = Path(os.environ.get("WORKER_WORKSPACE") or REPO_ROOT / "worker" / "profiles" / "maga-worker")
WS      = PROFILE
EXPERTS = WS / "experts"
GE_DIR  = WS / "ge_writer"
CAMP    = WS / "campaigns" / "_current"
OUTPUT_ROOT = Path(os.environ.get("MAGA_WORKER_OUTPUT_DIR") or REPO_ROOT / ".local" / "worker" / "outputs")
NOTES   = OUTPUT_ROOT / "notes"
_PROMPT_BUNDLE_ENV = "XHS_RUNTIME_PROMPT_BUNDLE_JSON"

# ─────────────────── 模型常量 (Volcengine Ark — Coding Plan) ───────────────────
MODEL_GE = "deepseek-v3-2-251201"           # GE 生文 — DeepSeek v3.2
MODEL_AE = "doubao-seed-2-0-mini-260428"    # AE 调用 — Doubao Seed 2.0 Mini

ARK_CODING_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"

# ─────────────────── OpenAI-compatible provider config ───────────────────
def runtime_base_url() -> str:
    """Resolve OpenAI-compatible base URL for xhs runtime.

    Defaults remain Ark-compatible, but MAGA/xhs-writer integration can point the
    runtime at the same OpenAI-compatible provider used by Hermes via env.
    """
    return (
        os.environ.get("XHS_RUNTIME_BASE_URL")
        or os.environ.get("ARK_BASE_URL")
        or os.environ.get("HERMES_MODEL_BASE_URL")
        or ARK_CODING_BASE_URL
    )


def runtime_api_key() -> str | None:
    return (
        os.environ.get("XHS_RUNTIME_API_KEY")
        or os.environ.get("CUSTOM_API_KEY")
        or os.environ.get("ARK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def model_ge() -> str:
    return os.environ.get("XHS_RUNTIME_MODEL_GE") or MODEL_GE


def model_ae() -> str:
    return os.environ.get("XHS_RUNTIME_MODEL_AE") or MODEL_AE


# ─────────────────── OpenAI client ───────────────────
def openai_client_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "api_key": runtime_api_key(),
        "base_url": runtime_base_url(),
    }
    timeout_raw = os.environ.get("XHS_RUNTIME_TIMEOUT", "90")
    try:
        kwargs["timeout"] = float(timeout_raw)
    except ValueError:
        kwargs["timeout"] = 90.0
    if "api.lyston.qzz.io" in runtime_base_url().lower():
        kwargs["default_headers"] = {"User-Agent": "curl/8.7.1"}
    return kwargs


def _client() -> OpenAI:
    return OpenAI(**openai_client_kwargs())


def runtime_prompt_bundle() -> dict[str, Any]:
    raw = os.environ.get(_PROMPT_BUNDLE_ENV)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def bundle_prompt(name: str) -> str:
    item = (runtime_prompt_bundle().get("prompts") or {}).get(name) or {}
    content = item.get("content") if isinstance(item, dict) else None
    return str(content) if content else ""


def bundle_asset_content(asset_type: str, asset_key: str) -> Any:
    item = (runtime_prompt_bundle().get("assets") or {}).get(f"{asset_type}:{asset_key}") or {}
    if not isinstance(item, dict):
        return None
    content_json = item.get("content_json")
    if isinstance(content_json, dict) and "content" in content_json:
        return content_json.get("content")
    return content_json


def ge_prompt_parts() -> tuple[str, str, str]:
    system = bundle_prompt("xhs_writer.ge.system") or (PROFILE / "system.md").read_text(encoding="utf-8")
    style = bundle_prompt("xhs_writer.ge.style_templates")
    if not style and (GE_DIR / "style_templates.md").exists():
        style = (GE_DIR / "style_templates.md").read_text(encoding="utf-8")
    voice = bundle_prompt("xhs_writer.ge.voice_dictionary")
    if not voice and (GE_DIR / "voice_dictionary.md").exists():
        voice = (GE_DIR / "voice_dictionary.md").read_text(encoding="utf-8")
    return system, style, voice


# ─────────────────── 模型调用 ───────────────────
def call_model(model: str, system: str, user: str, temperature: float = 0.7) -> str:
    """单次模型调用，返回纯文本。失败重试 3 次。"""
    last_err: Exception | None = None
    for _ in range(3):
        try:
            resp = _client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            last_err = e
    raise RuntimeError(f"call_model failed after 3 retries: {last_err}") from last_err


# ─────────────────── YAML 鲁棒解析 ───────────────────
_FENCE = re.compile(r"^```(?:yaml|yml)?\s*\n(.*?)\n```\s*$", re.DOTALL | re.IGNORECASE)


def parse_yaml_loose(text: str) -> dict | list | str:
    """容错 YAML 解析：剥 markdown fence、剥前后噪声、parse 失败时返回 {_raw: text}。"""
    if not text:
        return {}
    text = text.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    # 也处理只有起始 fence 没结尾的
    text = re.sub(r"^```(?:yaml|yml)?\s*\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n```\s*$", "", text)
    try:
        result = yaml.safe_load(text)
        return result if result is not None else {}
    except yaml.YAMLError as e:
        return {"_raw": text, "_parse_error": str(e)}


# ─────────────────── 语料抽样 ───────────────────
def sample_corpus(corpus: dict, brief: dict) -> dict:
    """按 corpus.output_mode 抽样语料。"""
    mode = corpus.get("output_mode")
    out: dict = {}
    for l1_name, group in (corpus.get("groups") or {}).items():
        items = (group or {}).get("items") or []
        if not items:
            continue
        if mode == "fixed":
            out[l1_name] = items
        elif mode == "random":
            out[l1_name] = random.sample(items, min(2, len(items)))
        elif mode == "ratio_random":
            ratios = brief.get("painpoint_ratio") if (
                corpus.get("expert") == "painpoint_selling" and l1_name == "痛点"
            ) else None
            if ratios:
                picked = []
                for cat, weight in ratios.items():
                    cat_items = [it for it in items if cat in (it.get("l2") or "")]
                    if cat_items:
                        n = max(1, int(round(weight * 3)))
                        picked.extend(random.sample(cat_items, min(n, len(cat_items))))
                out[l1_name] = picked or random.sample(items, min(3, len(items)))
            else:
                out[l1_name] = random.sample(items, min(3, len(items)))
        elif mode == "mixed":
            out[l1_name] = items[: min(5, len(items))]
        else:
            out[l1_name] = items[:5]
    return out


# ─────────────────── AE 调用 ───────────────────
def call_ae(ae: str, mode: str, brief: dict, draft: str | None = None,
            debug_dir: Path | None = None, tag: str = "") -> dict:
    """跑一次 AE：mode='instruct' 输出指令；mode='score' 输出评分。

    若提供 debug_dir，会落盘 prompt + raw_response + parsed yaml 三件套。
    """
    system_path = EXPERTS / ae / "system.md"
    corpus_path  = EXPERTS / ae / "corpus.yaml"
    rubric_path  = EXPERTS / ae / "score_rubric.md"

    system = bundle_prompt(f"xhs_writer.ae.{ae}.system")
    if not system and not system_path.exists():
        return {"_skipped": True, "reason": f"{ae}/system.md missing"}

    if not system:
        system = system_path.read_text(encoding="utf-8")
    corpus_from_bundle = bundle_asset_content("expert_corpus", ae)
    corpus = corpus_from_bundle if isinstance(corpus_from_bundle, dict) else None
    if corpus is None:
        corpus = yaml.safe_load(corpus_path.read_text(encoding="utf-8")) if corpus_path.exists() else {}
    sampled = sample_corpus(corpus, brief)
    rubric = bundle_prompt(f"xhs_writer.ae.{ae}.score_rubric")
    if not rubric:
        rubric = rubric_path.read_text(encoding="utf-8") if rubric_path.exists() else ""

    user_parts = [
        f"## 当前 Brief\n```yaml\n{yaml.dump(brief, allow_unicode=True, default_flow_style=False)}\n```",
        f"## 抽样语料 (output_mode={corpus.get('output_mode')})\n```yaml\n{yaml.dump(sampled, allow_unicode=True, default_flow_style=False)}\n```",
    ]
    if mode == "score":
        user_parts.append(f"## 待评分草稿\n```\n{draft}\n```")
        if rubric:
            user_parts.append(f"## 评分规则\n{rubric}")
        user_parts.append(
            "请严格按 system.md 中【输出契约 - 生文后(评分模式)】的 yaml 结构输出。"
            "**只输出 yaml 内容本身，不要 markdown 代码块标记，不要任何前后说明文字。**"
        )
    else:
        user_parts.append(
            "请严格按 system.md 中【输出契约 - 生文前(指令模式)】的 yaml 结构输出。"
            "**只输出 yaml 内容本身，不要 markdown 代码块标记，不要任何前后说明文字。**"
        )
    user_text = "\n\n".join(user_parts)

    text = call_model(model_ae(), system=system, user=user_text,
                      temperature=0.3 if mode == "score" else 0.5)
    parsed = parse_yaml_loose(text)
    result = parsed if isinstance(parsed, dict) else {"_raw": text}

    if debug_dir is not None:
        suffix = f"-{tag}" if tag else ""
        prompt_path = debug_dir / f"ae-{ae}-{mode}{suffix}.prompt.md"
        raw_path    = debug_dir / f"ae-{ae}-{mode}{suffix}.response.txt"
        out_path    = debug_dir / f"ae-{ae}-{mode}{suffix}.parsed.yaml"
        prompt_path.write_text(
            f"# AE: {ae} | mode: {mode}{(' | tag: '+tag) if tag else ''}\n\n"
            f"## SYSTEM (system.md)\n\n{system}\n\n"
            f"---\n\n## USER\n\n{user_text}\n",
            encoding="utf-8")
        raw_path.write_text(text, encoding="utf-8")
        out_path.write_text(
            yaml.dump(result, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8")

    return result


# ─────────────────── 冲突检测 + 收敛 spec ───────────────────
def collect_hard_blocklist(ae_outputs: dict[str, dict]) -> list[str]:
    """从 legal/platform/brand 三个必选 AE 收集所有红线词。"""
    block: set[str] = set()
    for ae, key in [
        ("legal",    "hard_blocklist"),
        ("platform", "platform_blocklist"),
        ("brand",    "brand_blocklist"),
    ]:
        words = (ae_outputs.get(ae) or {}).get(key) or []
        block.update(w for w in words if isinstance(w, str))
    return sorted(block)


def detect_conflicts(ae_outputs: dict[str, dict], hard_block: list[str]) -> list[tuple[str, str, str]]:
    """简单的规则比较 — 仅检测最常见的冲突。"""
    conflicts: list[tuple[str, str, str]] = []
    ps = ae_outputs.get("painpoint_selling") or {}
    for sp_group in ps.get("selected_sellingpoints") or []:
        for w in hard_block:
            if w and any(w in str(it) for it in (sp_group.get("items") or [])):
                conflicts.append(("painpoint_selling", "legal/platform/brand", f"卖点含红线词 {w}"))
    return conflicts


def build_writing_spec(brief: dict, ae_outputs: dict[str, dict], hard_block: list[str]) -> str:
    pas = ae_outputs.get("painpoint_selling") or {}
    cs  = ae_outputs.get("content_structure") or {}
    persona = ae_outputs.get("persona") or {}
    brand   = ae_outputs.get("brand") or {}
    camp    = brief.get("campaign") or {}

    # New online-prompt-derived AE set.
    brief_i = ae_outputs.get("brief_interpreter") or {}
    p_anchor = ae_outputs.get("painpoint_anchor") or {}
    sp_logic = ae_outputs.get("sellingpoint_logic") or {}
    narrative = ae_outputs.get("narrative_strategy") or {}
    pov = ae_outputs.get("persona_pov") or {}
    brand_guard = ae_outputs.get("brand_product_guard") or {}
    compliance = ae_outputs.get("compliance_redline") or {}
    xhs = ae_outputs.get("xhs_structure") or {}
    natural = ae_outputs.get("naturalness_ai_smell") or {}

    def _yaml(x):
        return yaml.dump(x, allow_unicode=True, default_flow_style=False).strip() if x else "(空)"

    if any([brief_i, p_anchor, sp_logic, narrative, pov, brand_guard, compliance, xhs, natural]):
        return f"""# Writing Spec — {brief.get('brief_id')}

## 任务归一
{_yaml(brief_i)}

## 痛点分类与首个卖点锚点
{_yaml(p_anchor)}

## 卖点展开与因果链
{_yaml(sp_logic)}

## 叙事路径与扰动
{_yaml(narrative)}

## 人设视角
{_yaml(pov)}

## 品牌与产品表达硬规则
{_yaml(brand_guard)}

## 合规红线
{_yaml(compliance)}

## 小红书结构 / 标题 / emoji / 输出格式
{_yaml(xhs)}

## 自然度与 AI 味控制
{_yaml(natural)}

## brief 原始输入（不可扩写，不可自行新增卖点/功效）
{_yaml(brief)}

## 红线词（绝对不能出现）
{chr(10).join('- ' + w for w in hard_block) or '(空)'}

## 生成要求
- 直接输出笔记，格式必须为：标题：[标题] 换行 正文：[正文]
- 禁止输出 hashtag、话题 tag、markdown、xml、括号、#、*。
- 不要输出 AE 名称、路径选择结果、规则解释或自检过程。
"""

    return f"""# Writing Spec — {brief.get('brief_id')}

## 必带元素
- 关键词: {camp.get('must_keywords', [])}
- 活动话术: {camp.get('must_messages', [])}
- 品牌识别词: {brand.get('must_mentions') or []}

## 红线词（绝对不能出现）
{chr(10).join('- ' + w for w in hard_block) or '(空)'}

## 痛点配比
{_yaml(pas.get('selected_painpoints'))}

## 卖点
{_yaml(pas.get('selected_sellingpoints'))}

## 产品事实
{_yaml(pas.get('product_facts'))}

## 人设 / 调性
- 人设: {persona.get('selected_persona') or persona.get('persona') or persona.get('identity') or ''}
- 沟通风格: {persona.get('voice') or persona.get('communication_style') or ''}
- 品牌调性: {brand.get('brand_tone') or []}

## 结构 / 字数 / emoji / 标题
{_yaml(cs)}

## brief 自身的偏好（fallback）
- 字数: {(brief.get('content_structure') or {}).get('word_count')}
- emoji: {(brief.get('content_structure') or {}).get('emoji')}
- 标题风格: {(brief.get('content_structure') or {}).get('title_style')}
"""


# ─────────────────── GE 生文 ───────────────────
def call_ge(brief: dict, spec_md: str, system: str, style: str, voice: str,
            feedback: str | None = None, prev_draft: str | None = None,
            debug_dir: Path | None = None, tag: str = "") -> str:
    sys_prompt = f"""{system}

## 风格模板（参考库）
{style}

## 口语化词典（避坑）
{voice}
"""
    if feedback and prev_draft:
        # 重写：低温度 + 强制保留未命中段落 + 不传 spec（避免重新解释整体）
        user = f"""# 任务：精准修订（**不要整篇重写**）

## 上一版草稿
```
{prev_draft}
```

## 各 AE 反馈（按硬→软排序）
{feedback}

## 修订规则（严格执行）
1. **只修改反馈中明确指出问题的位置**，未提到的段落 / 句子**逐字保留**
2. 不要重新创作开头、不要替换标题（除非反馈明确点名标题）
3. 不要重排段落顺序
4. 不要新增反馈未要求的内容
5. 输出格式与上一版一致（仅标题 + 正文），不要 hashtag / 话题 tag，不要任何前缀/解释

直接输出修订后的整篇笔记。"""
        result = call_model(model_ge(), system=sys_prompt, user=user, temperature=0.3).strip()
    else:
        user = f"""请基于以下 Writing Spec 生成一篇小红书笔记。
**严格遵守红线词与必带元素**。直接输出笔记正文（仅标题 + 正文），不要 hashtag / 话题 tag，不要任何解释/前缀。

{spec_md}"""
        result = call_model(model_ge(), system=sys_prompt, user=user, temperature=0.85).strip()

    if debug_dir is not None:
        suffix = f"-{tag}" if tag else ""
        (debug_dir / f"ge{suffix}.prompt.md").write_text(
            f"# GE call{(' | tag: '+tag) if tag else ''}\n\n"
            f"## SYSTEM\n\n{sys_prompt}\n\n---\n\n## USER\n\n{user}\n",
            encoding="utf-8")
        (debug_dir / f"ge{suffix}.response.md").write_text(result, encoding="utf-8")

    return result


# ─────────────────── 评分聚合 ───────────────────
def aggregate_scores(brief: dict, draft: str, required_aes: list[str],
                     debug_dir: Path | None = None, tag: str = "") -> dict:
    registry_data = bundle_asset_content("expert_registry", "xhs_writer")
    if registry_data is None:
        registry_data = yaml.safe_load((EXPERTS / "_registry.yaml").read_text(encoding="utf-8"))
    registry = (registry_data or {}).get("experts", {})
    results: dict[str, dict] = {}
    scorable_aes = [a for a in required_aes if (registry.get(a) or {}).get("score_type")]
    for ae in scorable_aes:
        results[ae] = call_ae(ae, mode="score", brief=brief, draft=draft,
                              debug_dir=debug_dir, tag=tag)

    hard_aes = [a for a in scorable_aes if (registry.get(a) or {}).get("score_type") == "0/1"]
    soft_aes = [a for a in scorable_aes if (registry.get(a) or {}).get("score_type") == "0-100"]

    hard_pass = all((results.get(a) or {}).get("score") == 1 for a in hard_aes)

    brief_types_data = bundle_asset_content("brief_type_registry", "xhs_writer")
    if brief_types_data is None:
        brief_types_data = yaml.safe_load((EXPERTS / "_brief_types.yaml").read_text(encoding="utf-8"))
    brief_type_cfg = ((brief_types_data or {})
                      .get("brief_types", {})
                      .get(brief.get("brief_type"), {}))
    soft_weights = brief.get("soft_weights") or brief_type_cfg.get("default_soft_weights") or {}
    total_w = sum(soft_weights.get(a, 1) for a in soft_aes) or 1
    soft_score = (sum(((results.get(a) or {}).get("score") or 0) * soft_weights.get(a, 1)
                      for a in soft_aes) / total_w) if soft_aes else 100.0

    suggestions: list[str] = []
    for a in hard_aes:
        if (results.get(a) or {}).get("score") == 0:
            for h in (results[a].get("hits") or results[a].get("hard_hits") or results[a].get("conditional_hits") or []):
                if isinstance(h, dict):
                    suggestions.append(f"[硬-{a}] {h.get('suggestion') or h.get('rule') or h.get('text')}")
                else:
                    suggestions.append(f"[硬-{a}] {h}")
    for a in soft_aes:
        sc = (results.get(a) or {}).get("score") or 0
        if sc < 80:
            for s in (results[a].get("suggestions") or []):
                suggestions.append(f"[软-{a}] {s}")
            for h in (results[a].get("hits") or []):
                if isinstance(h, dict):
                    suggestions.append(f"[软-{a}] {h.get('suggestion') or h.get('rule') or h.get('text')}")
                else:
                    suggestions.append(f"[软-{a}] {h}")

    return {
        "hard_pass": hard_pass,
        "soft_score": round(soft_score, 1),
        "suggestions": suggestions,
        "results": results,
        "hard_aes": hard_aes,
        "soft_aes": soft_aes,
        "scorable_aes": scorable_aes,
    }


# ─────────────────── 写回 lessons (选项 B 自动) ───────────────────
def write_lessons(brief: dict, ae_outputs_instruct: dict, agg: dict, verdict: str, rewrites: int) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    bid = brief["brief_id"]

    for ae, score_result in agg["results"].items():
        ld = EXPERTS / ae / "lessons"
        ld.mkdir(parents=True, exist_ok=True)
        score_value = (score_result or {}).get("score")
        lesson = {
            "brief_id": bid,
            "timestamp": ts,
            "verdict": verdict,
            "rewrites_used": rewrites,
            "final_score": score_value,
            "instruct_input_summary": list((ae_outputs_instruct.get(ae) or {}).keys()),
            "score_hits": (score_result or {}).get("hits"),
            "score_suggestions": (score_result or {}).get("suggestions"),
        }
        (ld / f"{bid}.yaml").write_text(
            yaml.dump(lesson, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8")

    GE_DIR.mkdir(parents=True, exist_ok=True)
    with (GE_DIR / "lessons.md").open("a", encoding="utf-8") as f:
        f.write(f"\n## {bid} ({ts})\n")
        f.write(f"- brief_type: {brief.get('brief_type')}\n")
        f.write(f"- soft_score: {agg['soft_score']:.1f}, hard_pass: {agg['hard_pass']}\n")
        f.write(f"- rewrites: {rewrites}\n")
        f.write(f"- verdict: {verdict}\n")


# ─────────────────── 全链路 trace 摘要 ───────────────────
def _emit_trace(bid: str, brief: dict, ae_outputs: dict, hard_block: list,
                conflicts: list, spec_md: str, decisions: list,
                picked_idx: int, final_draft: str, final_agg: dict,
                verdict: str, debug_dir: Path) -> str:
    """生成单文件全链路报告（中文 markdown），便于一眼看全。"""
    parts: list[str] = []
    parts.append(f"# 🔍 全链路 Trace — {bid}\n")
    parts.append(f"**verdict**: `{verdict}` | **picked**: `v{picked_idx}` | **hard_pass**: `{final_agg['hard_pass']}` | **soft_score**: `{final_agg['soft_score']}`\n")
    parts.append("> 所有原始 prompt/response 在同目录的 `ae-*.prompt.md` `ae-*.response.txt` `ae-*.parsed.yaml` `ge-*.prompt.md` `ge-*.response.md` 里。\n")

    # ── 0) 时序图（mermaid sequence diagram）
    parts.append("\n## 0️⃣ 全流程时序图\n")
    seq_lines = ["```mermaid", "sequenceDiagram"]
    seq_lines.append("    participant U as Brief")
    seq_lines.append("    participant O as Orchestrator")
    seq_lines.append("    participant AE as AE×8 (doubao-mini)")
    seq_lines.append("    participant GE as GE (deepseek-v3.2)")
    seq_lines.append("    participant N as notes/")
    seq_lines.append("")
    seq_lines.append(f"    U->>O: brief.yaml ({brief.get('brief_type')})")
    seq_lines.append(f"    O->>O: 查 _brief_types → {len(ae_outputs)} AE")
    seq_lines.append("    Note over O,AE: Step 3: 并行 instruct")
    for ae in list(ae_outputs.keys()):
        n_keys = len(ae_outputs[ae])
        seq_lines.append(f"    O->>+AE: {ae} (instruct)")
        seq_lines.append(f"    AE-->>-O: {n_keys} 字段")
    seq_lines.append(f"    O->>O: 收集红线词 {len(hard_block)} 个 + 冲突 {len(conflicts)} 个")
    seq_lines.append("    O->>N: spec.md")
    seq_lines.append("    O->>+GE: 生 v0 (spec)")
    seq_lines.append("    GE-->>-O: draft v0")
    for d in decisions:
        seq_lines.append(f"    Note over O,AE: 评分 v{d['rewrite']}")
        seq_lines.append(f"    O->>+AE: 8 AE × score(v{d['rewrite']})")
        hp = "✓" if d["hard_pass"] else "✗"
        seq_lines.append(f"    AE-->>-O: hard={hp} soft={d['soft_score']}")
        if d["action"] == "rewrite":
            seq_lines.append(f"    O->>+GE: 重写 (反馈 top {len(d['top_suggestions'])})")
            seq_lines.append(f"    GE-->>-O: draft v{d['rewrite']+1}")
        else:
            seq_lines.append(f"    Note over O: {d['action']}")
    seq_lines.append(f"    O->>O: best-of-N → v{picked_idx}")
    seq_lines.append(f"    O->>N: final.md ({verdict})")
    seq_lines.append("    O->>N: lessons × 9 写回")
    seq_lines.append("```\n")
    parts.append("\n".join(seq_lines))

    # ── 0.5) 决策流程图（actual path 高亮）
    parts.append("\n## 0️⃣.5 重写决策流程（实际路径高亮）\n")
    flow = ["```mermaid", "flowchart TD"]
    flow.append("    Start([生 v0]) --> Score0[Step 7: 8 AE 评分]")
    last_node = "Score0"
    final_action = decisions[-1]["action"] if decisions else ""
    for i, d in enumerate(decisions):
        node_id = f"V{d['rewrite']}"
        hp = "✓" if d["hard_pass"] else "✗"
        flow.append(f"    {last_node} --> {node_id}[v{d['rewrite']}: hard={hp}, soft={d['soft_score']}]")
        action = d["action"]
        if "accept" in action:
            flow.append(f"    {node_id} --> Pass([✅ pass])")
            flow.append(f"    style {node_id} fill:#90EE90")
            flow.append(f"    style Pass fill:#90EE90")
            last_node = "Pass"
        elif "early-stop" in action:
            flow.append(f"    {node_id} --> Early([⚡ early-stop])")
            flow.append(f"    style {node_id} fill:#FFD700")
            last_node = "Early"
        elif "max_rewrites" in action:
            flow.append(f"    {node_id} --> MaxStop([⚠ max_rewrites])")
            flow.append(f"    style {node_id} fill:#FFB6C1")
            last_node = "MaxStop"
        elif "rewrite" in action:
            rew_node = f"R{d['rewrite']}"
            flow.append(f"    {node_id} --> {rew_node}[Step 8: GE 重写 v{d['rewrite']+1}]")
            last_node = rew_node
    flow.append(f"    {last_node} --> Best{{best-of-N}}")
    flow.append(f"    Best --> Final([Step 9: final = v{picked_idx}])")
    flow.append(f"    style Final fill:#87CEEB")
    flow.append("```\n")
    parts.append("\n".join(flow))

    # ── 1) Brief
    parts.append("\n## 1️⃣ 输入 Brief\n```yaml\n" +
                 yaml.dump(brief, allow_unicode=True, sort_keys=False, default_flow_style=False) +
                 "```\n")

    # ── 2) AE instruct 讨论结果
    parts.append("\n## 2️⃣ AE 委员会讨论（instruct 模式）\n")
    parts.append(f"调用了 {len(ae_outputs)} 个 AE，每个 AE 的输出（截断显示，完整在 `ae-<name>-instruct.parsed.yaml`）：\n")
    for ae, out in ae_outputs.items():
        parts.append(f"\n### 🧠 {ae}")
        out_yaml = yaml.dump(out, allow_unicode=True, sort_keys=False,
                              default_flow_style=False, width=200)
        if len(out_yaml) > 1500:
            out_yaml = out_yaml[:1500] + "\n...(截断)"
        parts.append(f"```yaml\n{out_yaml}\n```")

    # ── 3) 红线词收集 + 冲突
    parts.append("\n## 3️⃣ 收敛阶段 — 红线词 + 冲突检测\n")
    parts.append(f"- 收集到红线词 **{len(hard_block)}** 个")
    if hard_block:
        sample = "、".join(hard_block[:15]) + ("、…" if len(hard_block) > 15 else "")
        parts.append(f"- 抽样: {sample}")
    parts.append(f"- 冲突 **{len(conflicts)}** 个")
    for c in conflicts:
        parts.append(f"  - `{c[0]}` ↔ `{c[1]}`: {c[2]}")

    # ── 4) Writing Spec
    parts.append("\n## 4️⃣ Writing Spec（给 GE 的最终指令）\n")
    spec_show = spec_md if len(spec_md) <= 3000 else spec_md[:3000] + "\n...(截断)"
    parts.append(spec_show)

    # ── 5) 评分回路 + 重写决策
    parts.append("\n## 5️⃣ 评分 / 重写 / 回溯链路\n")
    parts.append("| 轮次 | hard_pass | soft_score | new_best? | action |")
    parts.append("|---|---|---|---|---|")
    for d in decisions:
        rb = "✅" if d["is_new_best"] else "  "
        hp = "✓" if d["hard_pass"] else "✗"
        parts.append(f"| v{d['rewrite']} | {hp} | {d['soft_score']} | {rb} | {d['action']} |")

    parts.append("\n### 各 AE 在每轮的得分明细\n")
    parts.append("| AE | " + " | ".join(f"v{d['rewrite']}" for d in decisions) + " |")
    parts.append("|---|" + "|".join(["---"] * len(decisions)) + "|")
    all_aes = list((decisions[0]["per_ae"] if decisions else {}).keys())
    for ae in all_aes:
        row = [f"`{ae}`"]
        for d in decisions:
            sc = d["per_ae"].get(ae, {}).get("score")
            sg = d["per_ae"].get(ae, {}).get("suggestions", 0)
            row.append(f"{sc} ({sg}建议)" if sc is not None else "—")
        parts.append("| " + " | ".join(row) + " |")

    parts.append("\n### 各轮的 top suggestions（前 5 条）\n")
    for d in decisions:
        parts.append(f"\n**v{d['rewrite']} → action: {d['action']}**")
        if d["top_suggestions"]:
            for s in d["top_suggestions"]:
                parts.append(f"- {s}")
        else:
            parts.append("- (无 suggestion，全部 AE 通过)")

    # ── 6) 终稿
    parts.append(f"\n## 6️⃣ 终稿（v{picked_idx}, best-of-N 选中）\n")
    parts.append("```")
    parts.append(final_draft)
    parts.append("```")

    return "\n".join(parts) + "\n"


# ─────────────────── 主入口 ───────────────────
def run_full_flow(brief_path: str | None = None, verbose: bool = True, work_dir: str | Path | None = None) -> dict:
    """端到端跑完 10 步。返回包含路径、verdict、metrics 的 dict。"""
    bp = Path(brief_path) if brief_path else (CAMP / "brief.yaml")

    log = print if verbose else (lambda *a, **k: None)

    # Step 1
    brief = yaml.safe_load(bp.read_text(encoding="utf-8"))
    for k in ["brief_id", "brief_type", "brand", "products"]:
        assert k in brief, f"brief.yaml 缺少必填字段 {k}"
    bid = brief["brief_id"]
    log(f"[1/10] brief 读取: {bid} ({brief['brief_type']})")

    # 创建 debug 目录，全链路落盘
    notes_dir = Path(work_dir) if work_dir is not None else NOTES
    notes_dir.mkdir(parents=True, exist_ok=True)
    DEBUG = notes_dir / f"{bid}-debug"
    DEBUG.mkdir(parents=True, exist_ok=True)
    (DEBUG / "00-brief.yaml").write_text(
        yaml.dump(brief, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8")

    # Step 2
    bt = bundle_asset_content("brief_type_registry", "xhs_writer")
    if bt is None:
        bt = yaml.safe_load((EXPERTS / "_brief_types.yaml").read_text(encoding="utf-8"))
    if brief["brief_type"] not in bt["brief_types"]:
        raise ValueError(f"brief_type {brief['brief_type']} 未在 _brief_types.yaml 注册")
    required_aes = bt["brief_types"][brief["brief_type"]]["required_aes"]
    log(f"[2/10] required_aes: {required_aes}")

    # Step 3 — 调用各 AE instruct，落盘 prompt+响应+解析
    ae_outputs: dict[str, dict] = {}
    for ae in required_aes:
        log(f"[3/10] calling AE: {ae} (instruct)...")
        ae_outputs[ae] = call_ae(ae, mode="instruct", brief=brief, debug_dir=DEBUG)
        keys = list(ae_outputs[ae].keys())
        log(f"       → {ae} 输出字段: {keys}")

    # Step 4
    hard_block = collect_hard_blocklist(ae_outputs)
    conflicts = detect_conflicts(ae_outputs, hard_block)
    log(f"[4/10] 红线词 {len(hard_block)} 个; 冲突 {len(conflicts)} 个")
    (DEBUG / "01-conflicts.yaml").write_text(yaml.dump({
        "hard_block_count": len(hard_block),
        "hard_block_sample": hard_block[:30],
        "conflicts": [{"from": c[0], "to": c[1], "issue": c[2]} for c in conflicts],
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if conflicts:
        for c in conflicts:
            log(f"       ⚠ 冲突: {c[0]} ↔ {c[1]} | {c[2]}")

    # Step 5
    spec_md = build_writing_spec(brief, ae_outputs, hard_block)
    spec_path = notes_dir / f"{bid}-spec.md"
    spec_path.write_text(spec_md, encoding="utf-8")
    log(f"[5/10] spec → {spec_path}")

    # Step 6
    system, style, voice = ge_prompt_parts()
    log(f"[6/10] GE 生文中...")
    draft = call_ge(brief, spec_md, system, style, voice, debug_dir=DEBUG, tag="v0")
    rewrite_count = 0
    (notes_dir / f"{bid}-draft-v0.md").write_text(draft, encoding="utf-8")

    # Step 7-8 评分回路 (best-of-N + 单调约束)
    threshold = brief.get("score_threshold") or bt["brief_types"][brief["brief_type"]].get("score_threshold", 80)
    soft_floor = brief.get("soft_floor", 60)   # 软分地板：≥此值时即使没到阈值也可接受
    max_rw = brief.get("max_rewrites") or bt["brief_types"][brief["brief_type"]].get("max_rewrites", 2)

    # 维护最佳版本：(draft, agg, rewrite_idx)
    agg: dict = {}
    best: tuple = (None, None, -1)
    decisions: list[dict] = []   # 决策日志

    def _score_tuple(a: dict) -> tuple:
        return (1 if a["hard_pass"] else 0, a["soft_score"])

    while True:
        log(f"[7/10] 评分中 (rewrite={rewrite_count})...")
        agg = aggregate_scores(brief, draft, required_aes,
                               debug_dir=DEBUG, tag=f"v{rewrite_count}")
        log(f"       hard_pass={agg['hard_pass']}, soft_score={agg['soft_score']}")

        # 决策记录：每个 AE 的分数+建议数
        per_ae = {a: {
            "score": (agg["results"].get(a) or {}).get("score"),
            "suggestions": len((agg["results"].get(a) or {}).get("suggestions") or []),
        } for a in required_aes}

        is_new_best = best[0] is None or _score_tuple(agg) > _score_tuple(best[1])
        if is_new_best:
            best = (draft, agg, rewrite_count)

        decision = {
            "rewrite": rewrite_count,
            "hard_pass": agg["hard_pass"],
            "soft_score": agg["soft_score"],
            "is_new_best": is_new_best,
            "per_ae": per_ae,
            "top_suggestions": agg["suggestions"][:5],
        }

        # 决定下一步动作
        if agg["hard_pass"] and agg["soft_score"] >= threshold:
            decision["action"] = "accept (hit threshold)"; verdict = "pass"
            decisions.append(decision)
            break
        if rewrite_count >= max_rw:
            decision["action"] = f"stop (max_rewrites={max_rw})"
            decisions.append(decision)
            break
        if agg["hard_pass"] and agg["soft_score"] >= soft_floor and rewrite_count >= 1:
            decision["action"] = f"early-stop (hard_pass + soft≥floor({soft_floor}), 防过度优化)"
            decisions.append(decision)
            log(f"       [early-stop] hard_pass=True 且 soft={agg['soft_score']}≥floor({soft_floor})，停止")
            break

        decision["action"] = "rewrite"
        decisions.append(decision)
        rewrite_count += 1
        feedback = "\n".join(agg["suggestions"][:8])
        log(f"[8/10] 重写 v{rewrite_count}...")
        draft = call_ge(brief, spec_md, system, style, voice,
                        feedback=feedback, prev_draft=draft,
                        debug_dir=DEBUG, tag=f"v{rewrite_count}")
        (notes_dir / f"{bid}-draft-v{rewrite_count}.md").write_text(draft, encoding="utf-8")

    # 最终用 best (而不是 last)
    draft, agg, picked_idx = best
    log(f"       最终选用版本: v{picked_idx} (hard_pass={agg['hard_pass']}, soft={agg['soft_score']})")
    if not (agg["hard_pass"] and agg["soft_score"] >= threshold):
        verdict = "warning"
    else:
        verdict = "pass"

    # 落盘决策日志
    (DEBUG / "02-decisions.yaml").write_text(yaml.dump({
        "verdict": verdict,
        "picked_version": f"v{picked_idx}",
        "rounds": decisions,
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # Step 9
    final_path = notes_dir / f"{bid}-final.md"
    final_path.write_text(draft, encoding="utf-8")
    log(f"[9/10] 终稿 → {final_path}")

    # Step 10
    write_lessons(brief, ae_outputs, agg, verdict, rewrite_count)
    log(f"[10/10] lessons 已写回")

    # 生成全链路 trace 摘要
    trace = _emit_trace(bid, brief, ae_outputs, hard_block, conflicts,
                        spec_md, decisions, picked_idx, draft, agg, verdict, DEBUG)
    (DEBUG / "TRACE.md").write_text(trace, encoding="utf-8")
    log(f"\n[trace] 全链路报告: {DEBUG / 'TRACE.md'}")

    return {
        "brief_id": bid,
        "verdict": verdict,
        "hard_pass": agg["hard_pass"],
        "soft_score": agg["soft_score"],
        "rewrite_count": rewrite_count,
        "spec_path": str(spec_path),
        "final_path": str(final_path),
    }


if __name__ == "__main__":
    import sys
    bp = sys.argv[1] if len(sys.argv) > 1 else None
    result = run_full_flow(bp)
    print("\n=== RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
