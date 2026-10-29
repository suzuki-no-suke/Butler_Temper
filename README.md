Butler Temper
=============

チャットボットのプロンプトによる展開・性格表出について、調査・調整を行うためのアプリケーション。

- 仕様 : docs/specs/アプリケーション仕様.md
- 実装環境 : docs/specs/実装環境.md
- フォルダ構成 : docs/specs/フォルダ構成.md


# ローカルでの起動

必要なもの : uv、Node.js（npm）

1. `secrets/secrets.env` を作り、使う LLM API のキーを書く（secrets フォルダは Git に入らない）

```
BT_ANTHROPIC_API_KEY=...
# BT_OPENAI_API_KEY=...
# BT_GEMINI_API_KEY=...
# BT_OPENROUTER_API_KEY=...
```

2. 依存ライブラリを入れる（リポジトリ直下で実行。Frontend の分も一緒に入る。Python 側は起動時に uv が自動で入れる）

```bash
npm install
```

3. 起動する（リポジトリ直下で実行）

```bash
npm run dev
```

- DB のマイグレーション（data フォルダに作成・更新）と、BOT が一つも無いときの BOT の作成（各 Agent の既定の設定）をしてから、Backend（http://localhost:8000）と Frontend（http://localhost:5173）を同時に起動する
- Ctrl+C で両方とも止まる
- 片方だけ起動するときは `npm run dev:backend` / `npm run dev:frontend`、マイグレーションだけなら `npm run migrate`、BOT の作成だけなら `npm run seed`
- BOT 設定を JSON に書き出すときは `npm run export:bots`（既定の書き出し先は data/exports/bot_settings）

4. ブラウザで http://localhost:5173/ を開く


# 設定（環境変数）

- `BT_DATA_DIR` : データの置き場所（既定はリポジトリ直下の data）
- `BT_DATABASE_URL` : 通常の DB（既定は `sqlite:///<BT_DATA_DIR>/app.db`。PostgreSQL も可）
- `BT_RAW_DATABASE_URL` : RAW 用の DB（既定は `sqlite:///<BT_DATA_DIR>/raw.db`）
- `BT_CORS_ORIGINS` : Frontend の配信元（JSON の配列。既定は `["*"]`）
- `BT_ENV_FILE` : 読み込む env ファイル（既定は secrets/secrets.env）
- `BT_ANTHROPIC_API_KEY` / `BT_OPENAI_API_KEY` / `BT_GEMINI_API_KEY` / `BT_OPENROUTER_API_KEY` / `BT_TYPESAFE_API_KEY`
  - `BT_` の無い名前（`ANTHROPIC_API_KEY` など）も読む。両方あれば `BT_` 付きを使う
  - Claude Code など、`ANTHROPIC_API_KEY` を自分で使う道具と同じ環境では `BT_` 付きを使う
- Frontend の `VITE_API_BASE` : Backend の URL（ビルド時に指定。既定は http://localhost:8000）


# チェック

```bash
npm run check
```

Backend（ruff / mypy / pytest）、Frontend（tsc / oxlint / Vitest）、マイグレーションの差分を確かめる。

LLM API への疎通（設定されている API キーごとに、モデル一覧の取得と最小の呼び出し）は次で確かめる。実際に API を呼ぶので、少額の料金がかかる。

```bash
npm run check:connectivity
```
