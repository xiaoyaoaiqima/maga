#!/usr/bin/env python3
"""Authorized low-volume sampler for public Babytree mother-infant pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_SEEDS = [
    "https://m.babytree.com/community/",
    "https://m.babytree.com/community/yuer/",
    "https://m.babytree.com/community/group203957/",
    "https://m.babytree.com/community/club202012/",
    "https://m.babytree.com/ask/",
]

TOPIC_RE = re.compile(r"/community/[^\"'#?]+/topic_\d+\.html")
SEED_RE = re.compile(r"/community/(?:club\d{6}|group\d+|yuer|xinqing|meishi|sheying)/?")
REPLY_COUNT_RE = re.compile(r"(\d+)\s*回复")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_filename(url: str) -> str:
    parsed = urlparse(url)
    token = parsed.path.strip("/").replace("/", "__") or "index"
    token = re.sub(r"[^a-zA-Z0-9_.-]+", "_", token)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{token}__{digest}.html"


def fetch(session: requests.Session, url: str, timeout: int) -> requests.Response:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response


def discover_topic_candidates(html: str, base_url: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not TOPIC_RE.search(href):
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        if url not in seen:
            seen.add(url)
            anchor_text = link.get_text(" ", strip=True)
            candidates.append(
                {
                    "url": url,
                    "anchor_text": anchor_text,
                    "source_url": base_url,
                    "reply_count": parse_reply_count(anchor_text),
                }
            )
    return candidates


def discover_seed_candidates(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not SEED_RE.search(href):
            continue
        url = urljoin(base_url, href).split("#", 1)[0].rstrip("/") + "/"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_reply_count(text: str) -> int:
    match = REPLY_COUNT_RE.search(text or "")
    return int(match.group(1)) if match else 0


def rank_topic_candidates(
    candidates: list[dict[str, object]],
    keywords: list[str],
) -> list[dict[str, object]]:
    def score(candidate: dict[str, str]) -> tuple[int, int]:
        text = str(candidate.get("anchor_text", ""))
        hit_count = sum(1 for keyword in keywords if keyword and keyword in text)
        reply_count = int(candidate.get("reply_count") or 0)
        return (hit_count, reply_count, len(text))

    return sorted(candidates, key=score, reverse=True)


def sleep_between_requests(delay_min: float, delay_max: float) -> None:
    if delay_max < delay_min:
        delay_max = delay_min
    time.sleep(random.uniform(delay_min, delay_max))


def extract_visible_text(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = description_tag.get("content", "").strip() if description_tag else ""

    # Preserve page-local user text in reading order without trying to rewrite it.
    blocks: list[str] = []
    for selector in ["h1", ".detail-content", ".tit-normal", ".content", ".aa"]:
        for node in soup.select(selector):
            text = node.get_text("\n", strip=True)
            if text and text not in blocks:
                blocks.append(text)

    return {
        "title": title,
        "description": description,
        "visible_text_blocks": blocks,
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False)
            # JSON permits these Unicode separators, but JSONL readers commonly
            # split on them as line breaks. Escape them to keep one record per line.
            line = (
                line.replace("\u2028", "\\u2028")
                .replace("\u2029", "\\u2029")
                .replace("\u0085", "\\u0085")
            )
            handle.write(line + "\n")


def read_excluded_urls(paths: list[str]) -> set[str]:
    urls: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                url = row.get("url") or row.get("post_url")
                if url:
                    urls.add(str(url).split("#", 1)[0])
            except json.JSONDecodeError:
                urls.add(line.split("#", 1)[0])
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a low-volume authorized Babytree raw corpus sample."
    )
    parser.add_argument("--max-topics", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.5, help="Fixed delay fallback.")
    parser.add_argument("--delay-min", type=float, default=None)
    parser.add_argument("--delay-max", type=float, default=None)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--seed", action="append", default=[])
    parser.add_argument("--exclude-url-file", action="append", default=[])
    parser.add_argument("--min-reply-count", type=int, default=0)
    parser.add_argument("--discover-seeds", action="store_true")
    parser.add_argument("--max-discovered-seeds", type=int, default=40)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Prioritize topic links whose anchor text contains this keyword.",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir or f"outputs/babytree_raw_{timestamp}")
    raw_dir = out_dir / "raw_html"
    raw_dir.mkdir(parents=True, exist_ok=True)
    delay_min = args.delay if args.delay_min is None else args.delay_min
    delay_max = args.delay if args.delay_max is None else args.delay_max

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )

    seeds = args.seed or DEFAULT_SEEDS
    excluded_urls = read_excluded_urls(args.exclude_url_file)
    seed_rows: list[dict[str, object]] = []
    topic_candidates: list[dict[str, object]] = []
    seen_topics: set[str] = set()
    seen_seed_urls: set[str] = set()
    seed_queue = list(dict.fromkeys(seeds))

    while seed_queue:
        seed = seed_queue.pop(0)
        if seed in seen_seed_urls:
            continue
        seen_seed_urls.add(seed)
        fetched_at = utc_now()
        try:
            response = fetch(session, seed, args.timeout)
            html = response.text
            seed_file = raw_dir / clean_filename(seed)
            seed_file.write_text(html, encoding=response.encoding or "utf-8")
            discovered = discover_topic_candidates(html, seed)
            for candidate in discovered:
                url = str(candidate["url"])
                if url in excluded_urls:
                    continue
                if int(candidate.get("reply_count") or 0) < args.min_reply_count:
                    continue
                if url not in seen_topics:
                    seen_topics.add(url)
                    topic_candidates.append(candidate)
            discovered_seeds = []
            if args.discover_seeds and len(seen_seed_urls) + len(seed_queue) < args.max_discovered_seeds:
                discovered_seeds = discover_seed_candidates(html, seed)
                for seed_url in discovered_seeds:
                    if (
                        seed_url not in seen_seed_urls
                        and seed_url not in seed_queue
                        and len(seen_seed_urls) + len(seed_queue) < args.max_discovered_seeds
                    ):
                        seed_queue.append(seed_url)
            seed_rows.append(
                {
                    "url": seed,
                    "status_code": response.status_code,
                    "fetched_at": fetched_at,
                    "html_file": str(seed_file.relative_to(out_dir)),
                    "discovered_topic_count": len(discovered),
                    "accepted_topic_count": len(
                        [
                            candidate
                            for candidate in discovered
                            if str(candidate["url"]) in seen_topics
                            and int(candidate.get("reply_count") or 0) >= args.min_reply_count
                        ]
                    ),
                    "discovered_seed_count": len(discovered_seeds),
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep crawl audit trail.
            seed_rows.append({"url": seed, "fetched_at": fetched_at, "error": repr(exc)})
        sleep_between_requests(delay_min, delay_max)

    ranked_candidates = rank_topic_candidates(topic_candidates, args.keyword)
    topic_rows: list[dict[str, object]] = []
    for candidate in ranked_candidates[: args.max_topics]:
        url = candidate["url"]
        fetched_at = utc_now()
        row: dict[str, object] = {
            "url": url,
            "fetched_at": fetched_at,
            "source_url": candidate.get("source_url", ""),
            "anchor_text": candidate.get("anchor_text", ""),
            "reply_count": candidate.get("reply_count", 0),
        }
        html_file = raw_dir / clean_filename(url)
        if args.resume and html_file.exists():
            html = html_file.read_text(encoding="utf-8")
            extracted = extract_visible_text(html)
            row.update(
                {
                    "status_code": 200,
                    "html_file": str(html_file.relative_to(out_dir)),
                    "html_bytes": len(html.encode("utf-8")),
                    "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                    "resumed": True,
                    **extracted,
                }
            )
            topic_rows.append(row)
            continue
        try:
            response = fetch(session, url, args.timeout)
            html = response.text
            html_file.write_text(html, encoding=response.encoding or "utf-8")
            extracted = extract_visible_text(html)
            row.update(
                {
                    "status_code": response.status_code,
                    "html_file": str(html_file.relative_to(out_dir)),
                    "html_bytes": len(html.encode("utf-8")),
                    "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                    **extracted,
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep crawl audit trail.
            row["error"] = repr(exc)
        topic_rows.append(row)
        sleep_between_requests(delay_min, delay_max)

    manifest = {
        "created_at": utc_now(),
        "source": "babytree_public_pages",
        "authorization_note": "User stated authorization was obtained before running this sampler.",
        "max_topics": args.max_topics,
        "delay_min_seconds": delay_min,
        "delay_max_seconds": delay_max,
        "keywords": args.keyword,
        "seeds": seeds,
        "seed_count": len(seed_rows),
        "discover_seeds": args.discover_seeds,
        "max_discovered_seeds": args.max_discovered_seeds,
        "min_reply_count": args.min_reply_count,
        "excluded_url_count": len(excluded_urls),
        "discovered_topic_count": len(topic_candidates),
        "fetched_topic_count": len(topic_rows),
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_jsonl(out_dir / "seeds.jsonl", seed_rows)
    write_jsonl(out_dir / "items.jsonl", topic_rows)

    readme = (
        "# BabyTree Raw Sample\n\n"
        "This directory contains an authorized, low-volume raw sample of public "
        "Babytree pages.\n\n"
        "- `raw_html/`: original fetched HTML files.\n"
        "- `items.jsonl`: topic-level index with source URL, raw file path, "
        "hash, title, description, and visible text blocks.\n"
        "- `seeds.jsonl`: seed page fetch audit.\n"
        "- `manifest.json`: run parameters.\n"
    )
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"output_dir={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
