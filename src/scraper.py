"""eve.ebb.jp の新人VTuberランキングページをスクレイピングする.

- data/cache/page{1..4}.html を解析
- article.card 要素から各VTuberの情報を抽出
- 重複を排除(同じチャンネル名の再掲は上位のみ採用)
- data/channels_raw.json に保存
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://eve.ebb.jp/yt2/analyze_concurrency.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def fetch_page(page: int, cache_path: Path) -> str:
    """1ページ分のHTMLを取得(キャッシュがあればそれを使用)."""
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path.read_text(encoding="utf-8")
    resp = requests.get(
        BASE_URL,
        params={"view": "grid", "sort": "subs", "rank": 1, "page": page},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(resp.text, encoding="utf-8")
    return resp.text


def parse_html(html: str, source_page: int) -> list[dict]:
    """HTMLからVTuberエントリーを抽出する."""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    for card in soup.select("article.card"):
        video_id = (card.get("data-video") or "").strip()
        channel_name = (card.get("data-channel") or "").strip()
        if not video_id or not channel_name:
            continue

        title_link = card.select_one("a.title")
        title_text = title_link.get_text(" ", strip=True) if title_link else ""
        peak_match = re.search(r"最高同接\s*([\d,]+)", title_text)
        peak_viewers = int(peak_match.group(1).replace(",", "")) if peak_match else None

        video_title = ""
        stream_time = ""
        meta = card.select_one(".meta")
        if meta:
            for div in meta.find_all("div"):
                classes = div.get("class", []) or []
                if "time" in classes:
                    stream_time = div.get_text(" ", strip=True)
                else:
                    text = div.get_text(" ", strip=True)
                    if text.startswith("タイトル"):
                        video_title = text.replace("タイトル", "", 1).strip()

        thumb = card.select_one("img.thumb")
        thumb_url = (thumb.get("src") if thumb else "") or ""

        # チャンネル名から所属事務所タグを推定
        affiliation = _guess_affiliation(channel_name, video_title)

        results.append(
            {
                "channel_name": channel_name,
                "video_id": video_id,
                "peak_viewers": peak_viewers,
                "video_title": video_title,
                "stream_time": stream_time,
                "thumb_url": thumb_url,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "source_page": source_page,
                "affiliation_guess": affiliation,
            }
        )

    return results


_AFFILIATION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("ホロライブ", ("holo", "ホロライブ", "hololive", "holoX", "HoloX")),
    ("にじさんじ", ("にじさんじ", "nijisanji", "NIJISANJI", "Nijisanji")),
    ("ぶいすぽっ!", ("ぶいすぽ", "vspo", "VSPO")),
    ("ネオポルテ", ("ネオポルテ", "neoporte", "NEO-PORTE")),
    ("Re:AcT", ("Re:AcT", "ReAcT")),
    ("VShojo", ("VShojo", "vshojo")),
    ("ブレイブグループ", ("ブレイブグループ", "Brave Group", "HIMEHINA")),
    ("あおぎり高校", ("あおぎり高校", "Aogiri")),
    ("774inc.", ("774inc", "774 inc", "ハニストch", "アニマーレ", "シュガリリ")),
    ("NoriPro", ("NoriPro", "のりプロ")),
    ("VEE", ("VEE", "Vee")),
    ("Kawaii", ("Kawaii", "VirtuaReal")),
    ("個人勢", ()),  # フォールバック
]


def _guess_affiliation(channel_name: str, video_title: str) -> str:
    source = f"{channel_name} {video_title}"
    for label, keywords in _AFFILIATION_KEYWORDS:
        for kw in keywords:
            if kw and kw in source:
                return label
    return "不明/個人勢"


def dedupe(entries: Iterable[dict]) -> list[dict]:
    """同じchannel_nameの重複を排除(最初に出てきたものを採用=最高同接順)."""
    seen: set[str] = set()
    out: list[dict] = []
    for e in entries:
        key = e["channel_name"]
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


MAX_PAGE = 6


def scrape_all(cache_dir: Path) -> list[dict]:
    all_entries: list[dict] = []
    for page in range(1, MAX_PAGE + 1):
        cache_path = cache_dir / f"page{page}.html"
        html = fetch_page(page, cache_path)
        entries = parse_html(html, source_page=page)
        print(f"[scraper] page={page}: {len(entries)} entries")
        all_entries.extend(entries)
    unique = dedupe(all_entries)
    print(f"[scraper] total unique channels: {len(unique)} (from {len(all_entries)} raw)")
    return unique


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    cache_dir = project_root / "data" / "cache"
    out_path = project_root / "data" / "channels_raw.json"

    entries = scrape_all(cache_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[scraper] saved to {out_path}")


if __name__ == "__main__":
    main()
