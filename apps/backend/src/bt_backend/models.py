"""通常の DB（BOT 設定・会話）のテーブル。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Bot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    # 採用する Agent（コードで定義）。BOT ごとに固定する
    agent_id: str = Field(sa_column_kwargs={"server_default": ""})
    # モデルが存在しなくなった等で実行を止めている理由
    unavailable_reason: str | None = None
    # 名前を変えて保存（フォーク）した場合の元の BOT と、編集の元にしたバージョン。
    # 記録のためだけに持ち、元の BOT のバージョンや会話は引き継がない
    forked_from_bot_id: int | None = Field(default=None, foreign_key="bot.id")
    forked_from_version: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class BotVersion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("bot_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    version: int
    settings: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    # 開始時の BOT 設定のバージョンに固定する
    bot_version_id: int = Field(foreign_key="botversion.id")
    title: str = ""
    # active / stopped（エラーで停止）
    status: str = "active"
    # エラーで止まった会話を引き継いで作った場合の、元の会話
    resumed_from_id: int | None = Field(default=None, foreign_key="conversation.id")
    # 並行会話の候補を採用して作った場合の、その候補
    parallel_candidate_id: int | None = Field(default=None, foreign_key="parallelcandidate.id")
    # 開始時に固定した Agent テンプレート（名前 -> AgentTemplateVersion.id）と、
    # その本文を埋め込んだ Agent 設定。None なら Agent テンプレートの仕組みより前の記録で、
    # Agent のバージョンの設定をそのまま使う
    agent_template_version_ids: dict[str, int] | None = Field(default=None, sa_column=Column(JSON))
    resolved_settings: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # Agent の状態（メモリなど）。Agent が自分で保存する
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    seq: int
    # user / assistant / error
    role: str
    content: str
    # RAW 用の DB の RawCall.id（DB が別なので外部キーにはしない）
    raw_call_id: int | None = None
    # 表示用の内訳（例: メインとサブの発言）
    parts: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    # このターンの後の Agent の状態
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class MessageComment(SQLModel, table=True):
    """BOT の回答一つにつき一つの評価とコメント。"""

    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id", unique=True)
    # GOOD / FINE / BAD
    rating: str
    text: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ConversationComment(SQLModel, table=True):
    """会話全体へのコメント。都度いくつでも付けられる。"""

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    # GOOD / FINE / BAD。付けなくてもよい
    rating: str | None = None
    text: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ConversationInterrupt(SQLModel, table=True):
    """API から入った割込み要求。次のターンに Agent へ渡す。"""

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    message: str
    # 伝える相手（AgentCore が受け付ける相手の中から選ぶ）
    targets: list[str] = Field(sa_column=Column(JSON, nullable=False))
    # 伝えたターンの Agent の発言。まだ伝えていなければ None
    delivered_message_id: int | None = Field(default=None, foreign_key="message.id")
    created_at: datetime = Field(default_factory=utcnow)


class SettingsChatMessage(SQLModel, table=True):
    """BOT ごとの設定変更チャットの履歴。"""

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    # user / assistant / error
    role: str
    content: str
    # アシスタントが出した設定の変更案（変更しない場合は None）
    proposed_settings: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


# 会話用エージェント（ConversationAgent）。既存の Agent（Bot）とは別のテーブルに置き、
# 互いに行き来しない（会話用エージェントが Agent になることも、その逆も無い）


class ConversationBot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    # 採用する会話用エージェントの AgentCore（コードで定義）
    agent_id: str
    unavailable_reason: str | None = None
    forked_from_bot_id: int | None = Field(default=None, foreign_key="conversationbot.id")
    forked_from_version: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ConversationBotVersion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("bot_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="conversationbot.id", index=True)
    version: int
    settings: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ConversationBotSettingsChatMessage(SQLModel, table=True):
    """会話用エージェントごとの設定変更チャットの履歴。"""

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="conversationbot.id", index=True)
    role: str
    content: str
    proposed_settings: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Template(SQLModel, table=True):
    """対話用テンプレート。会話用エージェントのプロンプトに埋め込む文章（台本など）。

    中身はバージョンとして持つ。画面・資料では「対話用テンプレート」と呼ぶが、
    表・コード・API の名前は template のまま（技術的負債として残している）。
    """

    id: int | None = Field(default=None, primary_key=True)
    # プロンプトでは {{template:名前}} で参照する
    name: str = Field(unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class AgentTemplate(SQLModel, table=True):
    """Agent 設定に埋め込む文章。対話用テンプレート（Template）とは別に持ち、混ぜない。

    会話などを始めたときに最新のバージョンの本文を Agent 設定に埋め込み、固定する。
    """

    id: int | None = Field(default=None, primary_key=True)
    # Agent 設定では {{agent_template:名前}} で参照する
    name: str = Field(unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class AgentTemplateVersion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("template_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="agenttemplate.id", index=True)
    version: int
    # 保存時にサニタイズした本文
    content: str
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class TemplateVersion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("template_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="template.id", index=True)
    version: int
    # 保存時にサニタイズした本文
    content: str
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Dialogue(SQLModel, table=True):
    """会話用エージェントと Agent のエージェント間対話。"""

    id: int | None = Field(default=None, primary_key=True)
    conversation_bot_id: int = Field(foreign_key="conversationbot.id", index=True)
    # 開始時の会話用エージェントのバージョンに固定する
    conversation_bot_version_id: int = Field(foreign_key="conversationbotversion.id")
    bot_id: int = Field(foreign_key="bot.id", index=True)
    # 開始時の Agent のバージョンに固定する
    bot_version_id: int = Field(foreign_key="botversion.id")
    # 開始時に固定したテンプレート（名前 -> TemplateVersion.id）
    template_version_ids: dict[str, int] = Field(sa_column=Column(JSON, nullable=False))
    # active / stopped（エラーで停止）
    status: str = "active"
    resumed_from_id: int | None = Field(default=None, foreign_key="dialogue.id")
    # 開始時に固定した Agent テンプレート（名前 -> AgentTemplateVersion.id）と、
    # その本文を埋め込んだ Agent の設定。None なら Agent テンプレートの仕組みより前の記録で、
    # Agent のバージョンの設定をそのまま使う
    agent_template_version_ids: dict[str, int] | None = Field(default=None, sa_column=Column(JSON))
    agent_resolved_settings: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # 会話用エージェントの状態と、Agent の状態。それぞれが自分で保存する
    conversation_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class DialogueMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    dialogue_id: int = Field(foreign_key="dialogue.id", index=True)
    seq: int
    # conversation（会話用エージェント）/ agent（Agent）
    speaker: str
    # speech（発言）/ error
    role: str
    content: str
    raw_call_id: int | None = None
    # 表示用の内訳（Agent の発言のみ。会話用エージェントは持たない）
    parts: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    # このターンの後の、発言者の状態
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class DialogueMessageComment(SQLModel, table=True):
    """エージェント間対話の発言一つにつき一つの評価とコメント。どちらの発言にも付けられる。"""

    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="dialoguemessage.id", unique=True)
    rating: str
    text: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DialogueComment(SQLModel, table=True):
    """エージェント間対話の全体へのコメント。"""

    id: int | None = Field(default=None, primary_key=True)
    dialogue_id: int = Field(foreign_key="dialogue.id", index=True)
    rating: str | None = None
    text: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class SimulationRun(SQLModel, table=True):
    """シミュレータを 1 回実行した記録。実際に使った値（グローバル設定の値を含む）と結果を残す。

    シミュレータのソースは残さない。
    各回の LLM 呼び出しは、RAW 用の DB の simulationrawcall に置く。
    """

    id: int | None = Field(default=None, primary_key=True)
    simulator: str = Field(index=True)
    # 呼び出し元: conversation（チャットの会話）/ dialogue（エージェント間対話）
    # / webui（テスト実行）/ parallel（並行会話の候補）
    caller: str = Field(index=True)
    conversation_id: int | None = Field(default=None, foreign_key="conversation.id", index=True)
    # 呼び出したターンの発言（応答、またはエラー）
    message_id: int | None = Field(default=None, foreign_key="message.id")
    dialogue_id: int | None = Field(default=None, foreign_key="dialogue.id", index=True)
    dialogue_message_id: int | None = Field(default=None, foreign_key="dialoguemessage.id")
    # 並行会話の候補を作る中で呼んだ場合の、その候補
    parallel_candidate_id: int | None = Field(
        default=None, foreign_key="parallelcandidate.id", index=True
    )
    # 呼び出した AgentCore（テスト実行では空）
    agent_id: str = ""
    # 呼ぶ側が渡した引数
    args: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # 実行に使った値のすべて。引数が合わず実行しなかった場合は None
    params: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # succeeded / failed / invalid（引数が足りない・合わないため実行しなかった）
    status: str
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # 結果のほかの内訳（各回の出目、各回の出力など）
    detail: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # LLM 呼び出しのエラーの回数
    error_count: int = 0
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class SimulationSettingsRow(SQLModel, table=True):
    """シミュレータのグローバル設定。1 行だけ持つ。バージョン管理はしない。"""

    id: int | None = Field(default=None, primary_key=True)
    values: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    updated_at: datetime = Field(default_factory=utcnow)


class ContinuationRecord(SQLModel, table=True):
    """会話をまたいで Agent が引き継ぐ記録（つづきの合言葉など）。

    Bot（同じ名前の Agent。バージョン違いを含む）ごとに、キーで引く。中身は AgentCore が決める。
    """

    __table_args__ = (UniqueConstraint("bot_id", "key"),)

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    key: str
    # 記録を書いた会話（チャット）またはエージェント間対話
    conversation_id: int | None = Field(default=None, foreign_key="conversation.id")
    dialogue_id: int | None = Field(default=None, foreign_key="dialogue.id")
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ParallelConversation(SQLModel, table=True):
    """並行会話。分かれる位置までの会話を写して持ち、同じ入力への応答（候補）を何度も作る。

    元の会話をたどらずに済むよう、分かれる位置までの発言は ParallelMessage にすべて写す。
    """

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    # 元の会話・対話が固定していた Agent のバージョン
    bot_version_id: int = Field(foreign_key="botversion.id")
    # 写した元: conversation（チャットの会話）/ dialogue（エージェント間対話）
    # / new（会話の最初から）。記録のためだけに持つ
    source_kind: str
    # 外部キーにはしない（会話 → 候補 → 並行会話 → 会話 の循環を避けるため）
    source_conversation_id: int | None = None
    source_dialogue_id: int | None = Field(default=None, foreign_key="dialogue.id")
    # 開始時に固定した Agent テンプレート（名前 -> AgentTemplateVersion.id）と、
    # その本文を埋め込んだ Agent 設定。None なら Agent テンプレートの仕組みより前の記録で、
    # Agent のバージョンの設定をそのまま使う
    agent_template_version_ids: dict[str, int] | None = Field(default=None, sa_column=Column(JSON))
    resolved_settings: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # 分かれる位置での Agent の状態
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class ParallelMessage(SQLModel, table=True):
    """並行会話に写した、分かれる位置までの発言。

    エージェント間対話から写したときは、会話用エージェントの発言を user にする。
    """

    id: int | None = Field(default=None, primary_key=True)
    parallel_conversation_id: int = Field(foreign_key="parallelconversation.id", index=True)
    seq: int
    # user / assistant
    role: str
    content: str
    raw_call_id: int | None = None
    parts: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # 元の発言の日時
    created_at: datetime = Field(default_factory=utcnow)


class ParallelRound(SQLModel, table=True):
    """並行会話の 1 回分。一つの利用者の入力に対して、count 個の候補を作る。"""

    id: int | None = Field(default=None, primary_key=True)
    parallel_conversation_id: int = Field(foreign_key="parallelconversation.id", index=True)
    content: str
    count: int
    created_at: datetime = Field(default_factory=utcnow)


class ParallelCandidate(SQLModel, table=True):
    """並行会話の候補一つ。Agent の 1 ターン分の結果を、採用するまで会話とは別に持つ。"""

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="parallelround.id", index=True)
    # 回の中での番号（0 から）
    index: int
    # pending / running / succeeded / failed
    status: str = "pending"
    text: str | None = None
    parts: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    agent_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # 採用したときに、会話をまたぐ記録に書くもの
    continuations: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = None
    raw_call_id: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class ParallelSettingsRow(SQLModel, table=True):
    """並行会話の設定。1 行だけ持つ。バージョン管理はしない。"""

    id: int | None = Field(default=None, primary_key=True)
    values: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    updated_at: datetime = Field(default_factory=utcnow)
