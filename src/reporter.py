"""分析結果をHTMLレポートに整形する."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from analyzer import SUCCESS_PATTERNS
from insights import generate_insights


def _build_stats(analyzed: list[dict]) -> dict:
    agency_counter: Counter[str] = Counter()
    pattern_counter: Counter[str] = Counter()
    tier_counter: Counter[str] = Counter()
    total_peak = 0
    with_signals = 0

    for e in analyzed:
        a = e["analysis"]
        agency_counter[a["agency"]] += 1
        for p in a["patterns"]:
            pattern_counter[p] += 1
        tier_counter[a["peak_tier"]] += 1
        total_peak += e.get("peak_viewers") or 0
        if e.get("research", {}).get("buzz_signals"):
            with_signals += 1

    return {
        "total": len(analyzed),
        "total_peak": total_peak,
        "avg_peak": (total_peak // len(analyzed)) if analyzed else 0,
        "with_signals": with_signals,
        "agency_dist": agency_counter.most_common(),
        "pattern_dist": [
            (SUCCESS_PATTERNS.get(k, k), k, v) for k, v in pattern_counter.most_common()
        ],
        "tier_dist": sorted(
            tier_counter.items(),
            key=lambda x: ["S(1万超)", "A(3000〜1万)", "B(1000〜3000)", "C(500〜1000)", "D(250〜500)", "E(250未満)"].index(x[0])
            if x[0] in ["S(1万超)", "A(3000〜1万)", "B(1000〜3000)", "C(500〜1000)", "D(250〜500)", "E(250未満)"]
            else 99,
        ),
    }


def _format_analysis_for_card(analyzed_entry: dict) -> dict:
    """テンプレート用に、カード表示に必要な情報を整形する."""
    a = analyzed_entry["analysis"]
    research = analyzed_entry.get("research") or {}
    signals = research.get("buzz_signals") or {}

    # バズ詳細記述を生成
    buzz_details: list[dict] = []
    for category in [
        "tiktok_buzz",
        "twitter_buzz",
        "clip_buzz",
        "collab",
        "music",
        "past_life_hint",
        "subscriber_milestone",
    ]:
        hits = signals.get(category, [])
        if not hits:
            continue
        buzz_details.append(
            {
                "category": category,
                "category_label": {
                    "tiktok_buzz": "TikTok関連の言及",
                    "twitter_buzz": "Twitter(X)関連の言及",
                    "clip_buzz": "切り抜き・まとめでの言及",
                    "collab": "コラボ・共演の言及",
                    "music": "歌唱・音楽関連の言及",
                    "past_life_hint": "前世・経歴関連の言及",
                    "subscriber_milestone": "登録者マイルストーン",
                }.get(category, category),
                "hits": hits[:5],
            }
        )

    return {
        **analyzed_entry,
        "buzz_details": buzz_details,
    }


def generate_report(analyzed_path: Path, output_path: Path, template_dir: Path) -> None:
    analyzed = json.loads(analyzed_path.read_text(encoding="utf-8"))
    stats = _build_stats(analyzed)
    insights = generate_insights(analyzed)

    # カード表示用データ (同接降順)
    cards = [_format_analysis_for_card(e) for e in analyzed]
    cards.sort(key=lambda x: x.get("peak_viewers") or 0, reverse=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["format_int"] = lambda v: f"{int(v):,}" if v is not None else "-"
    template = env.get_template("report.html.j2")

    html = template.render(
        cards=cards,
        stats=stats,
        insights=insights,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        success_patterns=SUCCESS_PATTERNS,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    # preview.html にもコピー
    preview_path = output_path.parent / "preview.html"
    preview_path.write_text(html, encoding="utf-8")
    print(f"[reporter] wrote {output_path} and {preview_path}")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    analyzed_path = project_root / "data" / "channels_analyzed.json"
    output_path = project_root / "output" / "report.html"
    template_dir = project_root / "src" / "templates"

    if not analyzed_path.exists():
        raise SystemExit(f"not found: {analyzed_path}. run analyzer.py first.")

    generate_report(analyzed_path, output_path, template_dir)


if __name__ == "__main__":
    main()
