LLM SDK の引数と送信パラメーター
================================

# 概要

各社の Python SDK は、API が受け付けるパラメーターの一部を関数の引数として持たないことがある。その場合は extra_body で送る。

## 全体像

- 確認時点（2026-10-29）の anthropic SDK 2.3.0 の `messages.create` は、`temperature` / `top_p` / `top_k` を引数に持たない
  - 引数で渡すと `TypeError: Messages.create() got an unexpected keyword argument 'temperature'` になる
- SDK が知らないパラメーターは `extra_body` に入れると、リクエストの JSON にそのまま入る
- Backend では apps/backend/src/bt_backend/agents/params.py の `call_with_params` で、SDK の関数の引数に無いものを自動で extra_body に回している
- 同じ時点の anthropic / openai SDK は、httpx ではなく httpx2 のクライアントを受け取る。google-genai は httpx / httpx2 のどちらも受け取る


# 細則

- 確認した版
  - anthropic 2.3.0
  - openai 3.41.0
  - google-genai 2.33.0
- API 側がそのパラメーターを受け付けるかどうかは、SDK の引数の有無とは別の話である。受け付けない場合は API がエラーを返し、会話はエラーとして保存されて止まる
