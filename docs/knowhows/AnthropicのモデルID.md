Anthropic のモデル ID
=====================

# 概要

Claude API のモデル ID は、4.6 世代以降、日付の付かない ID そのものが固定のスナップショットである。日付付きの ID は無い。

## 全体像

- 確認日 : 2026-10-29（https://platform.claude.com/docs/en/about-claude/models/overview）
- 現行モデルの Claude API の ID（日付付きの ID は掲載されていない）
  - Claude Fable 5.1 : claude-fable-5-1
  - Claude Opus 5.5 : claude-opus-5-5
  - Claude Sonnet 5.5 : claude-sonnet-5-5
  - Claude Haiku 5.5 : claude-haiku-5-5
- ページの記載（原文）
  - "Every Claude model ID is a pinned snapshot, including the dateless IDs used from the 4.6 generation on."
  - "For models before the 4.6 generation, the alias is a convenience pointer that resolves to the dated ID. Dateless IDs are their own pinned snapshot; the alias row repeats them."
- 4.6 より前の世代は、日付の無い名前が別名（中身が差し替わりうる）で、日付付きの ID が固定のスナップショットである


# 細則

- 同じページの記載では、4 モデルともコンテキスト長は 1M トークン、最大出力は 128K トークン
- 思考（thinking）は adaptive で、Fable 5.1 と Opus 5.5 では常に有効。既定の effort は Fable 5.1・Sonnet 5.5 が high、Opus 5.5・Haiku 5.5 が medium
- 提供終了は早くても、Fable 5.1 が 2027-09-01、Opus 5.5 が 2027-09-22、Sonnet 5.5 が 2027-09-28、Haiku 5.5 が 2027-10-07
