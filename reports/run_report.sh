#!/bin/bash
# shinchoku2026 レポート自動生成・公開（launchd から定時実行）
# 1) generate.py で集計＋_pending.json出力
# 2) Claude(Opus) をヘッドレス起動してAI分析(ai-advice.json)を書かせる
# 3) generate.py --apply でAI分析を統合
# 4) ブラウザ表示＋GitHubへ公開
# AI分析が失敗してもデータ版レポートは必ず公開される（取りこぼしゼロ）。

REPO="/Users/macminim4pro/shinchoku2026"
RDIR="$REPO/reports"
LOG="$RDIR/cron.log"
CLAUDE="/Users/macminim4pro/.local/bin/claude"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:/Users/macminim4pro/.local/bin:$PATH"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') launchd run ====="
  cd "$RDIR" || { echo "cd失敗"; exit 1; }

  # 1) データ集計
  /usr/bin/python3 generate.py

  # 2) AI分析（ヘッドレスClaude）。失敗・タイムアウトしてもデータ版は残る。
  rm -f ai-advice.json
  echo "--- claude AI分析 開始 ---"
  "$CLAUDE" -p "$(cat ai_instructions.md)" \
      --allowedTools "Read Write" \
      --permission-mode acceptEdits \
      --model opus \
      --max-budget-usd 1.00 \
      --no-session-persistence 2>&1 | tail -3
  echo "--- claude AI分析 終了 ---"

  # 3) AI分析を統合（ai-advice.jsonが無ければデータ版のまま）
  /usr/bin/python3 generate.py --apply

  # 4) ブラウザ表示
  /usr/bin/open "$RDIR/index.html"

  # 5) GitHub公開
  cd "$REPO" || exit 1
  /usr/bin/git add reports/reports-data.js
  if /usr/bin/git diff --cached --quiet; then
    echo "変更なし: commit/pushスキップ"
  else
    /usr/bin/git commit -m "chore: 進捗レポート自動更新 $(date +%Y-%m-%d_%H:%M)"
    /usr/bin/git push
  fi
  echo "done $(date '+%H:%M:%S')"
} >> "$LOG" 2>&1
