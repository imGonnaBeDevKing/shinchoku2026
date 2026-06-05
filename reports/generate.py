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
            "requester": g("requester"),
        })
    return rows


def pdate(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


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
            "days": days,
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
        "over": over, "today": td, "soon": soon, "attn": attn,
        "recommend": rec,
    }


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


def main():
    today = datetime.date.today()
    rows = fetch_tasks()
    report = build_report(rows, today)

    # 時刻ごとに別エントリとして残す（同一分の再実行のみ上書き）。
    # 旧データ（idなし＝日付単位）も id を補完して取り込む。
    existing = []
    for r in load_existing():
        if "id" not in r:
            r["id"] = r.get("date", "") + " " + r.get("time", "00:00")
        existing.append(r)
    reports = [r for r in existing if r.get("id") != report["id"]]
    reports.append(report)
    reports.sort(key=lambda x: x["id"], reverse=True)

    body = json.dumps(reports, ensure_ascii=False, indent=2)
    with open(DATA_JS, "w", encoding="utf-8") as f:
        f.write("window.SHINCHOKU_REPORTS = " + body + ";\n")
    print(f"[ok] {report['id']} : active={report['stats']['active']} "
          f"over={len(report['over'])} today={len(report['today'])} "
          f"attn={len(report['attn'])} / 蓄積 {len(reports)}日分")


if __name__ == "__main__":
    main()
