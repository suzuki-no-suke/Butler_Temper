PydanticAI の Anthropic 呼び出し
================================

# 概要

PydanticAI（2.63.0）で Anthropic のモデルを使うとき、max_tokens を指定しないと裏側でストリーミングの通信になる。

## 全体像

- 確認日 : 2026-10-29。pydantic_ai/models/anthropic/__init__.py のソースによる
- max_tokens を指定しないと、モデルの最大出力（Claude 5.x では 128K）を送る
- max_tokens が約 21,333 を超えると、Anthropic SDK の決まり（10 分を超えうる応答はストリーミングが必要）に従い、PydanticAI が裏側でストリーミングの通信をする
- ストリーミングにしたくない場合は、model_settings の max_tokens を明示する（例 : 8192）
- 構造化出力（output_type）は、Claude 5.x ではツールではなく output_config（JSON スキーマ）で送られる。応答は JSON のテキストとして返る
