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
ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...
# GEMINI_API_KEY=...
# OPENROUTER_API_KEY=...
```

2. 依存ライブラリを入れる

```bash
cd apps/backend && uv sync
```

```bash
cd apps/frontend && npm install
```

3. DB を作る（リポジトリ直下で実行。data フォルダに作られる）

```bash
npm run migrate
```

4. Backend と Frontend を起動する（それぞれ別の端末で、リポジトリ直下で実行）

```bash
npm run dev:backend
```

```bash
npm run dev:frontend
```

5. ブラウザで http://localhost:5173/ を開く


# 設定（環境変数）

- `BT_DATA_DIR` : データの置き場所（既定はリポジトリ直下の data）
- `BT_DATABASE_URL` : 通常の DB（既定は `sqlite:///<BT_DATA_DIR>/app.db`。PostgreSQL も可）
- `BT_RAW_DATABASE_URL` : RAW 用の DB（既定は `sqlite:///<BT_DATA_DIR>/raw.db`）
- `BT_CORS_ORIGINS` : Frontend の配信元（JSON の配列。既定は `["*"]`）
- `BT_ENV_FILE` : 読み込む env ファイル（既定は secrets/secrets.env）
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY`
- Frontend の `VITE_API_BASE` : Backend の URL（ビルド時に指定。既定は http://localhost:8000）


# チェック

```bash
npm run check
```

Backend（ruff / mypy / pytest）、Frontend（tsc / oxlint / Vitest）、マイグレーションの差分を確かめる。
