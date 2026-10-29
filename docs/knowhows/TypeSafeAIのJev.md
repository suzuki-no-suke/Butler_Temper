TypeSafe AI の Jev
==================

# 概要

Jev は TypeSafe AI の「System One」の判定用モデルで、文章を生成せず、状態と型付きの質問を受け取り、確率付きの答えを返す。

## 全体像

- 確認日 : 2026-10-29。Python SDK（typesafe-sdk 0.7.5）のソースと、Web 上の紹介記事による
- エンドポイント : POST https://api.typesafe.ai/v1/systemone（Bearer 認証）。モデル一覧は GET /v1/models
- 質問の型
  - noul : はい／いいえ。答えは「はいの確率」（0〜1）
  - choice : 名前付きの選択肢から選ぶ
  - score : 順序付きの尺度で採点する
  - box : 画像内の位置
- 答えは宣言した選択肢の中からしか返らないので、JSON の読み取りに失敗する心配が無い
- SDK の既定のモデルは jev-latest（別名）。紹介記事では jev-1.13 系が現行とされるが、API では確かめていない


# 細則

- SDK（typesafe-sdk）
  - `TypeSafeClient(api_key=..., model=..., http_client=..., retry=RetryPolicy(max_retries=0), compression=False)`
  - `client.system_one(state=..., questions={"名前": Noul(instructions=...)})` の答えは `result.nouls["名前"].noul`
  - 既定ではリクエスト本文を zstd で圧縮する。記録した本文を読みたい場合は compression=False にする
  - 既定ではリトライする（max_retries=2）
  - httpx ではなく httpx2 のクライアントを受け取る
  - 環境変数 TYPESAFE_API_KEY / TYPESAFE_BASE_URL / TYPESAFE_DEFAULT_MODEL も読む
- Web 上の紹介記事では、初期の SDK のマイナー版で質問の型に破壊的な変更が入ったことがある、とされている
- 料金・速度は提供元の公称で、確かめていない
