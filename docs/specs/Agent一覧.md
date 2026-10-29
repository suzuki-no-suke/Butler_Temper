Agent 一覧
==========

# 概要

本資料は、Backend に用意する Agent（BOT の動き方の定義）と、その既定の動作を定める。

## 全体像

- 二層の秘密開示（secret-keeper） : メインとサブの二層。直近の会話と要約（メモリ）で会話し、条件を満たすとサブが秘密を開示する
- Jev 判定で秘匿情報を伝える（secret-relay） : 開示条件を TypeSafe AI の Jev が判定し、満たしたら秘匿情報をメインに伝える
- シンプル会話（claude-simple-fable / -opus / -sonnet / -haiku） : システムプロンプトだけを設定して会話する
- 各 Agent の設定の項目と既定値は、コード（apps/backend/src/bt_backend/agents）が原本。BOT 設定画面で確認できる
- モデル ID は日付の付かない ID を使う。4.6 世代以降は日付の無い ID 自体が固定のスナップショットで、日付付きの ID は無い（docs/knowhows/AnthropicのモデルID.md）


# 作業手順

1. Agent を足すときは apps/backend/src/bt_backend/agents に Agent のクラスを作り、registry.py に登録する
2. 設定の項目は AgentSettings を継承したモデルで定義し、すべての項目に既定値を付ける
3. 本資料に Agent を書き足す


# 二層の秘密開示（secret-keeper）

メイン（Opus 5.5）が利用者と会話し、サブ（Haiku 5.5）が裏で会話を見守る。会話が開示条件を満たすと、サブが秘密を開示する。

## 細則

- モデル
  - main : claude-opus-5-5
  - sub : claude-haiku-5-5
- メインに渡すコンテキスト
  - 直近 memory.recent_chars 文字（既定 5000。トークン数ではない）までの会話
  - それより前の会話の要約（メモリ）。システムプロンプトの後ろに付ける
- メモリ
  - 直近の範囲から外れた会話のうち、まだ要約していないものを、サブが前の要約と合わせて要約し直す
  - 要約と、どの発言まで要約したかは、Agent の状態として保存する
- 開示
  - サブは毎ターン、メインの応答の後に、会話が condition を満たしたかを判定する
  - 満たしていれば、サブ自身が secret を開示する発言を作り、メインの応答の後に表示する
  - メインには secret を渡さない
  - disclose_once が true（既定）なら、一度開示した後は判定しない
  - 判定の出力が読めない場合は開示しない
- 会話履歴としては、メインの発言だけを次のターンに渡す。サブの発言は表示用の内訳として保存する

(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-Agent方式.md)


# Jev 判定で秘匿情報を伝える（secret-relay）

メイン（Sonnet 5.5）が会話する。開示条件を満たしたかを TypeSafe AI の Jev が判定し、満たしたら秘匿情報をメインのシステムプロンプトに加え、メインが主人に伝える。

## 細則

- モデル
  - main : claude-sonnet-5-5
  - judge : jev-latest（TypeSafe AI）
  - (※ 現状、Jev は別名 jev-latest を使っている。固定の版の名前を確かめられていないため)
- 判定
  - 毎ターン、メインの応答の前に判定する
  - 直近 judge.recent_chars 文字（既定 5000）の会話を、状態（state）として Jev に渡す
  - condition を、はい／いいえの質問（noul）として Jev に渡す。judge.criteria_true / criteria_false があれば一緒に渡す
  - Jev が返すはいの確率が threshold（既定 0.8）以上なら開示済みにする
  - disclose_once が true（既定）なら、一度開示した後は判定しない
- 開示
  - 開示済みなら、main.secret_instruction（{secret} を secret に置き換えたもの）をシステムプロンプトの後ろに付ける
  - 開示前のメインには secret を渡さない
- メインには直近 main.context_chars 文字（既定 40000）までの会話を送る。要約はしない
- TypeSafe AI の API キーは BT_TYPESAFE_API_KEY（または TYPESAFE_API_KEY）で渡す

(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-Jev判定Agent.md)


# シンプル会話（claude-simple-*）

システムプロンプトだけを設定して会話する。最新の Fable / Opus / Sonnet / Haiku の四つを用意する。

## 細則

- モデル
  - claude-simple-fable : claude-fable-5-1
  - claude-simple-opus : claude-opus-5-5
  - claude-simple-sonnet : claude-sonnet-5-5
  - claude-simple-haiku : claude-haiku-5-5
- 直近 context_chars 文字（既定 40000）までの会話を毎回送る。それより前の会話は送らず、要約もしない

(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-Agent方式.md)


# 関連資料

## (仕様: docs/specs/アプリケーション仕様.md)

- BOT と Agent の関係、BOT 設定画面についての原本
