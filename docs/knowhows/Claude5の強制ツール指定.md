Claude 5 系の強制ツール指定
==========================

# 概要

Claude Sonnet 5.5 などでは、tool_choice でツールを強制する指定（type が tool / any）が 400 になる。auto にして、指示でツールを呼ばせる。

## 全体像

- 確認日 : 2026-10-30
- 実際の API で、claude-sonnet-5-5 に `tool_choice: {"type": "tool", "name": ...}` を送ると、次の 400 が返った
  - `tool_choice: type "tool" and "any" are not supported for this model.`
- claude-api スキルの記載では、Claude Fable 5.1 / Claude Opus 5.5 / Claude Sonnet 5.5 が同じく受け付けない
- 代わりの手段（同じ記載）
  - `tool_choice: {"type": "auto"}` にし、プロンプトでツールを名指しして呼ばせる
  - ツールの定義に `strict: true` を付けると、引数が型どおりになる（JSON Schema に additionalProperties: false と required が要る）
  - JSON を返させることだけが目的なら、構造化出力（output_config.format）を使う
- `tool_choice: {"type": "none"}` は使える


# 細則

- LLM シミュレータのまとめる回は、auto と指示で submit_result を呼ばせ、呼ばなければ失敗にしている（呼ぶ側の output_schema が strict の条件を満たすとは限らないため、strict は付けていない）
- Claude 5 系は thinking が既定で有効なので、ツールのやり取りを続けるときは、応答の内容（thinking ブロックを含む）をそのまま assistant の発言として返す

(作業ログ: worknote/worklog/0004-2026-10-30-シミュレータ.md)
