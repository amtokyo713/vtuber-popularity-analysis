"""VTuber人気要因分析プログラムのエントリーポイント.

全Phase(Scraper → YouTube Fetcher → Researcher → Analyzer → Reporter)を順に実行する.

オプション:
  --limit N          : 最初のN件のみ処理 (パイロット実行用)
  --skip-youtube     : YouTube情報取得をスキップ
  --skip-research    : Web調査をスキップ
  --only-report      : レポート生成のみ実行
  --research-sleep S : ddgs呼び出し間の待機秒数 (デフォルト1.3)
  --encrypt PASSWORD : レポート生成後にAES-256-GCMで暗号化(パスワード保護)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 同じディレクトリのモジュールを import 可能にする
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scraper
import youtube_fetcher
import researcher
import analyzer
import reporter


def run_pipeline(args: argparse.Namespace) -> None:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    output_dir = project_root / "output"
    template_dir = project_root / "src" / "templates"

    raw_path = data_dir / "channels_raw.json"
    enriched_path = data_dir / "channels_enriched.json"
    researched_path = data_dir / "channels_researched.json"
    analyzed_path = data_dir / "channels_analyzed.json"
    report_path = output_dir / "report.html"

    if args.only_report:
        print("=== Phase 5: レポート生成のみ ===")
        reporter.generate_report(
            analyzed_path,
            report_path,
            template_dir,
            filter_out_major=args.filter_out_major,
        )
        if args.encrypt:
            print("\n=== Phase 6: パスワード暗号化 ===")
            import encrypt_report
            sys.argv = ["encrypt_report.py", args.encrypt]
            encrypt_report.main()
        return

    # Phase 1: スクレイピング
    print("=== Phase 1: eve.ebb.jp スクレイピング ===")
    cache_dir = data_dir / "cache"
    raw_entries = scraper.scrape_all(cache_dir)
    raw_path.write_text(
        json.dumps(raw_entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"→ {len(raw_entries)} 件を {raw_path.name} に保存\n")

    # Phase 2: YouTube情報取得
    if not args.skip_youtube:
        print("=== Phase 2: YouTube情報取得 (yt-dlp) ===")
        youtube_fetcher.enrich_all(
            raw_entries, enriched_path, limit=args.limit
        )
        enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
        print()
    else:
        print("[skip] Phase 2: YouTube情報取得\n")
        # YouTubeスキップ時はrawをそのまま流用
        enriched = raw_entries[: args.limit] if args.limit else raw_entries
        enriched_path.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Phase 3: Web調査
    if not args.skip_research:
        print("=== Phase 3: Web調査 (ddgs) ===")
        researcher.research_all(
            enriched,
            researched_path,
            limit=args.limit,
            sleep=args.research_sleep,
        )
        print()
    else:
        print("[skip] Phase 3: Web調査\n")
        researched_path.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Phase 4: 分析
    print("=== Phase 4: 成功要因分析 ===")
    researched = json.loads(researched_path.read_text(encoding="utf-8"))
    # limit があれば研究済みはlimit分のみ
    if args.limit:
        researched = researched[: args.limit]
    analyzed = analyzer.analyze_all(researched)
    analyzed_path.write_text(
        json.dumps(analyzed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"→ {len(analyzed)} 件を分析完了\n")

    # Phase 5: レポート生成
    print("=== Phase 5: HTMLレポート生成 ===")
    reporter.generate_report(
        analyzed_path,
        report_path,
        template_dir,
        filter_out_major=args.filter_out_major,
    )

    # Phase 6: パスワード暗号化(オプション)
    if args.encrypt:
        print("\n=== Phase 6: パスワード暗号化 ===")
        import encrypt_report
        sys.argv = ["encrypt_report.py", args.encrypt]
        encrypt_report.main()

    print("\n=== 完了 ===")
    print(f"レポート: {report_path}")
    print("プレビュー: launch.json 経由で python http.server を起動して確認可能")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VTuber人気要因分析パイプライン")
    p.add_argument("--limit", type=int, default=None, help="最初のN件のみ処理")
    p.add_argument("--skip-youtube", action="store_true")
    p.add_argument("--skip-research", action="store_true")
    p.add_argument("--only-report", action="store_true")
    p.add_argument("--research-sleep", type=float, default=1.3)
    p.add_argument(
        "--encrypt",
        type=str,
        default=None,
        metavar="PASSWORD",
        help="レポート生成後にAES-256-GCMで暗号化(パスワード保護)",
    )
    p.add_argument(
        "--filter-out-major",
        action="store_true",
        help="ホロライブ/にじさんじ/ぶいすぽっ! を除外して個人勢・中堅事務所のみで分析",
    )
    return p.parse_args()


if __name__ == "__main__":
    run_pipeline(parse_args())
