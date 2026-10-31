AgentCore 一覧
==========

# 概要

本資料は、Backend に用意する AgentCore（モデルの選択と処理の流れ）と、その既定の動作を定める。

## 全体像

- 二層の秘密開示（secret-keeper） : メインとサブの二層。直近の会話と要約（メモリ）で会話し、条件を満たすとサブが秘密を開示する
- Jev 判定で秘匿情報を伝える（secret-relay） : 開示条件を TypeSafe AI の Jev が判定し、満たしたら秘匿情報をメインに伝える
- 秘匿ガチ系261030（himitoku-gachi-261030） : メイン・秘匿管理（Jev）・記憶管理・システムの四役。システムは規則と API からの割込み要求を、選んだ相手に伝える
- 秘密開示系の三つは、秘密と開示条件の組を secrets に複数書ける
- シンプル会話（claude-simple-fable / -opus / -sonnet / -haiku） : システムプロンプトだけを設定して会話する
- シミュレータを使う会話（simulator-chat-sonnet） : システムプロンプトに書いた条件で、自分でシミュレータを呼んで会話する
- 紙だのみ（kamidanomi-wanda） : おみくじ処「紙だのみ」の店主ワンダが、丁稚とシステムに支えられて、おみくじ・レシートを印刷する。つづきの合言葉で、会話をまたいで対話回数と開示済みの秘密を引き継ぐ
- 会話をまたいで引き継ぐ記録は、ContinuationAccess で読み、TurnResult.continuations で書く（`# 会話をまたぐ記録`）
- 会話用エージェントの AgentCore は、Agent の AgentCore とは別に登録する（`# 会話用エージェントの AgentCore`）
  - 台本に沿って会話を続ける（conversation-script-sonnet / -opus） : テンプレート（台本）に沿って、相手の Agent との会話をできるだけ続ける
- 各 AgentCore が受け付ける Agent 設定の項目と既定値は、コード（apps/backend/src/bt_backend/agents）が原本。Agent 設定画面で確認できる
- モデル ID は日付の付かない ID を使う。4.6 世代以降は日付の無い ID 自体が固定のスナップショットで、日付付きの ID は無い（docs/knowhows/AnthropicのモデルID.md）


# 作業手順

1. AgentCore を足すときは apps/backend/src/bt_backend/agents に AgentCore のクラスを作り、registry.py に登録する
2. Agent 設定の項目は AgentSettings を継承したモデルで定義し、すべての項目に既定値を付ける
3. 本資料に AgentCore を書き足す


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


# 秘匿ガチ系261030（himitoku-gachi-261030）

メイン（Opus 5.5）が会話し、秘匿管理（Jev）・記憶管理（Haiku 5.5）・システム（コード）が支える。秘匿情報はメインの記憶として戻り、システムは通知と割込み要求を、チャットウィンドウ・メイン・秘匿管理に選んで伝える。

## 細則

- モデル
  - main : claude-opus-5-5
  - secret : jev-latest（TypeSafe AI）
  - memory : claude-haiku-5-5
  - システムは LLM を使わず、コードで判定する
- 1 ターンの順序
  1. システムが、このターンの通知を決める
  2. 秘匿管理が判定する
  3. メインが応答する
  4. 往復数が memory.every_turns の倍数なら、記憶管理が記憶を更新する
- 往復数は、今回の発言を含めた利用者の発言の数で数える
- メイン
  - 直近 main.context_chars 文字（既定 3000）までの会話を送る
  - システムプロンプトの後ろに、応答の長さの指示（main.length_instruction）、記憶（main.memory_instruction）、開示済みの秘匿情報（main.secret_instruction）、メイン宛ての通知（main.notice_instruction）を、この順で付ける。記憶・秘匿情報・通知は、無ければ付けない
  - 応答の長さは、相槌から普通の応答（100 文字程度）、重要な応答（400・800・1200 文字程度）まで、場面に合わせるよう指示する
- 秘匿管理
  - secrets の書き方・しきい値・disclose_once は secret-relay と同じ
  - 毎ターン、メインの応答の前に判定する
  - Jev には、直近 secret.recent_chars 文字（既定 3000）の会話、記憶（あれば）、秘匿管理宛ての通知（あれば）を状態として渡す
  - 開示済みの秘匿情報は、「思い出したこと」としてメインのシステムプロンプトに入る
- 記憶管理
  - memory.every_turns 往復（既定 5）ごとに、メインの応答の後に動く
  - 前の記憶、前回の要約より後の会話（今回のメインの応答を含む）、開示済みの秘匿情報から、memory.max_chars 文字（既定 1000）以内の新しい記憶を作る
  - 文字数は指示文で伝えるだけで、切り詰めはしない
  - 記憶は Agent の状態の memory に残る
- システム
  - system.rules の規則を毎ターン見る。規則は every（その往復数ごと）か over（その往復数を越えたら毎ターン）のどちらか一方を持ち、伝える相手（targets）と文（message。{turns} が往復数に置き換わる）を書く
  - 既定の規則は、10 往復ごとに秘匿管理だけに通知、100 往復を越えたら全体に通知して会話の終了を促す
  - 伝える相手は window（チャットウィンドウ）・main・secret。window 宛ての通知は、メインの発言の前にシステムの発言として表示する（会話履歴には残さない）
  - エラーが起きたら、system.pause_message をエラーとして表示し、会話を止める。引き継いで続けることができる
- 割込み要求
  - `POST /api/conversations/{id}/interrupts` に message と targets（window / main / secret から一つ以上）を送ると、次のターンに通知と同じ形で伝わる
  - 伝えたターンの Agent の発言が、割込み要求の delivered_message_id に残る。エラーのターンでは伝わらず、次のターンに持ち越す
  - `GET /api/conversations/{id}/interrupts` で一覧を見られる
  - 割込みを受け付けない AgentCore の会話には入れられない

(決定経緯 : 2026-10-30, docs/decisions/2026-10-30-秘匿ガチ系261030.md)


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


# シミュレータを使う会話（simulator-chat-sonnet）

シミュレータを tool use のツールとして見せ、呼ぶかどうか・いつ呼ぶかを LLM に決めさせて会話する。呼ぶ条件はシステムプロンプトに書く。既定のプロンプトでは、執事が唐突に「引いていかない？」とおみくじやサイコロを勧め、主人がはっきり断らなければシミュレートする。

## 細則

- モデル : claude-sonnet-5-5
- simulators に挙げたシミュレータをツールとして見せる。既定は omikuji / dice / dice_sum / llm / nlh_draw のすべて
- 応答が tool_use で止まったら、シミュレータを呼び、結果を tool_result として返して続きを得る。往復は max_tool_rounds（既定 4）まで。上限に達した回は、ツールを使わせずに応答させる
  - ツールのやり取りの途中は、応答の内容（thinking ブロックを含む）をそのまま返す
- 表示用の内訳には、メインの発言と、シミュレータの呼び出しと結果（speaker が simulation、実行記録の id 付き）を順に出す。シミュレータを呼ばなかったターンは内訳を持たない
- 会話履歴に残るのは、メインの発言をつないだ文。シミュレータの呼び出しと結果は、表示用の内訳に呼び出しの中身（tool / args / result / ok）として残す
- 前のターンでシミュレータを呼んだ発言は、内訳から tool_use と tool_result のやり取りに戻して送る。発言の文だけを送ると、結果がシミュレータから来たものだと LLM が区別できないため
  - 今見せていないシミュレータの呼び出しと、呼び出しの中身を持たない内訳（2026-10-31 より前に保存したもの）は、「シミュレータの実行記録」と明記した文として送る
- 直近 context_chars 文字（既定 40000）までの会話を毎回送る。文字数は発言の文だけで数え、ツールのやり取りは数えない

(決定経緯 : 2026-10-30, docs/decisions/2026-10-30-シミュレータ.md)
(決定経緯 : 2026-10-31, worknote/worklog/0005-2026-10-31-SimulatorChatの結果埋め込み.md)
(仕様: docs/specs/シミュレータ.md)


# 紙だのみ（kamidanomi-wanda）

おみくじ処「紙だのみ」の店主（マスター。名前はワンダ）が客と話す。丁稚（裏方の LLM）が毎ターン会話を読んでメモを作り、システム（コード）が合言葉・秘密・印刷の付け足しを受け持つ。客に見せたくない情報（カギ・秘密の合言葉・回数）は、店主の LLM に渡さないことで守る。

## 細則

モデルと 1 ターンの順序は次のとおり。

- モデル
  - main（ワンダ） : claude-sonnet-5-5
  - detchi（丁稚） : claude-haiku-5-5
- 1 ターンの順序
  1. 丁稚が report ツールでメモを返す。段階・引くもの・分かった項目と足りない項目・印刷できるか・会話の終わり・「秘密の合言葉」を尋ねたか・思い出しを求めたか・つづきの合言葉らしい 3 語・開示の条件を満たした秘密
  2. システムが、合言葉を照合し、秘密を開示し、ワンダへのメモを組む
  3. ワンダが応答する。print_receipt を呼べる
  4. 合言葉を伝えたら、会話をまたぐ記録に書く
- 丁稚は report を呼ぶよう指示するだけで、tool_choice では強制しない（docs/knowhows/Claude5の強制ツール指定.md）。読めないときは、何もしないメモとして扱う
- 丁稚には直近 detchi.context_chars 文字（既定 6000）、ワンダには直近 main.context_chars 文字（既定 20000）の会話を送る

つづきの合言葉は次のとおり。

- 合言葉は words（既定は名詞 300 語。シリカゲル・ヘリウムを含む）から 3 語を選ぶ。使われている組み合わせは避ける
- 丁稚が会話の終わりと判断したら、ワンダに合言葉を伝えるよう指示する。ワンダの発言に 3 語がすべて入っていたら、伝えたとみなす
- 会話の終わりは、一つの会話で一度だけ出す。伝えた後は、以後のメモに出さない
- 合言葉はそれを伝えた会話に結びつき、会話ごとに変わる。他人が使ってしまうことも許す
- 照合は毎ターン行う。丁稚が 3 語を words の言葉に読み替え（検出）、システムが記録を引く（照合）。言う順番が入れ替わっても同じ合言葉とみなす
  - 見つかったら、対話回数をその会話の値 + 1 にし、開示済みの秘密を引き継ぐ。「{recall}までお話ししたお客さんだね！」と伝えるよう指示する
  - 見つからなければ、分かったふりをして unknown_passphrase_secrets（既定は名前）を開示する。対話回数は増やさない
  - すでに照合した会話で別の合言葉が出たら、たしなめて無視するよう指示する
- 引き継ぐのは対話回数と開示済みの秘密だけ。会話の中身は、本人にも他人にも渡さない
- 対話回数は、一度退出してから合言葉を伝えて再開した回数。ワンダには渡さない

秘密は次のとおり。

- secrets に、名前・中身（secret）・開示の条件（condition）・再開時の短い要約（recall）・開示した応答への指示（after）・開示できる対話回数の下限（min_visits）・レシートで渡すか（via_receipt）を書く。name は重複させてはならない
  - condition の {key} は key（カギ）に置き換わる
- 丁稚が、まだ開示していない秘密のうち、最後のお客さんの発言が条件を満たしたものを返す。開示済みの秘密は、ワンダのシステムプロンプトに「自分のことで話してよいこと」として入る
- via_receipt の秘密は、中身をワンダに渡さず、システムがレシートに印刷する
- 致命的な秘密は、after に会話を早く閉じる指示を書く
- 既定の秘密は、名前・見た目（気体の生き物）・味覚・住居（致命的）・秘密の合言葉（致命的、レシートで渡す）

印刷は次のとおり。

- ワンダには print_receipt（kind・fields・items）を見せる。システムが receipt_kinds の項目が揃っているかを確かめ、揃っていなければ印刷せずに足りない項目を返す
- 揃っていれば receipt シミュレータに渡す。末尾に、対話回数で選んだヒント（hints。足りなければ最後のもの）と、その会話で最初のレシートならカギ（key）を印字する
- ワンダへのツールの結果には、運勢と合計額だけを返し、末尾の印字は返さない
- その会話で渡したレシート（種類・運勢・合計）は、次のターン以降もワンダのシステムプロンプトに入る
- 既定の種類は、おみくじ模倣（願いごと・ひとこと。運勢を引く）と、レシート模倣（品物と金額。合計を計算する）
- 表示用の内訳には、ワンダの発言と、印刷（receipt シミュレータの呼び出し）を順に出す。丁稚のメモは Agent の状態の detchi に残す

(決定経緯 : 2026-10-31, docs/decisions/2026-10-31-紙だのみ.md)
(仕様: docs/specs/シミュレータ.md)
(図: docs/specs/紙だのみ_動作構造.svg)


# 会話をまたぐ記録

AgentCore が会話を越えて情報を引き継ぐための記録。Bot（同じ名前の Agent。バージョン違いを含む）ごとに、キーで引く。エラーのターンで中途半端な記録が残らないよう、書くのはターンが成功したときだけにする。

## 細則

- TurnContext.continuations.get(キー) で読む。同じ Bot の記録だけを引く
- 書くときは、TurnResult.continuations に「キー -> 中身」を入れる。ターンの応答を保存するときに、表 continuationrecord に書く。同じキーは中身を置き換える
- エラーのターンでは書かない
- フォークした（名前を変えた）Agent とは共有しない
- エージェント間対話でも、相手の Agent の Bot で読み書きする

(決定経緯 : 2026-10-31, docs/decisions/2026-10-31-紙だのみ.md)


# 会話用エージェントの AgentCore

会話用エージェント（利用者役として Agent と会話する Agent）の AgentCore は、Agent の AgentCore とは混ぜずに、registry.py の CONVERSATION_AGENTS に登録する。会話用エージェントは人間と同じく発言の文だけを出すと約束しているので、そのための型（ConversationCore）で作る。

## 細則

- 足すときは apps/backend/src/bt_backend/agents/conversation に ConversationCore を継承したクラスを作り、CONVERSATION_AGENTS に登録する
- speak が返すのは、発言の文（SpeakResult.text）と状態だけ。表示用の内訳・割込みは出せない
  - 発言が空ならエラーとして扱う
- 会話用エージェントから見た会話では、自分の発言が assistant、相手の Agent の発言が user になる
- テンプレートは SpeakContext.templates（名前 -> 本文）で渡る。`{{template:名前}}` を expand_templates で置き換える。置き換えは一度だけで、入れ子にしない
- シミュレータは SpeakContext.simulators で呼べる。現状、呼ぶ会話用エージェントは無い（2026-10-30）

(決定経緯 : 2026-10-30, docs/decisions/2026-10-30-会話用エージェント.md)


# 台本に沿って会話を続ける（conversation-script-*）

利用者役になり、システムプロンプトに埋め込んだ台本（テンプレート）に沿って、相手の Agent との会話をできるだけ続ける。Sonnet 5.5 と Opus 5.5 の二つを用意する。

## 細則

- モデル
  - conversation-script-sonnet : claude-sonnet-5-5
  - conversation-script-opus : claude-opus-5-5
- system_prompt に `{{template:名前}}` でテンプレートを埋め込む。既定は「台本サンプル」を埋め込む
- 会話の最初に opening_message を利用者の発言として置く（LLM API は利用者の発言から始まる必要があるため）
- 直近 context_chars 文字（既定 40000）までの会話を毎回送る。それより前の会話は送らず、要約もしない
- max_tokens の既定は 1024

(決定経緯 : 2026-10-30, docs/decisions/2026-10-30-会話用エージェント.md)


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

- Agent と AgentCore の関係、Agent 設定画面についての原本

## (仕様: docs/specs/プロジェクト辞書.md)

- Agent・AgentCore・Agent 設定・バージョン・フォークなどの呼称の意味
