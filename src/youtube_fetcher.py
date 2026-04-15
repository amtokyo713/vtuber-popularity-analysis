"""yt-dlpで動画とチャンネルの詳細情報を取得する.

- 各動画URLから、チャンネル名・登録者数・説明欄・タグ等を取得
- 説明欄からTwitter/TikTok/Instagram等のSNSリンクを正規表現で抽出
- data/channels_enriched.json に追記(レジューム可能)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yt_dlp

# SNSリンク抽出用の正規表現
SOCIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "twitter": re.compile(
        r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})",
        re.I,
    ),
    "tiktok": re.compile(
        r"https?://(?:www\.|vt\.)?tiktok\.com/@([A-Za-z0-9_.]+)",
        re.I,
    ),
    "instagram": re.compile(
        r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)",
        re.I,
    ),
    "discord": re.compile(
        r"https?://(?:www\.)?discord\.(?:gg|com/invite)/([A-Za-z0-9]+)",
        re.I,
    ),
    "twitch": re.compile(
        r"https?://(?:www\.)?twitch\.tv/([A-Za-z0-9_]{1,25})",
        re.I,
    ),
    "bilibili": re.compile(r"https?://space\.bilibili\.com/(\d+)", re.I),
    "fanbox": re.compile(r"https?://([A-Za-z0-9_-]+)\.fanbox\.cc", re.I),
    "booth": re.compile(r"https?://([A-Za-z0-9_-]+)\.booth\.pm", re.I),
}


def build_ydl() -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "retries": 2,
            "socket_timeout": 30,
            "ignoreerrors": True,
            "no_color": True,
        }
    )


def extract_socials(description: str) -> dict[str, list[str]]:
    """説明欄からSNSハンドル一覧を抽出する."""
    if not description:
        return {}
    result: dict[str, list[str]] = {}
    for name, pattern in SOCIAL_PATTERNS.items():
        matches = pattern.findall(description)
        if not matches:
            continue
        seen: set[str] = set()
        uniq: list[str] = []
        for m in matches:
            if m and m not in seen:
                seen.add(m)
                uniq.append(m)
        if uniq:
            result[name] = uniq
    return result


def fetch_one(ydl: yt_dlp.YoutubeDL, video_url: str) -> dict[str, Any] | None:
    try:
        info = ydl.extract_info(video_url, download=False)
    except Exception as e:
        print(f"  [warn] failed {video_url}: {type(e).__name__}: {e}")
        return None
    if not info:
        return None

    description = (info.get("description") or "")[:5000]
    return {
        "yt_channel": info.get("channel"),
        "yt_channel_id": info.get("channel_id"),
        "yt_channel_url": info.get("channel_url"),
        "yt_uploader": info.get("uploader"),
        "yt_uploader_id": info.get("uploader_id"),
        "yt_follower_count": info.get("channel_follower_count"),
        "yt_view_count": info.get("view_count"),
        "yt_like_count": info.get("like_count"),
        "yt_upload_date": info.get("upload_date"),
        "yt_duration": info.get("duration"),
        "yt_description": description,
        "yt_tags": (info.get("tags") or [])[:20],
        "yt_categories": info.get("categories") or [],
        "socials": extract_socials(description),
    }


def enrich_all(
    raw_entries: list[dict],
    cache_path: Path,
    limit: int | None = None,
    sleep: float = 0.7,
) -> list[dict]:
    """channels_raw.json の各エントリに YouTube情報を付与する (レジューム可能)."""
    cache: dict[str, dict] = {}
    if cache_path.exists():
        try:
            cache = {
                c["video_id"]: c
                for c in json.loads(cache_path.read_text(encoding="utf-8"))
            }
            print(f"[youtube_fetcher] loaded {len(cache)} cached entries")
        except Exception:
            cache = {}

    targets = raw_entries[:limit] if limit else raw_entries
    ydl = build_ydl()
    results: list[dict] = []

    for idx, entry in enumerate(targets, start=1):
        video_id = entry["video_id"]
        if video_id in cache and cache[video_id].get("yt_channel_id"):
            print(f"[{idx}/{len(targets)}] (cached) {entry['channel_name']}")
            results.append(cache[video_id])
            continue

        print(f"[{idx}/{len(targets)}] fetching {entry['channel_name']}")
        info = fetch_one(ydl, entry["video_url"])
        merged = dict(entry)
        if info:
            merged.update(info)
        results.append(merged)
        cache[video_id] = merged

        # 5件ごとに進捗保存(中断しても安全)
        if idx % 5 == 0:
            cache_path.write_text(
                json.dumps(list(cache.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        time.sleep(sleep)

    cache_path.write_text(
        json.dumps(list(cache.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def main() -> None:
    import sys

    project_root = Path(__file__).resolve().parent.parent
    raw_path = project_root / "data" / "channels_raw.json"
    out_path = project_root / "data" / "channels_enriched.json"

    if not raw_path.exists():
        raise SystemExit(f"not found: {raw_path}. run scraper.py first.")

    limit: int | None = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass

    raw_entries = json.loads(raw_path.read_text(encoding="utf-8"))
    enriched = enrich_all(raw_entries, out_path, limit=limit)
    with_follower = sum(1 for e in enriched if e.get("yt_follower_count"))
    print(
        f"[youtube_fetcher] enriched {len(enriched)} entries "
        f"({with_follower} with follower count) → {out_path}"
    )


if __name__ == "__main__":
    main()
