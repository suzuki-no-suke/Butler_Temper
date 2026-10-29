Agent 一覧
==========

# 概要

本資料は、Backend に用意する Agent（BOT の動き方の定義）と、その既定の動作を定める。

## 全体像

- 二層の秘密開示（secret-keeper） : メインとサブの二層。直近の会話と要約（メモリ）で会話し、条件を満たすとサブが秘密を開示する
- Jev 判定で秘匿情報を伝える（secret-relay） : 開示条件を TypeSafe AI の Jev が判定し、満たしたら秘匿情報をメインに伝える
- 秘密開示系の二つは、秘密と開示条件の組を secrets に複数書ける
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
- 秘密
  - secrets に、名前（name）・秘密（secret）・開示条件（condition）の組を複数書ける。name は重複させてはならない
  - 開示済みの秘密は、Agent の状態の disclosed に name の一覧として残る
- 開示
  - サブは毎ターン、メインの応答の後に、まだ開示していない秘密それぞれについて、会話が condition を満たしたかを一回の呼び出しでまとめて判定する
  - 満たした秘密ごとに、サブ自身がその秘密を開示する発言を作り、メインの応答の後に表示する
  - メインには secret を渡さない
  - disclose_once が true（既定）なら、一度開示した秘密は以後判定しない
  - 判定の出力が読めない場合は、どの秘密も開示しない
- 会話履歴としては、メインの発言だけを次のターンに渡す。サブの発言は表示用の内訳として保存する

(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-Agent方式.md)
(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-履歴と複数の秘密.md)


# Jev 判定で秘匿情報を伝える（secret-relay）

メイン（Sonnet 5.5）が会話する。開示条件を満たしたかを TypeSafe AI の Jev が判定し、満たしたら秘匿情報をメインのシステムプロンプトに加え、メインが主人に伝える。

## 細則

- モデル
  - main : claude-sonnet-5-5
  - judge : jev-latest（TypeSafe AI）
  - (※ 現状、Jev は別名 jev-latest を使っている。固定の版の名前を確かめられていないため)
- 秘密
  - secrets に、名前（name）・秘密（secret）・開示条件（condition）の組を複数書ける。name は重複させてはならない
  - 秘密ごとに、しきい値（threshold）と、はい／いいえとみなす状態の説明（criteria_true / criteria_false）を書ける
  - 開示済みの秘密は、Agent の状態の disclosed に name の一覧として残る
- 判定
  - 毎ターン、メインの応答の前に判定する
  - 直近 judge.recent_chars 文字（既定 5000）の会話を、状態（state）として Jev に渡す
  - まだ開示していない秘密それぞれの condition を、はい／いいえの質問（noul）として、一回の呼び出しでまとめて Jev に渡す
  - Jev が返すはいの確率が、その秘密のしきい値（無ければ全体の threshold。既定 0.8）以上なら開示済みにする
  - disclose_once が true（既定）なら、一度開示した秘密は以後判定しない
- 開示
  - 開示済みの秘密があれば、main.secret_instruction（{secrets} を開示済みの秘密の一覧に置き換えたもの）をシステムプロンプトの後ろに付ける
  - 開示前の秘密はメインに渡さない
- メインには直近 main.context_chars 文字（既定 40000）までの会話を送る。要約はしない
- TypeSafe AI の API キーは BT_TYPESAFE_API_KEY（または TYPESAFE_API_KEY）で渡す

(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-Jev判定Agent.md)
(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-履歴と複数の秘密.md)


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


# 秘密が一つだった頃の設定

保存済みの古いバージョンの設定（secret / condition を直接持つ形）も、そのまま使える。

## 細則

- 古い設定は、name が secret の秘密一つとして読む
- secret-keeper : 古い sub.judge_instruction は出力の形が違うため、読み込むときに既定の指示文に戻す
- secret-relay : 古い judge.criteria_true / criteria_false は、その秘密の説明として読む。main.secret_instruction の {secret} は、開示済みの秘密の一覧に置き換える
- 古い状態（disclosed が true）は、その一つの秘密を開示済みとして読む

(決定経緯 : 2026-10-29, docs/decisions/2026-10-29-履歴と複数の秘密.md)


# 関連資料

## (仕様: docs/specs/アプリケーション仕様.md)

- BOT と Agent の関係、BOT 設定画面についての原本
