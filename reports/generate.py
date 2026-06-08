#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shinchoku2026 日次タスクレポート生成器。
Firestore(tasks)を読み取り、実行日基準で分類し、
reports-data.js に当日分をupsert（同日があれば上書き）して蓄積する。
file:// で開けるよう、データはJS変数として書き出す（fetch不要）。
"""
import json
import datetime
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JS = os.path.join(HERE, "reports-data.js")
PENDING = os.path.join(HERE, "_pending.json")      # AI分析待ち（generate.py が出力 → Claude が読む）
AI_ADVICE = os.path.join(HERE, "ai-advice.json")   # Claude が書く → --apply で取り込む

API_KEY = "AIzaSyC1cVgoBleKcvXU3Z1G0FNY8JlL72pNP-c"
PROJECT = "kikakugyoumu-907d6"
URL = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
    f"/databases/(default)/documents/tasks?key={API_KEY}&pageSize=300"
)


def fetch_tasks():
    with urllib.request.urlopen(URL, timeout=30) as r:
        d = json.load(r)
    rows = []
    for doc in d.get("documents", []):
        f = doc.get("fields", {})

        def g(k):
            v = f.get(k, {})
            return list(v.values())[0] if v else ""

        rows.append({
            "title": g("title"),
            "deadline": g("deadline"),
            "progress": int(g("progress") or 0),
            "completed": g("completed") is True,
            "requester": anon_requester(g("requester")),
        })
    return rows


# 実名をAIへ渡さないための匿名化（Firestoreに旧名が残っていても保険として変換）
REQUESTER_ALIAS = {
    "目黒さん": "企画部M様", "目黒": "企画部M様",
    "島村さん": "営業部S様", "島村": "営業部S様",
    "奥田さん": "営業部O様", "奥田": "営業部O様",
    "船木さん": "サポート部F様", "船木": "サポート部F様",
}


def anon_requester(v):
    return REQUESTER_ALIAS.get(v, v)


def pdate(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


# タスク種別(タイトル内のキーワード)→ コピーして即使えるAI相談プロンプト。
# 上から順に最初に一致したものを採用。未一致は汎用プロンプト。
AI_PROMPT_RULES = [
    (("動画", "セミナー"),
     "「{t}」を期限内に仕上げたいです。目的・ターゲット・尺(分)・伝えたい3点を私が答えるので質問してください。"
     "そのうえで構成案(オープニング/本編/CTA)とナレーション台本の骨子を作ってください。"),
    (("音", "修正"),
     "「{t}」で音声を直したいです。使用ソフト(例: Premiere/Audition/CapCut)を前提に、"
     "ノイズ除去・音量平準化の手順を番号付きで教えてください。元の問題(雑音/音割れ/音量差)は私が伝えます。"),
    (("バックアップ",),
     "「{t}」を確実に行いたいです。対象データ・保存先・頻度を私が答えるので、"
     "抜け漏れのないバックアップ手順チェックリストと、復元テストの方法を作ってください。"),
    (("サーバー", "残量"),
     "「{t}」の手順を整理したいです。サーバー種別を私が伝えるので、残量・使用率の確認方法(コマンド/管理画面)と、"
     "逼迫時の対処(不要ファイル特定・増設判断)を順に教えてください。"),
    (("申請", "アカウント"),
     "「{t}」を進めたいです。何を申請するか私が説明するので、必要書類・入力項目・つまずきやすい点を洗い出し、"
     "申請完了までのステップを番号付きで示してください。"),
    (("名刺",),
     "「{t}」を仕上げたいです。記載項目(氏名/役職/連絡先/ロゴ有無)を私が渡すので、レイアウト案を2パターン提案し、"
     "印刷入稿で失敗しない注意点(塗り足し/解像度/書体)も教えてください。"),
    (("メール",),
     "「{t}」の文面を作りたいです。相手との関係性・用件・トーン(丁寧/カジュアル)を私が答えるので、"
     "件名と本文を長さ違いで3案提案してください。"),
    (("図面",),
     "「{t}」を準備したいです。用途・サイズ・含める要素を私が伝えるので、必要な図面項目の洗い出しと、"
     "作成ツール別(CAD/PowerPoint/Canva)の作り方を提案してください。"),
    (("展示会", "配布", "サイン"),
     "「{t}」を期限内に用意したいです。展示会の目的・来場者像・伝えたい情報を私が答えるので、"
     "内容構成とデザインの方向性、印刷スケジュールの逆算を提案してください。"),
    (("ドメイン",),
     "「{t}」の対応を整理したいです。対象ドメインと現状(更新/移管/設定)を私が伝えるので、"
     "手順と注意点(DNS反映待ち/失効リスク)を順に教えてください。"),
    (("サイト", "WEB", "入力", "シュミレート", "シミュレート", "価格"),
     "「{t}」を進めたいです。対象ページ・入れる内容・参考にしたい既存サイトを私が共有するので、"
     "構成と入力テキストのたたき台を作り、抜け漏れチェックリストも添えてください。"),
]


def make_ai_prompt(title):
    for keys, tmpl in AI_PROMPT_RULES:
        if any(k in title for k in keys):
            return tmpl.format(t=title)
    return (
        "「{t}」が止まっています。最短で完了させたいです。まず『何が終われば完了か』を1文で定義し、"
        "私に必要な前提を3つ質問してから、具体的な実行ステップを番号付きで提案してください。"
    ).format(t=title)


def build_report(rows, today):
    active = [r for r in rows if not r["completed"]]
    over, td, soon, attn = [], [], [], []
    for r in active:
        dd = pdate(r["deadline"])
        if dd is None:
            continue
        days = (dd - today).days
        item = {
            "title": r["title"], "deadline": r["deadline"],
            "progress": r["progress"], "requester": r["requester"],
            "days": days, "aiPrompt": make_ai_prompt(r["title"]),
        }
        if days < 0:
            over.append(item)
        elif days == 0:
            td.append(item)
        elif days <= 3:
            soon.append(item)
        # 注意分類: 絶=5日以内かつ進捗<=70 / 乱=15日以内かつ進捗<=30
        if 0 <= days <= 5 and r["progress"] <= 70:
            attn.append({**item, "cat": "絶"})
        elif 0 <= days <= 15 and r["progress"] <= 30:
            attn.append({**item, "cat": "乱"})
    over.sort(key=lambda x: x["days"])
    soon.sort(key=lambda x: x["days"])
    attn.sort(key=lambda x: x["days"])

    # 本日の推奨着手: 期限超過(古い順) → 本日期限 を上位3件
    rec = []
    for x in over:
        rec.append(x)
    for x in td:
        rec.append(x)
    rec = rec[:3]

    now = datetime.datetime.now()
    return {
        "date": today.isoformat(),
        "time": now.strftime("%H:%M"),
        "id": today.isoformat() + " " + now.strftime("%H:%M"),
        "generatedAt": now.isoformat(timespec="seconds"),
        "stats": {"total": len(rows), "active": len(active)},
        "activeTitles": sorted(r["title"] for r in active),
        "over": over, "today": td, "soon": soon, "attn": attn,
        "recommend": rec,
    }


def make_message(report, prev):
    """前回スナップショットと比較し、完了は褒め、増加は励ます。"""
    if not prev or "activeTitles" not in prev:
        report["mood"] = "neutral"
        report["message"] = "今日もコツコツいきましょう。状況を見守っています。"
        report["done"] = []
        report["added"] = []
        return
    prev_set = set(prev["activeTitles"])
    cur_set = set(report["activeTitles"])
    done = sorted(prev_set - cur_set)    # 前回は未完了 → 今回は消えた＝完了/削除
    added = sorted(cur_set - prev_set)   # 今回新たに現れた未完了タスク
    report["done"] = done
    report["added"] = added
    if done and added:
        report["mood"] = "mixed"
        report["message"] = (
            f"🎉 {len(done)}件 片づきました、お見事です！"
            f"そして新たに {len(added)}件 増えましたが、ここまで来たあなたなら大丈夫。一つずつ。"
        )
    elif done:
        report["mood"] = "praise"
        report["message"] = (
            f"🎉 {len(done)}件 完了しました、素晴らしいです！この調子で着実に進めましょう。"
        )
    elif added:
        report["mood"] = "cheer"
        report["message"] = (
            f"💪 タスクが {len(added)}件 増えました。焦らず優先度の高いものから。あなたなら捌けます。"
        )
    else:
        report["mood"] = "neutral"
        report["message"] = "変化なし。淡々と前進しましょう。次の1件に集中。"


def load_existing():
    if not os.path.exists(DATA_JS):
        return []
    txt = open(DATA_JS, encoding="utf-8").read()
    i, j = txt.find("["), txt.rfind("]")
    if i == -1 or j == -1:
        return []
    try:
        return json.loads(txt[i:j + 1])
    except Exception:
        return []


def write_data(reports):
    body = json.dumps(reports, ensure_ascii=False, indent=2)
    with open(DATA_JS, "w", encoding="utf-8") as f:
        f.write("window.SHINCHOKU_REPORTS = " + body + ";\n")


def load_reports():
    out = []
    for r in load_existing():
        if "id" not in r:
            r["id"] = r.get("date", "") + " " + r.get("time", "00:00")
        out.append(r)
    return out


def write_pending(report):
    """Claude が読むAI分析待ちファイル。止まっているタスクを渡す。"""
    stuck = []
    seen = set()
    for it in report["over"] + report["today"] + report["attn"]:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        state = ("期限超過" if it["days"] < 0 else
                 "本日期限" if it["days"] == 0 else f"あと{it['days']}日")
        stuck.append({
            "title": it["title"], "deadline": it["deadline"],
            "days": it["days"], "state": state,
            "progress": it["progress"], "requester": it.get("requester", ""),
        })
    payload = {
        "id": report["id"], "date": report["date"], "time": report["time"],
        "stats": report["stats"],
        "counts": {"over": len(report["over"]), "today": len(report["today"]),
                   "soon": len(report["soon"]), "attn": len(report["attn"])},
        "done": report.get("done", []), "added": report.get("added", []),
        "stuck_tasks": stuck,
    }
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def apply_ai():
    """Claude が書いた ai-advice.json を reports-data.js に取り込む。"""
    if not os.path.exists(AI_ADVICE):
        print("[apply] ai-advice.json が無いためスキップ")
        return
    advice = json.load(open(AI_ADVICE, encoding="utf-8"))
    target_id = advice.get("id")
    by_title = {t["title"]: t for t in advice.get("tasks", [])}
    reports = load_reports()
    hit = False
    for rep in reports:
        if rep.get("id") != target_id:
            continue
        hit = True
        if advice.get("briefing"):
            rep["aiBriefing"] = advice["briefing"]
        for key in ("over", "today", "attn"):
            for it in rep.get(key, []):
                t = by_title.get(it["title"])
                if not t:
                    continue
                if t.get("insight"):
                    it["aiInsight"] = t["insight"]
                if t.get("prompt"):
                    it["aiPrompt"] = t["prompt"]
    if hit:
        write_data(reports)
        print(f"[apply] AI分析を取り込みました id={target_id} "
              f"tasks={len(by_title)} briefing={'有' if advice.get('briefing') else '無'}")
    else:
        print(f"[apply] id={target_id} に一致する記録が見つかりません")


def main():
    today = datetime.date.today()
    rows = fetch_tasks()
    report = build_report(rows, today)

    # 時刻ごとに別エントリとして残す（同一分の再実行のみ上書き）。
    existing = load_reports()
    others = [r for r in existing if r.get("id") != report["id"]]
    past = sorted((r for r in others if r.get("id", "") < report["id"]),
                  key=lambda x: x["id"], reverse=True)
    make_message(report, past[0] if past else None)
    reports = others + [report]
    reports.sort(key=lambda x: x["id"], reverse=True)

    write_data(reports)
    write_pending(report)
    print(f"[ok] {report['id']} : active={report['stats']['active']} "
          f"over={len(report['over'])} today={len(report['today'])} "
          f"attn={len(report['attn'])} done={len(report.get('done',[]))} "
          f"added={len(report.get('added',[]))} mood={report.get('mood')} "
          f"/ 蓄積 {len(reports)}件")
    print(f"     msg: {report.get('message','')}")
    print(f"     pending: {PENDING}（このファイルのstuck_tasksを読んでAI分析→{AI_ADVICE}に書く）")


if __name__ == "__main__":
    import sys
    if "--apply" in sys.argv:
        apply_ai()
    else:
        main()
