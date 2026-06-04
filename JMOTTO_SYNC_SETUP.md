# J-MOTTO 予定 → ダッシュボード同期 セットアップ手順（A案 / 一番簡単な方式）

## 仕組み（かんたん版）

```
[1] J-MOTTO  ──手動で同期ボタンを押す──▶  Teams/Outlook 予定表
[2] Outlook  ──Power Automate(自動)──▶  Firestore: external_events
[3] Firestore  ──ダッシュボードが自動読み取り──▶  カレンダーに紫色で表示
```

- **J-MOTTOから直接は取らない**。同期ボタンでOutlookに入った予定を読むだけ。
- Power Automate は「**①ログイン → ②Outlook予定を取得 → ③Firestoreに保存**」の3ステップだけ。
- **鍵ファイル・Cloud Functions・JWT署名は不要**。アプリと同じログイン方式（メール＋パスワード）を使う。

---

## STEP 1. Bot用ログインアカウントを作る（Firebase）

1. [Firebase Console](https://console.firebase.google.com/) → プロジェクト **kikakugyoumu-907d6**
2. **Authentication** → **Users** → **ユーザーを追加**
3. メール: `jmotto-bot@<会社ドメイン>`、パスワード: 任意の強固なもの → 作成
4. 作成後に表示される **ユーザーUID** を控える（STEP2で使う）

> これは「Power Automate専用の利用者アカウント」。人は使わない。

---

## STEP 2. Firestoreルール（Botだけ書き込み許可）

Firebase Console → **Firestore Database** → **ルール** に以下を追記。

```
match /external_events/{docId} {
  allow read:  if true;                                   // 既存tasksのread条件に合わせる
  allow write: if request.auth != null
               && request.auth.uid == 'STEP1で控えたBotのUID';
}
```

> read条件は既存の `tasks` に合わせる（例: `if request.auth != null;`）。

---

## STEP 3. Power Automate フロー作成

[make.powerautomate.com](https://make.powerautomate.com) → **自動化したクラウド フロー** ではなく **スケジュール済みクラウド フロー** を新規作成。

> ※ HTTPアクションは Power Automate プレミアム機能。利用可否を会社の管理者に確認。

### トリガー：繰り返し

- 「**繰り返し**」 1時間ごと（または1日3回など）

### アクション①：Botでログインしてトークン取得（HTTP）

```
メソッド: POST
URI: https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSy... (index.htmlのapiKey)
ヘッダー: Content-Type = application/json
本文:
{
  "email": "jmotto-bot@<会社ドメイン>",
  "password": "STEP1で決めたパスワード",
  "returnSecureToken": true
}
```

→ レスポンスの `idToken` を次で使う（「JSONの解析」アクションで `idToken` を取り出すか、`body('HTTP')['idToken']` で参照）。

### アクション②：Outlookの予定を取得

- `Office 365 Outlook` → 「**イベントの取得 (V3)**」
  - カレンダーID = 自分の予定表
  - 期間フィルタで当日〜14日後など

### アクション③：各予定をFirestoreへ保存（Apply to each + HTTP）

「イベントの取得」の `value` に対して **Apply to each**、中で HTTP：

```
メソッド: PATCH
URI: https://firestore.googleapis.com/v1/projects/kikakugyoumu-907d6/databases/(default)/documents/external_events/@{items('Apply_to_each')?['id']}
ヘッダー:
  Authorization = Bearer @{outputs('HTTP')?['body']?['idToken']}
  Content-Type  = application/json
本文:
{
  "fields": {
    "title":    { "stringValue": "@{items('Apply_to_each')?['subject']}" },
    "start":    { "stringValue": "@{items('Apply_to_each')?['start']}" },
    "end":      { "stringValue": "@{items('Apply_to_each')?['end']}" },
    "allDay":   { "booleanValue": @{items('Apply_to_each')?['isAllDay']} },
    "source":   { "stringValue": "jmotto" },
    "location": { "stringValue": "@{items('Apply_to_each')?['location']?['displayName']}" }
  }
}
```

> ドキュメントID に Outlookイベントの `id` を使うので、更新時も重複せず上書きされる。

---

## STEP 4. 動作確認

1. J-MOTTOで予定を作成 → **J-MOTTOの同期ボタン**を押してOutlookへ反映
2. Power Automate を手動実行
3. Firebase Console の Firestore `external_events` にドキュメントが増えるか確認
4. ダッシュボードのカレンダーを開く → **紫色のイベント**が出ればOK

---

## 運用ルール

- **J-MOTTOの同期ボタンを押す**のだけが手作業（1日1回など）
- 以降はOutlook→Firestore→ダッシュボードまで自動

---

## ダッシュボード側（実装済み・コード変更不要）

- `fetchExternalEvents()`：`external_events` を読む（未作成でもエラーで止まらない）
- `externalEventsToCalendarEvents()`：紫色(#5856D6)のカレンダーイベントへ変換
- `calendarEvents()`：祝日・タスクと一緒に表示

→ Firestoreに `external_events` が入れば自動で表示される。
