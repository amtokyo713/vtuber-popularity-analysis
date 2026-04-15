"""収集データから各VTuberの成功要因を分類・分析する.

- 事務所の判定 (大手/中堅/個人勢)
- 成功パターンの分類 (複数該当可)
- 具体的な「バズ理由」テキストの生成
- data/channels_analyzed.json に保存
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 「大手事務所」フィルター用のラベル(ユーザーから明示された3社)
# ---------------------------------------------------------------------------
MAJOR_AGENCY_FILTER: set[str] = {
    "ホロライブ",
    "にじさんじ",
    "ぶいすぽっ!",
}

# ---------------------------------------------------------------------------
# 事務所分類
# ---------------------------------------------------------------------------
MAJOR_AGENCIES: dict[str, list[str]] = {
    "ホロライブ": ["ホロライブ", "hololive", "holoX", "ReGLOSS", "FLOW GLOW", "holoEN"],
    "にじさんじ": ["にじさんじ", "nijisanji", "NIJISANJI", "にじEN"],
    "ぶいすぽっ!": ["ぶいすぽ", "vspo", "VSPO", "V-Stars"],
    "ネオポルテ": ["ネオポルテ", "neo-porte", "NEO-PORTE", "neoporte"],
    "のりプロ": ["のりプロ", "NoriPro"],
    "あおぎり高校": ["あおぎり高校", "Aogiri"],
    "774inc.": ["774inc", "774 inc", "アニマーレ", "シュガリリ", "ハニスト"],
    "Brave group": ["Brave group", "ブレイブグループ", "HIMEHINA", "Re:AcT", "ReAcT", "VApArt"],
    "VShojo": ["VShojo", "vshojo"],
    "Idol Corp": ["Idol Corp", "idolcorp"],
    "Phase Connect": ["Phase Connect", "phaseconnect"],
    "VEE": ["VEE "],
    "Kawaii": ["Kawaii "],
}

# ---------------------------------------------------------------------------
# 成功パターン定義
# ---------------------------------------------------------------------------
SUCCESS_PATTERNS: dict[str, str] = {
    "agency_power": "事務所パワー型(大手ブランド特需)",
    "past_life_power": "前世強豪型(既存ファン流入)",
    "debut_project": "デビュー企画・コンセプト型",
    "visual_design": "ビジュアル・デザイン話題型",
    "clip_spread": "切り抜き拡散型",
    "tiktok_spread": "TikTok拡散型",
    "twitter_spread": "Twitter(X)拡散型",
    "collaboration": "コラボ起点型",
    "music_power": "歌唱・音楽型",
    "indie_solo": "個人勢実力型",
    "mass_debut": "期生・大型デビュー型",
}


def classify_agency(entry: dict[str, Any]) -> str:
    """チャンネル名・タイトル・説明欄・調査結果から事務所を判定する."""
    parts = [
        entry.get("channel_name", ""),
        entry.get("video_title", ""),
        entry.get("yt_channel", "") or "",
        entry.get("yt_description", "") or "",
    ]
    research = entry.get("research") or {}
    for r in (research.get("results") or [])[:20]:
        parts.append(f"{r.get('title', '')} {r.get('body', '')}")
    combined = " ".join(parts).lower()

    for agency, keywords in MAJOR_AGENCIES.items():
        for kw in keywords:
            if kw.lower() in combined:
                return agency
    return "個人勢/不明"


def _peak_tier(peak: int) -> str:
    if peak >= 10000:
        return "S(1万超)"
    if peak >= 3000:
        return "A(3000〜1万)"
    if peak >= 1000:
        return "B(1000〜3000)"
    if peak >= 500:
        return "C(500〜1000)"
    if peak >= 250:
        return "D(250〜500)"
    return "E(250未満)"


def classify_patterns(entry: dict[str, Any], agency: str) -> tuple[list[str], dict[str, list[dict]]]:
    """成功パターン(複数)とそれぞれの根拠を返す."""
    patterns: list[str] = []
    evidence: dict[str, list[dict]] = {}

    research = entry.get("research") or {}
    signals = research.get("buzz_signals") or {}
    video_title = (entry.get("video_title") or "").lower()
    description = (entry.get("yt_description") or "").lower()
    socials = entry.get("socials") or {}

    # 1) 事務所パワー型(大手2社は確定、中堅は+αで)
    if agency in {"ホロライブ", "にじさんじ"}:
        patterns.append("agency_power")
        evidence["agency_power"] = [
            {"reason": f"{agency}所属のため、初配信時点で大手ブランドによる流入がある"}
        ]

    # 2) 期生・大型デビュー型
    mass_keywords = ["期生", "ReGLOSS", "FLOW GLOW", "holoX", "DEV_IS", "StarsEN", "新人"]
    if any(kw in entry.get("channel_name", "") or kw in video_title for kw in mass_keywords):
        patterns.append("mass_debut")
        evidence["mass_debut"] = [
            {"reason": "期生・ユニットとしての同時デビューで注目を集めた可能性"}
        ]

    # 3) 前世強豪型
    if signals.get("past_life_hint"):
        patterns.append("past_life_power")
        evidence["past_life_power"] = signals["past_life_hint"][:3]

    # 4) TikTok拡散型
    if signals.get("tiktok_buzz") or "tiktok" in socials:
        patterns.append("tiktok_spread")
        hits = signals.get("tiktok_buzz", [])[:3]
        if "tiktok" in socials:
            hits.append(
                {
                    "reason": f"公式TikTokアカウント運用: @{socials['tiktok'][0]}",
                    "url": f"https://www.tiktok.com/@{socials['tiktok'][0]}",
                }
            )
        evidence["tiktok_spread"] = hits

    # 5) Twitter(X)拡散型
    if signals.get("twitter_buzz"):
        patterns.append("twitter_spread")
        evidence["twitter_spread"] = signals["twitter_buzz"][:3]

    # 6) 切り抜き拡散型
    if signals.get("clip_buzz"):
        patterns.append("clip_spread")
        evidence["clip_spread"] = signals["clip_buzz"][:3]

    # 7) コラボ起点型
    if signals.get("collab"):
        patterns.append("collaboration")
        evidence["collaboration"] = signals["collab"][:3]

    # 8) 歌唱・音楽型
    if signals.get("music") or "歌ってみた" in description or "歌枠" in description:
        patterns.append("music_power")
        evidence["music_power"] = signals.get("music", [])[:3] or [
            {"reason": "説明欄/動画タイトルに歌唱系キーワードあり"}
        ]

    # 9) ビジュアル・デザイン型
    if signals.get("design_hint"):
        patterns.append("visual_design")
        evidence["visual_design"] = signals["design_hint"][:3]

    # 10) デビュー企画型(動画タイトルに「初配信」「デビュー」)
    debut_keywords = ["初配信", "debut", "デビュー", "お披露目"]
    if any(kw in video_title for kw in debut_keywords):
        patterns.append("debut_project")
        evidence["debut_project"] = [
            {"reason": f"初配信動画タイトル「{entry.get('video_title', '')[:80]}」"}
        ]

    # 11) 個人勢実力型(事務所なしでバズ)
    if agency == "個人勢/不明" and (
        signals.get("clip_buzz") or signals.get("twitter_buzz") or signals.get("tiktok_buzz")
    ):
        patterns.append("indie_solo")
        evidence["indie_solo"] = [
            {"reason": "事務所バックアップなしでSNS・切り抜きを通じて流入を獲得"}
        ]

    # 重複除去(順序保持)
    seen = set()
    uniq: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq, evidence


def generate_summary(
    entry: dict[str, Any],
    agency: str,
    patterns: list[str],
    evidence: dict[str, list[dict]],
) -> str:
    """人が読める形の分析サマリー(日本語)を生成する."""
    name = entry.get("channel_name", "?")
    peak = entry.get("peak_viewers") or 0
    followers = entry.get("yt_follower_count")

    parts: list[str] = []
    head = f"【{name}】最高同接 {peak:,}"
    if followers:
        head += f" / 登録者 {followers:,}人"
    parts.append(head)
    parts.append(f"所属: {agency}")

    if not patterns:
        parts.append(
            "成功要因の明確な分類はできなかった。"
            "Web検索でバズシグナルを十分に検出できなかった可能性あり。"
        )
        return "\n".join(parts)

    parts.append("【成功要因】")
    for p in patterns:
        label = SUCCESS_PATTERNS.get(p, p)
        parts.append(f"  ・{label}")
        for ev in evidence.get(p, [])[:2]:
            reason = ev.get("reason")
            title = ev.get("title")
            snippet = ev.get("snippet") or ""
            url = ev.get("url")
            if reason:
                parts.append(f"    └ {reason}")
            elif title:
                line = f"    └ 「{title[:80]}」"
                if snippet:
                    line += f" — {snippet[:120]}"
                if url:
                    line += f" ({url})"
                parts.append(line)
    return "\n".join(parts)


def analyze_all(researched: list[dict]) -> list[dict]:
    out: list[dict] = []
    for entry in researched:
        agency = classify_agency(entry)
        patterns, evidence = classify_patterns(entry, agency)
        summary = generate_summary(entry, agency, patterns, evidence)
        merged = dict(entry)
        merged["analysis"] = {
            "agency": agency,
            "peak_tier": _peak_tier(entry.get("peak_viewers") or 0),
            "patterns": patterns,
            "pattern_labels": [SUCCESS_PATTERNS.get(p, p) for p in patterns],
            "evidence": evidence,
            "summary": summary,
        }
        out.append(merged)
    return out


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    in_path = project_root / "data" / "channels_researched.json"
    out_path = project_root / "data" / "channels_analyzed.json"

    if not in_path.exists():
        raise SystemExit(f"not found: {in_path}. run researcher.py first.")

    researched = json.loads(in_path.read_text(encoding="utf-8"))
    analyzed = analyze_all(researched)
    out_path.write_text(
        json.dumps(analyzed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pattern_counts: dict[str, int] = {}
    for e in analyzed:
        for p in e["analysis"]["patterns"]:
            pattern_counts[p] = pattern_counts.get(p, 0) + 1
    print(f"[analyzer] analyzed {len(analyzed)} entries → {out_path}")
    print(f"[analyzer] pattern distribution:")
    for p, c in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {SUCCESS_PATTERNS.get(p, p)}: {c}")


if __name__ == "__main__":
    main()
