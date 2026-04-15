"""各VTuberについてWeb検索で情報収集する.

- ddgs を用いて8種類のクエリでWeb検索
- 検索結果本文からバズシグナル(TikTok/Twitter/切り抜き等)を検出
- data/channels_researched.json に追記(レジューム可能)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ddgs import DDGS

# 検索クエリテンプレート (名前のみ差し替え)
QUERY_TEMPLATES: list[tuple[str, str]] = [
    ("overview", '"{name}" VTuber'),
    ("debut", '"{name}" 初配信'),
    ("clip", '"{name}" 切り抜き'),
    ("tiktok", '"{name}" TikTok'),
    ("twitter_x", '"{name}" Twitter OR X バズ'),
    ("past_life", '"{name}" 前世 中の人'),
    ("agency", '"{name}" 所属 事務所 デビュー'),
    ("popularity", '"{name}" 人気 理由 バズ'),
]

# バズシグナル検出用キーワード
BUZZ_KEYWORDS: dict[str, list[str]] = {
    "tiktok_buzz": [
        "tiktok", "ティックトック", "TikTokでバズ", "TikTok人気",
        "ショート動画", "ショート バズ", "切り抜きTikTok",
    ],
    "twitter_buzz": [
        "twitter", "ツイッター", "X(旧Twitter)", "X(twitter)",
        "バズった", "トレンド入り", "ツイート 話題", "リポスト",
        "リツイート", "拡散",
    ],
    "clip_buzz": [
        "切り抜き", "まとめ", "切り抜きチャンネル", "名場面",
        "切り抜き動画", "切り抜き師",
    ],
    "meme_buzz": [
        "ミーム", "流行語", "ネットミーム", "meme",
    ],
    "collab": [
        "コラボ", "共演", "collab", "合同配信",
    ],
    "music": [
        "歌ってみた", "オリジナル曲", "歌唱力", "歌い手", "歌枠",
        "ライブ", "ボーカル",
    ],
    "past_life_hint": [
        "前世", "中の人", "魂", "転生", "同時引退",
    ],
    "design_hint": [
        "ママ", "絵師", "イラストレーター", "デザイン", "Live2D",
    ],
    "subscriber_milestone": [
        "10万人", "20万人", "30万人", "50万人", "100万人",
        "登録者",
    ],
    "holo_nijisanji": [
        "ホロライブ", "にじさんじ", "hololive", "nijisanji",
        "holoX", "ReGLOSS", "FLOW GLOW",
    ],
}


def _ddgs_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """DDGS.text を叩いて整形済み結果を返す."""
    results: list[dict[str, Any]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="jp-jp", max_results=max_results):
                results.append(
                    {
                        "title": (r.get("title") or "")[:300],
                        "url": r.get("href") or r.get("url") or "",
                        "body": (r.get("body") or "")[:500],
                    }
                )
    except Exception as e:
        print(f"    [warn] search failed '{query[:40]}…': {type(e).__name__}: {e}")
    return results


def detect_buzz_signals(results: list[dict]) -> dict[str, list[dict]]:
    """検索結果からバズシグナルを検出し、該当スニペットを抽出する."""
    signals: dict[str, list[dict]] = {}
    for category, keywords in BUZZ_KEYWORDS.items():
        hits: list[dict] = []
        for r in results:
            text_lower = f"{r['title']} {r['body']}".lower()
            matched_kw = [kw for kw in keywords if kw.lower() in text_lower]
            if matched_kw:
                hits.append(
                    {
                        "matched": matched_kw[:3],
                        "title": r["title"],
                        "url": r["url"],
                        "snippet": r["body"][:250],
                        "query_key": r.get("query_key", ""),
                    }
                )
                if len(hits) >= 5:
                    break
        if hits:
            signals[category] = hits
    return signals


def research_one(
    name: str,
    per_query_results: int = 5,
    sleep: float = 1.3,
) -> dict[str, Any]:
    """1VTuberを調査する."""
    all_results: list[dict] = []
    for key, template in QUERY_TEMPLATES:
        query = template.format(name=name)
        rs = _ddgs_search(query, max_results=per_query_results)
        for r in rs:
            r["query_key"] = key
            r["query"] = query
        all_results.extend(rs)
        time.sleep(sleep)

    signals = detect_buzz_signals(all_results)
    return {
        "queries_run": [q.format(name=name) for _, q in QUERY_TEMPLATES],
        "total_results": len(all_results),
        "results": all_results,
        "buzz_signals": signals,
    }


def research_all(
    enriched: list[dict],
    cache_path: Path,
    limit: int | None = None,
    sleep: float = 1.3,
) -> list[dict]:
    cache: dict[str, dict] = {}
    if cache_path.exists():
        try:
            cache = {
                c["video_id"]: c
                for c in json.loads(cache_path.read_text(encoding="utf-8"))
            }
            print(f"[researcher] loaded {len(cache)} cached entries")
        except Exception:
            cache = {}

    targets = enriched[:limit] if limit else enriched
    out: list[dict] = []

    for idx, entry in enumerate(targets, start=1):
        video_id = entry["video_id"]
        if video_id in cache and cache[video_id].get("research"):
            print(f"[{idx}/{len(targets)}] (cached) {entry['channel_name']}")
            out.append(cache[video_id])
            continue

        print(f"[{idx}/{len(targets)}] researching {entry['channel_name']}")
        research = research_one(entry["channel_name"], sleep=sleep)
        merged = dict(entry)
        merged["research"] = research
        out.append(merged)
        cache[video_id] = merged

        # 3件ごとに進捗保存
        if idx % 3 == 0:
            cache_path.write_text(
                json.dumps(list(cache.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    cache_path.write_text(
        json.dumps(list(cache.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def main() -> None:
    import sys

    project_root = Path(__file__).resolve().parent.parent
    in_path = project_root / "data" / "channels_enriched.json"
    out_path = project_root / "data" / "channels_researched.json"

    if not in_path.exists():
        raise SystemExit(f"not found: {in_path}. run youtube_fetcher.py first.")

    limit: int | None = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass

    enriched = json.loads(in_path.read_text(encoding="utf-8"))
    researched = research_all(enriched, out_path, limit=limit)
    with_signal = sum(1 for e in researched if e.get("research", {}).get("buzz_signals"))
    print(
        f"[researcher] researched {len(researched)} entries "
        f"({with_signal} with buzz signals) → {out_path}"
    )


if __name__ == "__main__":
    main()
