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
    """プロンプトに埋め込む文章（台本など）。中身はバージョンとして持つ。"""

    id: int | None = Field(default=None, primary_key=True)
    # プロンプトでは {{template:名前}} で参照する
    name: str = Field(unique=True)
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
    # / webui（テスト実行）
    caller: str = Field(index=True)
    conversation_id: int | None = Field(default=None, foreign_key="conversation.id", index=True)
    # 呼び出したターンの発言（応答、またはエラー）
    message_id: int | None = Field(default=None, foreign_key="message.id")
    dialogue_id: int | None = Field(default=None, foreign_key="dialogue.id", index=True)
    dialogue_message_id: int | None = Field(default=None, foreign_key="dialoguemessage.id")
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
