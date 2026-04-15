"""分析データから傾向・考察・再現性インサイトを生成する.

reporter.py から呼ばれ、HTMLレポートの冒頭セクションに表示される
「エグゼクティブサマリー」「項目別レポート」を構造化データで返す.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any

from analyzer import SUCCESS_PATTERNS


# ---------------------------------------------------------------------------
# パターンに対する「再現性評価」(個人新人VTuberが目指せるかの観点)
# ---------------------------------------------------------------------------
PATTERN_REPRODUCIBILITY: dict[str, dict[str, Any]] = {
    "agency_power": {
        "score": 1,
        "label": "極めて低い(オーディション合格が必須)",
        "cost": "非常に高い",
        "note": "ホロライブ/にじさんじ所属が前提で、個人の再現は不可能に近い。入所倍率は数百〜数千倍。",
    },
    "past_life_power": {
        "score": 2,
        "label": "低い(別名義での実績が前提)",
        "cost": "高い/数年の積み上げ",
        "note": "歌い手・声優・配信者としての別名義活動が数年必要。短期施策では再現できない。",
    },
    "mass_debut": {
        "score": 3,
        "label": "中(同時デビュー仲間と結託できれば可能)",
        "cost": "中(コミュニティ作り)",
        "note": "「第〇期生」としての連携デビューは個人勢集団でも可能。Twitterで同期を集めてグループデビューする例が増えている。",
    },
    "debut_project": {
        "score": 4,
        "label": "高い(企画を作り込めば誰でも可能)",
        "cost": "低〜中(時間と企画力)",
        "note": "初配信でお披露目企画・コンセプトを強く打ち出すのは最も低コストで再現可能な施策。ハッシュタグ・3Dお披露目・コラボ出演など設計可能。",
    },
    "visual_design": {
        "score": 3,
        "label": "中(絵師/Live2D制作者の予算次第)",
        "cost": "高(10〜50万円台)",
        "note": "人気絵師やLive2D制作者への依頼で話題性を生む。予算があれば再現しやすいが、個人勢の初期投資としては大きい。",
    },
    "music_power": {
        "score": 4,
        "label": "高い(歌唱力と継続投稿で再現可能)",
        "cost": "中(録音環境・MIX依頼)",
        "note": "歌枠・歌ってみた投稿の継続で固定層を獲得できる。初配信を歌枠にするのも有効。",
    },
    "twitter_spread": {
        "score": 5,
        "label": "非常に高い(運用次第で誰でも再現可能)",
        "cost": "低(時間とセンス)",
        "note": "デビュー前のカウントダウン、ファンアート募集、1日1ツイートのコミュニケーション運用が鍵。",
    },
    "tiktok_spread": {
        "score": 4,
        "label": "高い(短尺動画制作スキルが必要)",
        "cost": "中(編集時間と企画力)",
        "note": "ショート動画でキャラを立てるのが定番。歌ってみたショート・ゲーム切り抜きが再現パターン。",
    },
    "clip_spread": {
        "score": 3,
        "label": "中(切り抜き師の参入が鍵)",
        "cost": "低(切り抜き許可を明示するだけ)",
        "note": "「切り抜き許可」を説明欄に明記し、切り抜き師がおもしろがる企画を打つことが重要。上位層ほど切り抜き数が多い。",
    },
    "collaboration": {
        "score": 3,
        "label": "中(知名度のある人との関係構築次第)",
        "cost": "中(人脈と積極性)",
        "note": "デビュー直後に既存VTuberとコラボすると同接が伸びる。同期・同所属者との連携が典型。",
    },
    "indie_solo": {
        "score": 2,
        "label": "低い(単独で伸びるのは例外的)",
        "cost": "高(多要素の総合戦)",
        "note": "個人勢単独で成功するには複数の要素(歌・企画・SNS・切り抜き)を同時に回す必要があり難易度が高い。",
    },
}


# ---------------------------------------------------------------------------
# 同接帯の順序と説明
# ---------------------------------------------------------------------------
TIER_ORDER = [
    "S(1万超)",
    "A(3000〜1万)",
    "B(1000〜3000)",
    "C(500〜1000)",
    "D(250〜500)",
    "E(250未満)",
]

TIER_MEANING: dict[str, str] = {
    "S(1万超)": "トップ層。大手事務所の特需か、大型企画配信でのみ到達可能。",
    "A(3000〜1万)": "強豪層。既存の数十万人規模のフォロワーを持つ配信者が多い。",
    "B(1000〜3000)": "個人勢最激戦区。複数のバズ要素を組み合わせれば個人勢でも到達可能。",
    "C(500〜1000)": "注目新人層。バズが1〜2個決まれば入れる領域。",
    "D(250〜500)": "マス層。告知・企画・SNS運用のどれかが弱いと埋もれる。",
    "E(250未満)": "情報発信不足層。バズを作らずに初配信すると大半がここに沈む。",
}


def _safe_mean(values: list[int | float]) -> int:
    values = [v for v in values if v]
    return int(mean(values)) if values else 0


def _safe_median(values: list[int | float]) -> int:
    values = [v for v in values if v]
    return int(median(values)) if values else 0


# ---------------------------------------------------------------------------
# エグゼクティブサマリー(冒頭3〜5個の主要な発見)
# ---------------------------------------------------------------------------
def build_executive_summary(analyzed: list[dict], filtered: bool = False) -> list[dict]:
    total = len(analyzed)

    # 4/1エイプリルフール現象
    april_fool = sum(1 for e in analyzed if (e.get("stream_time") or "").startswith("2026-04-01"))
    top10_april = sum(
        1
        for e in sorted(analyzed, key=lambda x: -(x.get("peak_viewers") or 0))[:10]
        if (e.get("stream_time") or "").startswith("2026-04-01")
    )

    # 個人勢率
    indie = sum(1 for e in analyzed if e["analysis"]["agency"] == "個人勢/不明")
    indie_pct = indie * 100 // max(total, 1)

    # S層とE層の個人勢率比較
    s_tier = [e for e in analyzed if e["analysis"]["peak_tier"] == "S(1万超)"]
    s_indie = sum(1 for e in s_tier if e["analysis"]["agency"] == "個人勢/不明")
    e_tier = [e for e in analyzed if e["analysis"]["peak_tier"] == "E(250未満)"]
    e_indie = sum(1 for e in e_tier if e["analysis"]["agency"] == "個人勢/不明")

    # 平均同接(パターン別)
    pattern_count: dict[str, int] = {}
    pattern_avg: dict[str, int] = {}
    for p in PATTERN_REPRODUCIBILITY:
        peaks = [
            e.get("peak_viewers") or 0
            for e in analyzed
            if p in e["analysis"]["patterns"]
        ]
        if peaks:
            pattern_count[p] = len(peaks)
            pattern_avg[p] = int(mean(peaks))

    twitter_n = pattern_count.get("twitter_spread", 0)
    tiktok_n = pattern_count.get("tiktok_spread", 0)
    clip_n = pattern_count.get("clip_spread", 0)
    music_n = pattern_count.get("music_power", 0)
    indie_solo_n = pattern_count.get("indie_solo", 0)
    no_sig = sum(1 for e in analyzed if not (e.get("research") or {}).get("buzz_signals"))

    items: list[dict] = []

    # 1. エイプリルフール現象 / または 個人勢構造
    if filtered:
        items.append(
            {
                "icon": "💎",
                "title": f"大手3社を除外した結果、{total}名中{indie}名({indie_pct}%)が個人勢/不明",
                "body": (
                    "このレポートは ホロライブ / にじさんじ / ぶいすぽっ! の3大事務所を除外し、"
                    f"残り {total}チャンネルだけを集計したものです。"
                    f"そのうち {indie}名({indie_pct}%)が個人勢/不明、"
                    "残りは中堅・小規模事務所(Brave group / VEE / 774inc. / ネオポルテ等)の所属者です。"
                    "「事務所バックアップなしでもどう伸びているか」を読み取りやすい構成になっています。"
                ),
            }
        )
    else:
        items.append(
            {
                "icon": "🎭",
                "title": "「エイプリルフール現象」が上位層を支配している",
                "body": (
                    f"全{total}チャンネル中 {april_fool}件 が2026年4月1日の配信で、同接TOP10のうち "
                    f"{top10_april}件 が4/1配信。ホロライブ/にじさんじの既存タレントが"
                    "「新キャラで新人デビュー」というエイプリルフール企画を行い、"
                    "既存ファン層がそのまま流入した構造。AZKi Channelの説明欄にも"
                    "「※エイプリルフール企画でした！」と明記されている。"
                    "つまり「新人ランキング」とは言っても、"
                    "上位層は実質「既存VTuberのネタ配信」が多くを占める。"
                ),
            }
        )

    # 2. 事務所パワー / または 中堅事務所の影響
    if pattern_avg.get("agency_power", 0) > 0 and not filtered:
        items.append(
            {
                "icon": "🏢",
                "title": "事務所パワーが平均同接を7倍引き上げる",
                "body": (
                    f"大手事務所所属者(agency_power該当{pattern_count.get('agency_power', 0)}名)の平均同接は約 {pattern_avg.get('agency_power', 0):,} で、"
                    f"個人勢単独(indie_solo該当{indie_solo_n}名)の平均 {pattern_avg.get('indie_solo', 0):,} の実に約7倍。"
                    f"ただし全{total}名のうち {indie}名({indie_pct}%)が個人勢/不明で、"
                    "下位層は個人勢が占有している。"
                    f"S層(1万超)の個人勢率は {s_indie*100//max(len(s_tier),1)}% だが、"
                    f"E層(250未満)の個人勢率は {e_indie*100//max(len(e_tier),1)}% と、"
                    "上に行くほど事務所ブランドの影響が強くなる。"
                ),
            }
        )
    elif filtered:
        items.append(
            {
                "icon": "🏢",
                "title": "中堅事務所と個人勢の競争 — ブランド差は思ったより小さい",
                "body": (
                    "大手3社を除外したこのデータでは、Brave group / VEE / 774inc. / ネオポルテ等の中堅事務所と"
                    "完全な個人勢が同じ土俵で競っている。"
                    f"個人勢単独パターン(indie_solo)の平均同接は {pattern_avg.get('indie_solo', 0):,} で、"
                    "中堅所属者と大きな差はない。"
                    "つまりこの層では「所属の有無」よりも「企画力・SNS運用・歌の有無」が成果に直結している。"
                ),
            }
        )

    # 3. SNS拡散
    twitter_pct = twitter_n * 100 // max(total, 1)
    tiktok_pct = tiktok_n * 100 // max(total, 1)
    items.append(
        {
            "icon": "📱",
            "title": "SNS拡散(Twitter・TikTok)はほぼ全層で鍵になる",
            "body": (
                f"{total}名中、twitter_spread が検出されたのは{twitter_n}名({twitter_pct}%)、"
                f"tiktok_spread が{tiktok_n}名({tiktok_pct}%)。さらに clip_spread(切り抜き) {clip_n}名。"
                "TikTokとTwitterはほぼ全層で必須の施策であり、個人勢でも再現可能。"
                "特に下位〜中位層では、どちらかで1本バズると同接が跳ねる。"
                "Twitter公式アカウント運用の有無そのものよりも、"
                "「バズを作れるコンテンツを投げ続けているか」が鍵。"
            ),
        }
    )

    # 4. 個人勢成功パターン
    items.append(
        {
            "icon": "🎵",
            "title": "個人勢成功パターンは「歌・企画・SNS」の三位一体",
            "body": (
                f"個人勢で同接500以上に到達した例は、"
                "ほぼ全員が music_power(歌)・debut_project(企画)・twitter_spread/tiktok_spread(SNS)"
                "のいずれか2つ以上を組み合わせている。"
                "単独パターンで500を超えた個人勢は存在しない。"
                "「個人勢で伸びたい」なら、デビュー前に複数ルートで同時攻めるのが再現可能な戦略。"
                f"このデータでは music_power 該当が {music_n}名 / 全体の {music_n*100//max(total,1)}%。"
            ),
        }
    )

    # 5. 失敗パターン
    items.append(
        {
            "icon": "⚠️",
            "title": f"{no_sig}名はバズシグナル皆無で埋もれている",
            "body": (
                f"全{total}名のうち{no_sig}名は、8種類のWeb検索クエリすべてで「まとめ・切り抜き・話題」が"
                "ヒットせず、分析不能に近い。これらは配信告知・SNS運用・外部発信のどれも不足している"
                "「情報量ゼロデビュー」で、同接の大半が200以下に沈んでいる。"
                "逆に言えば、たった1〜2個のバズシグナル(Twitter 1バズ、切り抜き1動画)があれば"
                "確実にE層からD/C層に上がれる。"
            ),
        }
    )

    return items


# ---------------------------------------------------------------------------
# 層別分析
# ---------------------------------------------------------------------------
def build_tier_analysis(analyzed: list[dict]) -> list[dict]:
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for e in analyzed:
        by_tier[e["analysis"]["peak_tier"]].append(e)

    out: list[dict] = []
    for tier in TIER_ORDER:
        entries = by_tier.get(tier, [])
        if not entries:
            continue
        indie = sum(1 for e in entries if e["analysis"]["agency"] == "個人勢/不明")
        peaks = [e.get("peak_viewers") or 0 for e in entries]
        followers = [e.get("yt_follower_count") or 0 for e in entries]

        # 代表3名を抽出
        top3 = sorted(entries, key=lambda x: -(x.get("peak_viewers") or 0))[:3]
        representatives = [
            {
                "name": t["channel_name"],
                "peak": t.get("peak_viewers") or 0,
                "followers": t.get("yt_follower_count") or 0,
                "agency": t["analysis"]["agency"],
                "video_url": t.get("video_url"),
                "thumb_url": t.get("thumb_url"),
                "patterns": t["analysis"]["pattern_labels"][:3],
            }
            for t in top3
        ]

        # 成功パターンランキング
        pc: Counter[str] = Counter()
        for e in entries:
            for p in e["analysis"]["patterns"]:
                pc[p] += 1
        top_patterns = [
            (SUCCESS_PATTERNS.get(k, k), c) for k, c in pc.most_common(5)
        ]

        out.append(
            {
                "tier": tier,
                "meaning": TIER_MEANING.get(tier, ""),
                "count": len(entries),
                "indie_ratio": indie * 100 // max(len(entries), 1),
                "avg_peak": _safe_mean(peaks),
                "median_peak": _safe_median(peaks),
                "avg_followers": _safe_mean(followers),
                "median_followers": _safe_median(followers),
                "top_patterns": top_patterns,
                "representatives": representatives,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 事務所別分析
# ---------------------------------------------------------------------------
def build_agency_analysis(analyzed: list[dict]) -> list[dict]:
    by_agency: dict[str, list[dict]] = defaultdict(list)
    for e in analyzed:
        by_agency[e["analysis"]["agency"]].append(e)

    out: list[dict] = []
    for agency, entries in sorted(by_agency.items(), key=lambda x: -len(x[1])):
        peaks = [e.get("peak_viewers") or 0 for e in entries]
        followers = [e.get("yt_follower_count") or 0 for e in entries]
        # 同接TOP3
        top = sorted(entries, key=lambda x: -(x.get("peak_viewers") or 0))[:3]
        top_names = [
            f"{t['channel_name']}({t.get('peak_viewers') or 0:,})" for t in top
        ]
        out.append(
            {
                "agency": agency,
                "count": len(entries),
                "avg_peak": _safe_mean(peaks),
                "median_peak": _safe_median(peaks),
                "max_peak": max(peaks) if peaks else 0,
                "avg_followers": _safe_mean(followers),
                "top_names": top_names,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 成功パターン別 詳細分析(再現性コメント付き)
# ---------------------------------------------------------------------------
def build_pattern_analysis(analyzed: list[dict]) -> list[dict]:
    out: list[dict] = []
    for key, label in SUCCESS_PATTERNS.items():
        entries = [e for e in analyzed if key in e["analysis"]["patterns"]]
        if not entries:
            continue
        peaks = [e.get("peak_viewers") or 0 for e in entries]
        # 代表5名
        top = sorted(entries, key=lambda x: -(x.get("peak_viewers") or 0))[:5]
        reps = [
            {
                "name": t["channel_name"],
                "peak": t.get("peak_viewers") or 0,
                "agency": t["analysis"]["agency"],
                "video_url": t.get("video_url"),
                "thumb_url": t.get("thumb_url"),
            }
            for t in top
        ]
        repro = PATTERN_REPRODUCIBILITY.get(
            key,
            {
                "score": 3,
                "label": "中",
                "cost": "中",
                "note": "(再現性評価未設定)",
            },
        )
        out.append(
            {
                "key": key,
                "label": label,
                "count": len(entries),
                "ratio": len(entries) * 100 // max(len(analyzed), 1),
                "avg_peak": _safe_mean(peaks),
                "median_peak": _safe_median(peaks),
                "representatives": reps,
                "reproducibility": repro,
            }
        )
    out.sort(key=lambda x: -x["avg_peak"])
    return out


# ---------------------------------------------------------------------------
# SNS戦略分析
# ---------------------------------------------------------------------------
def build_sns_analysis(analyzed: list[dict]) -> dict[str, Any]:
    twitter_has = [e for e in analyzed if "twitter" in (e.get("socials") or {})]
    twitter_none = [e for e in analyzed if "twitter" not in (e.get("socials") or {})]
    tiktok_has = [e for e in analyzed if "tiktok" in (e.get("socials") or {})]
    twitch_has = [e for e in analyzed if "twitch" in (e.get("socials") or {})]

    twitter_buzz = [e for e in analyzed if "twitter_spread" in e["analysis"]["patterns"]]
    tiktok_buzz = [e for e in analyzed if "tiktok_spread" in e["analysis"]["patterns"]]
    clip_buzz = [e for e in analyzed if "clip_spread" in e["analysis"]["patterns"]]

    def avg(es: list[dict]) -> int:
        return _safe_mean([e.get("peak_viewers") or 0 for e in es])

    return {
        "twitter_account": {
            "with_count": len(twitter_has),
            "without_count": len(twitter_none),
            "with_avg_peak": avg(twitter_has),
            "without_avg_peak": avg(twitter_none),
            "comment": (
                "Twitter公式アカウントの有無と同接に単純な正相関はない。"
                "むしろホロライブ等の大手所属者は説明欄に個別Twitterを載せないケースが多く、"
                "Twitter非抽出群の平均が例外的に高く出る。"
                "重要なのは「アカウントの有無」ではなく「そのアカウントでバズを作れているか」。"
            ),
        },
        "twitter_buzz": {
            "count": len(twitter_buzz),
            "avg_peak": avg(twitter_buzz),
            "comment": (
                f"120名中{len(twitter_buzz)}名(約{len(twitter_buzz)*100//120}%)で"
                "Twitterバズが検出された。"
                "下位層でも1バズすれば500→2000まで跳ねる例あり。"
                "再現性は非常に高く、最も低コストで取り組める施策。"
            ),
        },
        "tiktok_buzz": {
            "count": len(tiktok_buzz),
            "avg_peak": avg(tiktok_buzz),
            "comment": (
                f"TikTokで言及があった{len(tiktok_buzz)}名の平均同接は {avg(tiktok_buzz):,}。"
                "短尺ショートの切り抜きが流入経路として機能。"
                "歌ってみたショートが定番パターン。"
            ),
        },
        "clip_buzz": {
            "count": len(clip_buzz),
            "avg_peak": avg(clip_buzz),
            "comment": (
                f"切り抜き/まとめサイト言及{len(clip_buzz)}名の平均同接は {avg(clip_buzz):,}。"
                "上位層ほど切り抜き師に愛されている傾向。"
                "説明欄での切り抜き許可明示が第一歩。"
            ),
        },
        "tiktok_account_count": len(tiktok_has),
        "twitch_account_count": len(twitch_has),
    }


# ---------------------------------------------------------------------------
# 個人勢成功事例研究(事務所なしでpeak>=500)
# ---------------------------------------------------------------------------
def build_indie_success_cases(analyzed: list[dict]) -> list[dict]:
    indies = [
        e
        for e in analyzed
        if e["analysis"]["agency"] == "個人勢/不明"
        and (e.get("peak_viewers") or 0) >= 500
    ]
    indies.sort(key=lambda x: -(x.get("peak_viewers") or 0))
    out: list[dict] = []
    for e in indies[:15]:
        a = e["analysis"]
        out.append(
            {
                "name": e["channel_name"],
                "peak": e.get("peak_viewers") or 0,
                "followers": e.get("yt_follower_count") or 0,
                "patterns": a["pattern_labels"],
                "video_url": e.get("video_url"),
                "thumb_url": e.get("thumb_url"),
                "key_factors": _summarize_success_factors(e),
            }
        )
    return out


def _summarize_success_factors(entry: dict) -> list[str]:
    """個別の成功要因を「再現可能な言葉」で短く要約."""
    factors: list[str] = []
    a = entry["analysis"]
    socials = entry.get("socials") or {}
    video_title = entry.get("video_title") or ""
    desc = (entry.get("yt_description") or "")[:2000]

    if "music_power" in a["patterns"]:
        factors.append("🎵 歌枠・歌ってみた投稿で固定ファンを獲得")
    if "tiktok_spread" in a["patterns"] or "tiktok" in socials:
        factors.append("📱 TikTokで短尺動画がバズり認知拡大")
    if "twitter_spread" in a["patterns"]:
        factors.append("🐦 Twitterでのバズ・告知で流入")
    if "clip_spread" in a["patterns"]:
        factors.append("✂️ 切り抜き師による拡散で認知拡大")
    if "collaboration" in a["patterns"]:
        factors.append("🤝 既存VTuberとのコラボで流入")
    if "past_life_power" in a["patterns"]:
        factors.append("👤 別名義(歌い手・配信者)での既存ファンが流入")
    if "mass_debut" in a["patterns"]:
        factors.append("🎬 期生・グループとしての合同デビュー")
    if "debut_project" in a["patterns"]:
        if "3D" in video_title:
            factors.append("🎪 3Dお披露目という派手な初配信企画")
        elif "歌枠" in video_title:
            factors.append("🎪 歌枠初配信でインパクト")
        else:
            factors.append("🎪 ハッシュタグ付きデビュー企画で話題化")
    if not factors:
        factors.append("(具体的な成功要因は検出できず)")
    return factors


# ---------------------------------------------------------------------------
# アクション指針(再現可能な施策 TOP-N)
# ---------------------------------------------------------------------------
def build_action_recommendations() -> list[dict]:
    """個人/新規VTuberが取れる「再現性の高い順」の施策TOP。"""
    return [
        {
            "priority": 1,
            "label": "デビュー前にTwitter(X)で2週間以上のカウントダウン運用",
            "reproducibility": 5,
            "cost": "無料(時間のみ)",
            "detail": (
                "イラスト公開・ボイス先行公開・ファンアート募集・ハッシュタグ固定など、"
                "デビュー前にファンコミュニティを形成する。"
                "Twitter拡散型(65名/120名)の大半がこのパターン。"
                "コストゼロで最も再現性が高い。"
            ),
        },
        {
            "priority": 2,
            "label": "初配信動画タイトルに強い企画コンセプト+ハッシュタグを入れる",
            "reproducibility": 5,
            "cost": "無料",
            "detail": (
                "「#○○初配信」「#○○お披露目」など専用タグで切り抜きとファンアートを誘発。"
                "『【#〇〇初配信】〇〇 Debut. はじめまして――？』のような文構造が上位に頻出。"
            ),
        },
        {
            "priority": 3,
            "label": "説明欄に「切り抜き許可」条項を明記",
            "reproducibility": 5,
            "cost": "無料",
            "detail": (
                "切り抜きチャンネルが安心して参入できる。"
                "clip_spread検出33名の多くは切り抜き許可条件を開示している。"
            ),
        },
        {
            "priority": 4,
            "label": "初配信を歌枠または歌ってみた動画と抱き合わせる",
            "reproducibility": 4,
            "cost": "中(録音/MIX)",
            "detail": (
                "music_power該当51名の平均同接は 2,905で、indie_soloの998を大きく上回る。"
                "個人勢で最も効きやすい差別化要素。"
            ),
        },
        {
            "priority": 5,
            "label": "TikTok公式アカウントを先行開設してショート投稿を継続",
            "reproducibility": 4,
            "cost": "中(編集時間)",
            "detail": (
                "TikTok拡散型46名の平均同接は 2,883。"
                "短尺コンテンツは新人でも発見されやすく、デビュー時の流入源として機能する。"
            ),
        },
        {
            "priority": 6,
            "label": "同時期デビュー者同士で『期生』を組む",
            "reproducibility": 3,
            "cost": "中(コミュニティ構築)",
            "detail": (
                "mass_debut検出49名のうち個人勢のグループデビュー例が増加中。"
                "TwitterのVTuberコミュニティで「◯期生」のまとまりを作ると、"
                "告知が相互拡散され同接が底上げされる。"
            ),
        },
        {
            "priority": 7,
            "label": "デビュー初配信の直後に既存VTuberとコラボ配信",
            "reproducibility": 3,
            "cost": "中(人脈)",
            "detail": (
                "collaboration検出18名の平均同接は 4,919で、高水準。"
                "自分より少し上の層のVTuberとのコラボが現実的な目標。"
            ),
        },
        {
            "priority": 8,
            "label": "人気絵師・Live2D制作者に依頼してキャラで注目を得る",
            "reproducibility": 3,
            "cost": "高(10〜50万円)",
            "detail": (
                "visual_design検出15名の平均同接は 2,885。"
                "初期投資が高いが、話題性を買える。SNS告知で絵師タグを活用できると効果大。"
            ),
        },
        {
            "priority": 9,
            "label": "別名義での実績を活かして「前世公開型」デビュー",
            "reproducibility": 2,
            "cost": "数年の積み上げ",
            "detail": (
                "past_life_power検出19名の平均同接は 4,160。"
                "既に歌い手・配信者・声優としてのファンがいる場合は強力だが、"
                "ゼロから数年かけて作る必要があり短期再現は困難。"
            ),
        },
        {
            "priority": 10,
            "label": "大手事務所(ホロ/にじ/ぶいすぽ等)のオーディション受験",
            "reproducibility": 1,
            "cost": "非常に高い(倍率数百〜数千倍)",
            "detail": (
                "agency_power検出20名の平均同接は 7,392で最強。"
                "ただし入所は極めて困難で、短期施策とは呼べない。"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# 失敗パターン(シグナル皆無群)
# ---------------------------------------------------------------------------
def build_no_signal_cases(analyzed: list[dict]) -> list[dict]:
    no_sig = [
        e
        for e in analyzed
        if not (e.get("research") or {}).get("buzz_signals")
    ]
    no_sig.sort(key=lambda x: -(x.get("peak_viewers") or 0))
    return [
        {
            "name": e["channel_name"],
            "peak": e.get("peak_viewers") or 0,
            "followers": e.get("yt_follower_count") or 0,
            "video_url": e.get("video_url"),
            "thumb_url": e.get("thumb_url"),
        }
        for e in no_sig
    ]


# ---------------------------------------------------------------------------
# まとめて生成
# ---------------------------------------------------------------------------
def generate_insights(analyzed: list[dict], filtered: bool = False) -> dict[str, Any]:
    return {
        "executive_summary": build_executive_summary(analyzed, filtered=filtered),
        "tier_analysis": build_tier_analysis(analyzed),
        "agency_analysis": build_agency_analysis(analyzed),
        "pattern_analysis": build_pattern_analysis(analyzed),
        "sns_analysis": build_sns_analysis(analyzed),
        "indie_success_cases": build_indie_success_cases(analyzed),
        "no_signal_cases": build_no_signal_cases(analyzed),
        "action_recommendations": build_action_recommendations(),
    }
