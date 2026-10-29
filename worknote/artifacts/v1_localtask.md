v1 手元で確認すること
=====================

# 概要

v1（2026-10-29 時点の claude ブランチ）のうち、クラウドのセッションでは確かめられず、手元で確認することの一覧。

## 全体像

- PostgreSQL での動作
- 本番相当の配置（Apache での Frontend の静的配信、systemd からの Backend の起動）
- TypeSafe AI（Jev）との疎通
- 本物の LLM API での各 Agent の動作


# 作業手順

1. 最新の claude ブランチを取り込む（`git pull origin claude`）
2. `npm install` のあと `npm run check` を流し、すべて通ることを確かめる
3. 下の項目を順に確かめ、結果（うまくいかなかった場合はエラーの内容）を記録する


# PostgreSQL での動作

SQLite と PostgreSQL の両対応で作ったが、SQLite でしか動かしていない。

## 細則

- 環境変数 `BT_DATABASE_URL` と `BT_RAW_DATABASE_URL` に PostgreSQL の接続先を入れる
  - 例) `postgresql+psycopg://user:pass@localhost/butler_temper`
  - PostgreSQL のドライバ（psycopg など）は、まだ依存ライブラリに入れていない。`cd apps/backend && uv add "psycopg[binary]"` などで足す必要がある
- `npm run migrate` が通るか（通常の DB と RAW 用の DB の二つ）
- `npm run dev` で起動し、BOT の作成、会話、コメント、設定変更チャット、履歴が動くか
- 確かめたい点
  - JSON の列（設定、Agent の状態、RAW）が読み書きできるか
  - 日時がずれないか（UTC で保存している）


# 本番相当の配置

Apache などで Frontend を静的配信し、Backend は systemd から起動する想定だが、手順も含めて未着手。

## 細則

- Frontend
  - `VITE_API_BASE` に Backend の URL を入れてビルドする（`cd apps/frontend && VITE_API_BASE=https://... npm run build`）
  - `apps/frontend/dist` を Apache の公開フォルダに置く。相対パスで出力しているので、サブパスに置いてもよい
  - HashRouter なので、Apache 側の URL 書き換え設定は要らない
- Backend
  - `uv run --project apps/backend uvicorn bt_backend.main:app --host ... --port ...` を systemd のサービスにする
  - 設定と API キーは systemd の環境変数（EnvironmentFile など）で渡す。`BT_DATA_DIR` は書き込める場所にする
  - `BT_CORS_ORIGINS` に Frontend の配信元を入れる（既定は全許可）
  - 起動前に `npm run migrate`（または `uv run --project apps/backend python apps/migrate/migrate.py upgrade`）を流す
- 確かめたい点
  - 起動時に `data/agent_snapshots/<ハッシュ>.zip` が作られるか（配置先でも Agents のソースが読めるか）


# TypeSafe AI（Jev）との疎通

クラウドのセッションでは、ネットワーク設定で api.typesafe.ai への接続が拒否され、確かめられていない。

## 細則

- `secrets/secrets.env` に `BT_TYPESAFE_API_KEY=...` を書く
- `npm run check:connectivity` を流し、[TypeSafe AI] が OK になるか
  - モデル一覧が表示されるので、jev-latest ではない固定の版の名前を控える（secret-relay Agent を固定の版にするため）
- 「Jev 判定で秘匿情報を伝える」BOT で会話し、開示条件を満たすと秘密が伝わるか
  - 各ターンの「Agent の状態」の last_judge に、秘密ごとの確率が出る


# 本物の LLM API での各 Agent の動作

テストは偽の API で行っている。本物の API では、Anthropic の疎通と設定変更チャットの一回の呼び出しだけを確かめた。

## 細則

- シンプル会話（Fable / Opus / Sonnet / Haiku）で会話できるか
- 応答が途中で切れないか
  - Fable 5.1 と Opus 5.5 は思考（thinking）が常に有効。思考の分も max_tokens に含まれる可能性がある（裏は取っていない）
  - 切れる場合は、設定 JSON の max_tokens を増やす
- 二層の秘密開示で、要約（メモリ）と、秘密ごとの開示が期待どおりに動くか
  - サブ（Haiku 5.5）が判定の JSON を正しく返すか。読めない場合は開示しない作りになっている
- 設定変更チャットで、変更案が「編集中の設定」に反映されるか
- 履歴の「引き継いで続ける」で、エラーで止まった会話を続けられるか
- Windows で `npm run dev` が起動するか（alembic.ini の文字コードの問題は直したが、Windows では確かめていない）


# 関連資料

## (手順: README.md)

- ローカルでの起動、環境変数、チェックと疎通確認のコマンド
