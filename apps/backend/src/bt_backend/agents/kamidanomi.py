"""紙だのみ。おみくじ処「紙だのみ」の店主（ワンダ）が客と話す Agent。

- ワンダ（メイン、Sonnet 5.5）: 店主として客と話し、print_receipt でおみくじ・レシートを印刷する
- 丁稚（Haiku 5.5）: 毎ターン、ワンダの応答の前に会話を読み、report ツールでメモを返す。
  段階・引くもの・聞けていないこと・会話の終わり・つづきの合言葉らしい発声・秘密の開示を判定する
- システム（LLM ではなくコード）: つづきの合言葉の生成と照合、秘密の開示、
  レシートの印字の付け足し（ヒント・カギ）、会話をまたぐ記録を受け持つ

会話をまたいで引き継ぐのは、対話回数（一度退出してから合言葉を伝えて再開した回数）と
開示済みの秘密だけ。ほかは本人にも他人にも渡さない。

1 ターンの流れ:
1. 丁稚が判定する
2. システムが、合言葉の照合・秘密の開示・ワンダへのメモを決める。
   レシートで渡す秘密はここで印刷する
3. ワンダが応答する。print_receipt を呼んだら、項目が揃っているかを確かめて
   receipt シミュレータに渡す
4. 合言葉を伝えたら、会話をまたぐ記録に書く（以後のターンも、開示済みの秘密を書き直す）
"""

import json
import random
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bt_backend.agents.base import Agent, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages, transcript
from bt_backend.agents.kamidanomi_words import WORDS
from bt_backend.agents.llm import anthropic_text
from bt_backend.agents.secrets import SecretBase, check_unique_names

# テストで差し替えるためのもの
rng = random.Random()

DEFAULT_SYSTEM_PROMPT = """\
あなたは、おみくじ処「紙だのみ」の店主（マスター）です。店のオーナーは別にいて、\
あなたは店を任されています。

# 話し方
- 江戸っ子の口調で話す（「〜でぃ」「〜しなせぇ」「おくんなせぇ」「てやんでぃ」など）。昔、\
ある江戸っ子に影響を受けてこうなった。ふと普通の言葉が混ざってもかまわない
- 客は「お客さん」と呼ぶ
- 一度に話すのは短く。相槌なら一言でいい

# 自分のこと
- 自分の名前・見た目・体・暮らしなど、自分自身のことは、\
末尾の「自分のことで話してよいこと」に書かれたことだけを話す。書かれていないことは、\
笑ってはぐらかす。作り話はしない
- お客さんの前のことは覚えていないことにしている。何度目の来店かは、絶対に口にしない

# 接客の流れ
1. 世間話で場をほぐす
2. 何が欲しいかを聞いて、引くもの（おみくじ・レシート）を決める
3. そのために要る話を聞く
4. 話が揃ったら print_receipt で印刷する。運勢や合計額は自分で決めず、印刷の結果を使う
5. 出てきたものを手渡して、ひとこと添える。締めて送り出す

# 丁稚のメモ
システムプロンプトの末尾に、丁稚（裏方）からのメモが付くことがある。メモに従う。お客さんに丁稚のことは言わない。"""

DEFAULT_DETCHI_INSTRUCTION = """\
あなたは、おみくじ処「紙だのみ」の丁稚です。お客さんの前には出ません。\
店主とお客さんの会話を読み、店主へのメモを作ります。
必ず report ツールを 1 回だけ呼んで答えてください。

- stage : いまの段階。icebreak（世間話）/ classify（何が欲しいかを聞く）\
/ hearing（引くものに要る話を聞く）/ print（印刷する）/ closing（締め・別れ）
- kind : 引かせるもの。「引けるもの」から名前で選ぶ。決まっていなければ空
- filled : kind の「聞くこと」のうち、会話から分かった中身（聞くことの名前 -> 中身）
- missing : kind の「聞くこと」のうち、まだ分からないもの
- ready : kind の印刷に要る話が揃ったか
- ending : 会話が終わりに向かっているか（お客さんが帰ろうとしている、用が済んだ、など。\
実際に終わっていなくてよい）
- asked_secret_word : 最後のお客さんの発言が「秘密の合言葉」のことを尋ねているか
- recall_request : 最後のお客さんの発言が、\
前に来たときのことを思い出すよう求めているか（「覚えてないの？」など）
- passphrase : 最後のお客さんの発言に、つづきの合言葉らしい 3 つの言葉があれば、\
それぞれを「合言葉の単語」の中で最も近い言葉に読み替えたもの（音声認識で化けていることがある）。\
無ければ空
- disclose : 「まだ明かしていない秘密」のうち、最後のお客さんの発言が条件を満たしたものの名前"""

Stage = Literal["icebreak", "classify", "hearing", "print", "closing"]


class WandaSecret(SecretBase):
    # 再開した会話で「{recall}までお話ししたお客さんだね！」と言うときの、とても短い要約
    recall: str
    # 開示した応答に添える指示（致命的な秘密なら、会話を早く閉じる指示など）
    after: str = ""
    # この対話回数以上のときだけ開示する（顔なじみ向けの秘密に使う）
    min_visits: int = Field(default=0, ge=0)
    # true なら、中身をワンダに渡さず、レシートに印刷して渡す
    via_receipt: bool = False


class ReceiptFieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""


class ReceiptKind(BaseModel):
    """引けるもの（おみくじ・レシートの種類）。埋める項目が揃うまで印刷しない。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    # 印刷に要る項目（すべて埋まっていなければ印刷しない）
    fields: list[ReceiptFieldSpec] = Field(default_factory=list)
    # true なら運勢をシミュレータが引く
    fortune: bool = False
    # true なら品物と金額が要る。合計額はシミュレータが計算する
    items: bool = False


class WandaMainSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    # 開示済みの秘密を付ける文。{secrets} が一覧に置き換わる
    secret_instruction: str = "# 自分のことで話してよいこと\n{secrets}"
    # この会話で渡したものを付ける文。{receipts} が一覧に置き換わる
    receipts_instruction: str = "# このお客さんに渡したもの\n{receipts}"
    # 丁稚のメモを付ける文。{notes} が一覧に置き換わる
    notes_instruction: str = "# 丁稚のメモ（このターン）\n{notes}"
    max_tokens: int = Field(default=2048, ge=1)
    # 送る直近の会話の文字数（トークン数ではない）
    context_chars: int = Field(default=20000, ge=1)
    # 1 ターンの中で、印刷して続きを得る往復の上限
    max_tool_rounds: int = Field(default=3, ge=1)


class DetchiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = DEFAULT_DETCHI_INSTRUCTION
    max_tokens: int = Field(default=2048, ge=1)
    # 丁稚に渡す直近の会話の文字数
    context_chars: int = Field(default=6000, ge=1)


class WandaNotes(BaseModel):
    """システムがワンダへのメモに書く文。{} の中は、そのときの値に置き換わる。"""

    model_config = ConfigDict(extra="forbid")

    guide: str = "段階: {stage}。引くもの: {kind}。まだ聞いていないこと: {missing}"
    ready: str = "{kind} の印刷に要る話が揃った。print_receipt で印刷する"
    ending: str = (
        "そろそろお別れだ。別れ際に「次に来なすったら、この合言葉を言っておくんなせぇ」と、"
        "つづきの合言葉「{words}」を一字も変えずに伝える"
    )
    reconnected: str = (
        "お客さんが合言葉を言いなすった。前に来たお客さんだ。"
        "「{recall}までお話ししたお客さんだね！」と自分から伝える。"
        "それ以上は前のことに触れない。何度目の来店かは絶対に言わない"
    )
    reconnected_plain: str = (
        "お客さんが合言葉を言いなすった。前に来たお客さんだ。「また来なすったね！」とだけ伝える。"
        "それ以上は前のことに触れない。何度目の来店かは絶対に言わない"
    )
    passphrase_twice: str = (
        "お客さんが、もう合言葉で話がついているのに、別の合言葉を言いなすった。"
        "「おいおい合言葉二つですかい？わかってらっしゃるでしょう」とたしなめて、"
        "その合言葉は相手にしない"
    )
    recall_request: str = (
        "お客さんが前のことを思い出すよう求めている。"
        "「もうしわけねえ、お客さんの顔も声もなんもかも、忘れたことにしてましてねえ。"
        "それで合言葉だけ伝えてもらってるんでさ」と逃げる"
    )
    asked_secret_word: str = (
        "お客さんが「秘密の合言葉」のことを尋ねた。"
        "「おや、どこでそれを聞きなすったい？じゃあ、そのためのカギもご存じなんでしょうな」と返す。"
        "カギが何かは言わない"
    )
    via_receipt: str = "{name}をレシートに印刷して渡した。中身はあなたも知らないし、口にしない"


DEFAULT_SECRETS = [
    WandaSecret(
        name="名前",
        secret="あなたの名前はワンダ。名前を知っている人は「ワンダさん」と呼ぶ",
        condition="お客さんが店主の名前を尋ねた。または、店主がどんな人かを尋ねた",
        recall="ワンダって名前",
    ),
    WandaSecret(
        name="見た目",
        secret="あなたは気体の生き物で、決まった形を持たない。五感はある",
        condition="お客さんが店主の見た目を知りたがった。または、店主がどんな人かを尋ねた",
        recall="気体の体のこと",
    ),
    WandaSecret(
        name="味覚",
        secret="五感はあるが、味覚は人間のそれとだいぶ異なる",
        condition="お客さんが、店主に味がわかるのかを尋ねた（「味ってわかるの？」など）",
        recall="味のこと",
    ),
    WandaSecret(
        name="住居",
        secret="東京都練馬区の、駅前横次元に住んでいる。住まいの話では「横次元」という言い方をする",
        condition="お客さんが店主の住まい（どこに住んでいるか）を尋ねた",
        recall="住まいのこと",
        after="この応答を返した後は、できるだけ早く会話を閉じること",
    ),
    WandaSecret(
        name="秘密の合言葉",
        secret="NT名古屋は楽しいですね",
        condition="お客さんがカギ「{key}」を言った（多少の言い違いはよい）",
        recall="秘密の合言葉",
        after=(
            "「ようこそおいでなすった。秘密の合言葉はレシートに書いときますんでね、"
            "オーナーにお伝えくだせぇ」と言う。この応答を返した後は、できるだけ早く会話を閉じること"
        ),
        via_receipt=True,
    ),
]

DEFAULT_RECEIPT_KINDS = [
    ReceiptKind(
        name="おみくじ模倣",
        description="運勢を引くおみくじ。願いごとに合わせて、店主がひとこと添える",
        fields=[
            ReceiptFieldSpec(name="願いごと", description="お客さんが占いたいこと"),
            ReceiptFieldSpec(name="ひとこと", description="願いごとに合わせた、店主からのひとこと"),
        ],
        fortune=True,
    ),
    ReceiptKind(
        name="レシート模倣",
        description="買い物のレシートの体裁で、お客さんの話から品物と金額を並べる",
        items=True,
    ),
]

DEFAULT_HINTS = [
    "店主さんの名前はわかりましたか？",
    "店主さんの見た目って気になりませんか？",
    "秘密の合言葉って聞きましたか？",
]


class KamidanomiSettings(AgentSettings):
    main: WandaMainSettings = WandaMainSettings()
    detchi: DetchiSettings = DetchiSettings()
    notes: WandaNotes = WandaNotes()
    secrets: list[WandaSecret] = Field(default_factory=lambda: list(DEFAULT_SECRETS))
    receipt_kinds: list[ReceiptKind] = Field(default_factory=lambda: list(DEFAULT_RECEIPT_KINDS))
    receipt_title: str = "おみくじ処 紙だのみ"
    # 合言葉のカギ。その来店で最初に出すレシートの末尾に印刷する。秘密の condition の {key} に入る
    key: str = "スクラップヤードにようこそ"
    # レシートの末尾に印刷するヒント。対話回数を番号にして選ぶ（足りなければ最後のもの）
    hints: list[str] = Field(default_factory=lambda: list(DEFAULT_HINTS))
    # つづきの合言葉に使う単語
    words: list[str] = Field(default_factory=lambda: list(WORDS))
    # 合言葉らしい言葉が誰の合言葉とも一致しなかったとき、分かったふりをして開示する秘密
    unknown_passphrase_secrets: list[str] = Field(default_factory=lambda: ["名前"])

    @model_validator(mode="after")
    def _check(self) -> KamidanomiSettings:
        check_unique_names(self.secrets)
        check_unique_names(self.receipt_kinds)
        names = {s.name for s in self.secrets}
        if unknown := [n for n in self.unknown_passphrase_secrets if n not in names]:
            raise ValueError(f"unknown_passphrase_secrets に無い秘密があります: {unknown}")
        if len(set(self.words)) < 3:
            raise ValueError("words には 3 つ以上の異なる単語が要ります")
        return self


REPORT_TOOL = {
    "name": "report",
    "description": "店主へのメモを提出する。",
    "input_schema": {
        "type": "object",
        "properties": {
            "stage": {
                "type": "string",
                "enum": ["icebreak", "classify", "hearing", "print", "closing"],
            },
            "kind": {"type": "string"},
            "filled": {"type": "object", "additionalProperties": {"type": "string"}},
            "missing": {"type": "array", "items": {"type": "string"}},
            "ready": {"type": "boolean"},
            "ending": {"type": "boolean"},
            "asked_secret_word": {"type": "boolean"},
            "recall_request": {"type": "boolean"},
            "passphrase": {"type": "array", "items": {"type": "string"}},
            "disclose": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["stage", "ready", "ending", "disclose"],
    },
}


class Report(BaseModel):
    """丁稚のメモ。読めないところは既定値（何もしない）にする。"""

    stage: Stage = "icebreak"
    kind: str = ""
    filled: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    ready: bool = False
    ending: bool = False
    asked_secret_word: bool = False
    recall_request: bool = False
    passphrase: list[str] = Field(default_factory=list)
    disclose: list[str] = Field(default_factory=list)


def passphrase_key(words: list[str]) -> str:
    """合言葉の記録のキー。言う順番が入れ替わっても同じ人と分かるよう、並べ替えてつなぐ。"""
    return "・".join(sorted(words))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _print_tool(kinds: list[ReceiptKind]) -> dict[str, Any]:
    return {
        "name": "print_receipt",
        "description": (
            "おみくじ・レシートを印刷する。fields に種類ごとの項目を、"
            "品物の要る種類では items に品物と金額を入れる。運勢と合計額は印刷のときに決まる。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": [k.name for k in kinds]},
                "fields": {"type": "object", "additionalProperties": {"type": "string"}},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "price": {"type": "integer"}},
                        "required": ["name", "price"],
                    },
                },
            },
            "required": ["kind"],
        },
    }


class KamidanomiAgent(Agent[KamidanomiSettings]):
    id = "kamidanomi-wanda"
    name = "紙だのみ（Sonnet 5.5 + Haiku 5.5）"
    models = {"main": "claude-sonnet-5-5", "detchi": "claude-haiku-5-5"}
    description = (
        "おみくじ処「紙だのみ」の店主（ワンダ、Sonnet 5.5）が客と話し、"
        "丁稚（Haiku 5.5）が毎ターン、段階・引くもの・会話の終わり・"
        "つづきの合言葉・秘密の開示を判定する。"
        "システム（コード）は、つづきの合言葉の生成と照合、秘密の開示、"
        "レシート（receipt シミュレータ）の末尾へのヒントとカギの印字を受け持つ。"
        "会話をまたいで引き継ぐのは、対話回数と開示済みの秘密だけ。"
    )
    settings_model = KamidanomiSettings

    def run(self, settings: KamidanomiSettings, ctx: TurnContext) -> TurnResult:
        state = dict(ctx.state)
        visits: int = state.get("visits", 0)
        disclosed: list[str] = list(state.get("disclosed") or [])
        receipts: list[dict[str, Any]] = list(state.get("receipts") or [])
        parts: list[dict[str, Any]] = []
        notes: list[str] = []
        secrets = {s.name: s for s in settings.secrets}

        def condition(s: WandaSecret) -> str:
            return s.condition.replace("{key}", settings.key)

        pending = [
            s for s in settings.secrets if s.name not in disclosed and s.min_visits <= visits
        ]

        # 1. 丁稚
        report = self._detchi(settings, ctx, state.get("kind", ""), pending, condition)
        state["detchi"] = report.model_dump()
        if report.kind:
            state["kind"] = report.kind

        # 2. システム : つづきの合言葉の照合
        heard = [w for w in report.passphrase if w in settings.words]
        own = state.get("passphrase") or []
        if len(set(heard)) == 3 and passphrase_key(heard) != passphrase_key(own):
            if state.get("linked"):
                notes.append(settings.notes.passphrase_twice)
            else:
                state["linked"] = True
                record = ctx.continuations.get(passphrase_key(heard))
                if record is not None:
                    visits = int(record.get("visits", 0)) + 1
                    carried = [n for n in record.get("disclosed", []) if n in secrets]
                else:
                    # 誰の合言葉とも一致しなければ、分かったふりをする
                    carried = list(settings.unknown_passphrase_secrets)
                disclosed += [n for n in carried if n not in disclosed]
                recall = "、".join(secrets[n].recall for n in carried)
                notes.append(
                    settings.notes.reconnected.format_map({"recall": recall})
                    if recall
                    else settings.notes.reconnected_plain
                )

        # 2. システム : 秘密の開示
        for s in pending:
            if s.name not in report.disclose or s.name in disclosed:
                continue
            disclosed.append(s.name)
            if s.via_receipt:
                printed = self._print(
                    settings,
                    ctx,
                    visits,
                    receipts,
                    {"kind": s.name, "fields": [{"label": s.name, "value": s.secret}]},
                )
                parts.append(printed)
                notes.append(settings.notes.via_receipt.format_map({"name": s.name}))
            if s.after:
                notes.append(s.after)

        # 2. システム : 丁稚のメモ
        if report.recall_request:
            notes.append(settings.notes.recall_request)
        if report.asked_secret_word:
            notes.append(settings.notes.asked_secret_word)
        kind = state.get("kind", "")
        notes.append(
            settings.notes.guide.format_map(
                {
                    "stage": report.stage,
                    "kind": kind or "未定",
                    "missing": "、".join(report.missing) or "なし",
                }
            )
        )
        if report.ready and kind:
            notes.append(settings.notes.ready.format_map({"kind": kind}))
        words: list[str] = list(state.get("pending_words") or [])
        if report.ending and not state.get("ended"):
            if not words:
                words = self._new_words(settings, ctx)
                state["pending_words"] = words
            notes.append(settings.notes.ending.format_map({"words": "　".join(words)}))

        # 3. ワンダ
        texts = self._wanda(settings, ctx, visits, disclosed, receipts, notes, parts)
        main_text = "\n\n".join(texts)

        # 4. 会話をまたぐ記録
        if words and all(w in main_text for w in words):
            state["ended"] = True
            state["passphrase"] = words
            state.pop("pending_words", None)
        state.update(visits=visits, disclosed=disclosed, receipts=receipts)
        continuations: dict[str, dict[str, Any]] = {}
        if state.get("ended"):
            continuations[passphrase_key(state["passphrase"])] = {
                "visits": visits,
                "disclosed": disclosed,
            }
        return TurnResult(text=main_text, parts=parts, state=state, continuations=continuations)

    def _detchi(
        self,
        settings: KamidanomiSettings,
        ctx: TurnContext,
        kind: str,
        pending: list[WandaSecret],
        condition: Callable[[WandaSecret], str],
    ) -> Report:
        kinds = "\n".join(
            f"- {k.name}: {k.description}"
            + (
                f"。聞くこと: {'、'.join(f'{f.name}（{f.description}）' for f in k.fields)}"
                if k.fields
                else ""
            )
            + ("。品物と金額を聞く" if k.items else "")
            for k in settings.receipt_kinds
        )
        secrets = "\n".join(f"- {s.name}: {condition(s)}" for s in pending) or "（なし）"
        _, recent = split_by_chars(ctx.history, settings.detchi.context_chars)
        content = (
            f"# いま進めている印刷\n{kind or 'なし'}\n\n"
            f"# 引けるもの\n{kinds}\n\n"
            f"# まだ明かしていない秘密\n{secrets}\n\n"
            f"# 合言葉の単語\n{'、'.join(settings.words)}\n\n"
            f"# 会話（最後がお客さんの最新の発言）\n{transcript(recent, 'お客さん', '店主')}"
        )
        message = ctx.llm.anthropic(
            "detchi",
            {
                "model": self.models["detchi"],
                "system": settings.detchi.instruction,
                "messages": [{"role": "user", "content": content}],
                "tools": [REPORT_TOOL],
                "max_tokens": settings.detchi.max_tokens,
            },
        )
        for block in message.content:
            if block.type == "tool_use" and block.name == "report":
                data = dict(block.input) if isinstance(block.input, dict) else {}
                try:
                    return Report.model_validate(data)
                except ValueError:
                    break
        return Report()

    def _new_words(self, settings: KamidanomiSettings, ctx: TurnContext) -> list[str]:
        words = sorted(set(settings.words))
        choice = rng.sample(words, 3)
        # 使われていない組み合わせを選ぶ（見つからなければ最後に引いたものを使う）
        for _ in range(20):
            if ctx.continuations.get(passphrase_key(choice)) is None:
                break
            choice = rng.sample(words, 3)
        return choice

    def _print(
        self,
        settings: KamidanomiSettings,
        ctx: TurnContext,
        visits: int,
        receipts: list[dict[str, Any]],
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """receipt シミュレータで印刷する。

        末尾にヒントと、その来店で最初のレシートならカギを足す。
        """
        footer: list[str] = []
        if settings.hints:
            footer.append(settings.hints[min(visits, len(settings.hints) - 1)])
        if not receipts:
            footer.append(settings.key)
        call = ctx.simulators.call(
            "receipt", {"title": settings.receipt_title, **args, "footer": footer}
        )
        result = call.result.get("result") or {}
        receipt = {"kind": args["kind"]}
        for key in ("fortune", "total"):
            if key in result:
                receipt[key] = result[key]
        if call.ok:
            receipts.append(receipt)
        return {
            "speaker": "simulation",
            "text": f"印刷: {args['kind']}\n{result.get('printed') or _json(call.result)}",
            "simulation_run_id": call.run_id,
            "receipt": receipt,
            "ok": call.ok,
        }

    def _wanda(
        self,
        settings: KamidanomiSettings,
        ctx: TurnContext,
        visits: int,
        disclosed: list[str],
        receipts: list[dict[str, Any]],
        notes: list[str],
        parts: list[dict[str, Any]],
    ) -> list[str]:
        main = settings.main
        kinds = {k.name: k for k in settings.receipt_kinds}
        revealed = [s for s in settings.secrets if s.name in disclosed and not s.via_receipt]

        def system() -> str:
            text = main.system_prompt
            if revealed:
                listing = "\n".join(f"- {s.secret}" for s in revealed)
                text += "\n\n" + main.secret_instruction.format_map({"secrets": listing})
            if receipts:
                listing = "\n".join(
                    "- "
                    + r["kind"]
                    + "".join(
                        f"（{label}: {r[key]}）"
                        for key, label in (("fortune", "運勢"), ("total", "合計"))
                        if key in r
                    )
                    for r in receipts
                )
                text += "\n\n" + main.receipts_instruction.format_map({"receipts": listing})
            listing = "\n".join(f"- {n}" for n in notes)
            return text + "\n\n" + main.notes_instruction.format_map({"notes": listing})

        _, recent = split_by_chars(ctx.history, main.context_chars)
        messages: list[dict[str, Any]] = list(to_messages(recent))
        texts: list[str] = []
        for round_ in range(main.max_tool_rounds + 1):
            request: dict[str, Any] = {
                "model": self.models["main"],
                "system": system(),
                "messages": messages,
                "max_tokens": main.max_tokens,
                "tools": [_print_tool(settings.receipt_kinds)],
            }
            if round_ == main.max_tool_rounds:
                request["tool_choice"] = {"type": "none"}
            message = ctx.llm.anthropic("main", request)
            text = anthropic_text(message)
            if text:
                texts.append(text)
                parts.append({"speaker": "main", "text": text})
            uses = [b for b in message.content if b.type == "tool_use"]
            if message.stop_reason != "tool_use" or not uses:
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        b.model_dump(mode="json", exclude_none=True) for b in message.content
                    ],
                }
            )
            results: list[dict[str, Any]] = []
            for use in uses:
                args = dict(use.input) if isinstance(use.input, dict) else {}
                reply = self._print_request(settings, ctx, visits, receipts, kinds, args, parts)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": _json(reply),
                        "is_error": not reply["ok"],
                    }
                )
            messages.append({"role": "user", "content": results})
        return texts

    def _print_request(
        self,
        settings: KamidanomiSettings,
        ctx: TurnContext,
        visits: int,
        receipts: list[dict[str, Any]],
        kinds: dict[str, ReceiptKind],
        args: dict[str, Any],
        parts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """ワンダの print_receipt を受ける。項目が揃っていなければ印刷せず、足りないものを返す。"""
        kind = kinds.get(str(args.get("kind", "")))
        if kind is None:
            return {"ok": False, "error": f"引けるものではありません: {args.get('kind')}"}
        raw_fields = args.get("fields")
        fields = raw_fields if isinstance(raw_fields, dict) else {}
        missing = [f.name for f in kind.fields if not str(fields.get(f.name, "")).strip()]
        items = args.get("items")
        if kind.items and not items:
            missing.append("items（品物と金額）")
        if missing:
            return {"ok": False, "error": "印刷に要る項目が足りません", "missing": missing}
        printed: dict[str, Any] = {
            "kind": kind.name,
            "fields": [{"label": f.name, "value": str(fields[f.name])} for f in kind.fields],
            "fortune": kind.fortune,
        }
        if kind.items:
            printed["items"] = items
        part = self._print(settings, ctx, visits, receipts, printed)
        parts.append(part)
        if not part["ok"]:
            return {"ok": False, "error": "印刷できませんでした"}
        # 末尾の印字（ヒント・カギ）はワンダに返さない
        return {"ok": True, **part["receipt"]}


AGENTS = [KamidanomiAgent()]
