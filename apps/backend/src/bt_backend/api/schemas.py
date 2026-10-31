from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentOut(BaseModel):
    id: str
    name: str
    description: str
    models: dict[str, str]
    default_settings: dict[str, Any]
    interrupt_targets: list[str]


class BotCreate(BaseModel):
    name: str = Field(min_length=1)
    agent_id: str
    settings: dict[str, Any]
    note: str = ""


class BotFork(BaseModel):
    name: str = Field(min_length=1)
    settings: dict[str, Any]
    note: str = ""
    # 編集の元にしたバージョン（既定の設定から作った場合などは None）
    base_version: int | None = None


class VersionCreate(BaseModel):
    settings: dict[str, Any]
    note: str = ""


class VersionOut(BaseModel):
    id: int
    version: int
    settings: dict[str, Any]
    note: str
    created_at: datetime


class BotOut(BaseModel):
    id: int
    name: str
    agent_id: str
    agent_name: str
    unavailable_reason: str | None
    forked_from_bot_id: int | None
    forked_from_bot_name: str | None = None
    forked_from_version: int | None
    created_at: datetime
    latest_version: int | None


class BotDetail(BotOut):
    versions: list[VersionOut]


class ConversationCreate(BaseModel):
    bot_id: int


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


Rating = Literal["GOOD", "FINE", "BAD"]


class MessageCommentIn(BaseModel):
    rating: Rating
    text: str = ""


class MessageCommentOut(BaseModel):
    rating: Rating
    text: str
    updated_at: datetime


class ConversationCommentIn(BaseModel):
    rating: Rating | None = None
    text: str = ""


class ConversationCommentOut(BaseModel):
    id: int
    rating: Rating | None
    text: str
    created_at: datetime


class ConversationSettingsOut(BaseModel):
    bot_id: int
    bot_name: str
    agent_id: str
    agent_name: str
    version: int
    note: str
    created_at: datetime
    settings: dict[str, Any]


class SettingsChatIn(BaseModel):
    message: str = Field(min_length=1)
    # 画面上の編集中の設定（JSON のテキスト。書きかけでもよい）
    current_settings: str


class SettingsChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    proposed_settings: dict[str, Any] | None
    created_at: datetime


class SettingsChatOut(BaseModel):
    messages: list[SettingsChatMessageOut]
    # 今回の変更案（変更しない、またはエラーの場合は None）
    proposed_settings: dict[str, Any] | None


class MessageOut(BaseModel):
    id: int
    seq: int
    role: str
    content: str
    raw_call_id: int | None
    parts: list[dict[str, Any]] | None
    agent_state: dict[str, Any] | None
    created_at: datetime
    comment: MessageCommentOut | None = None


class ConversationOut(BaseModel):
    id: int
    bot_id: int
    bot_name: str
    bot_version: int
    title: str
    status: str
    agent_state: dict[str, Any] | None
    resumed_from_id: int | None
    # 並行会話の候補を採用して作った会話なら、その候補と並行会話
    parallel_candidate_id: int | None = None
    parallel_conversation_id: int | None = None
    created_at: datetime
    message_count: int
    # 最初の利用者の発言（一覧での見分け用）
    preview: str
    last_message_at: datetime | None


class InterruptCreate(BaseModel):
    message: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)


class InterruptOut(BaseModel):
    id: int
    conversation_id: int
    message: str
    targets: list[str]
    delivered_message_id: int | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
    comments: list[ConversationCommentOut]


class RawCallOut(BaseModel):
    id: int
    conversation_id: int | None
    dialogue_id: int | None
    parallel_candidate_id: int | None = None
    agent_id: str
    source_hash: str
    exchanges: list[dict[str, Any]]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[^{}\n]+$")
    content: str
    note: str = ""


class TemplateVersionCreate(BaseModel):
    content: str
    note: str = ""


class TemplateVersionOut(BaseModel):
    id: int
    version: int
    content: str
    note: str
    created_at: datetime


class TemplateOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    latest_version: int


class TemplateDetail(TemplateOut):
    versions: list[TemplateVersionOut]


class DialogueCreate(BaseModel):
    conversation_bot_id: int
    bot_id: int


class DialogueMessageOut(BaseModel):
    id: int
    seq: int
    speaker: Literal["conversation", "agent"]
    role: Literal["speech", "error"]
    content: str
    raw_call_id: int | None
    parts: list[dict[str, Any]] | None
    agent_state: dict[str, Any] | None
    created_at: datetime
    comment: MessageCommentOut | None = None


class DialogueTemplateOut(BaseModel):
    name: str
    template_id: int
    version: int


class DialogueOut(BaseModel):
    id: int
    conversation_bot_id: int
    conversation_bot_name: str
    conversation_bot_version: int
    bot_id: int
    bot_name: str
    bot_version: int
    templates: list[DialogueTemplateOut]
    status: str
    resumed_from_id: int | None
    created_at: datetime
    message_count: int
    # 最初の会話用エージェントの発言（一覧での見分け用）
    preview: str
    last_message_at: datetime | None


class DialogueDetail(DialogueOut):
    messages: list[DialogueMessageOut]
    comments: list[ConversationCommentOut]


class DialogueTemplateContentOut(DialogueTemplateOut):
    content: str


class DialogueSettingsOut(BaseModel):
    conversation_bot: ConversationSettingsOut
    bot: ConversationSettingsOut
    templates: list[DialogueTemplateContentOut]


class SimulatorParamOut(BaseModel):
    name: str
    # required（必須）/ optional（任意）/ global（指定不可。グローバル設定でのみ決める）
    kind: Literal["required", "optional", "global"]
    description: str
    global_key: str | None
    # 任意の項目の既定値（グローバル設定から取るものは、今の設定の値）
    default: Any = None


class SimulatorOut(BaseModel):
    name: str
    label: str
    description: str
    result_description: str
    input_schema: dict[str, Any]
    params: list[SimulatorParamOut]


class SimulatorProposeIn(BaseModel):
    request: str = Field(min_length=1)
    # 画面に出しているこれまでのやり取り（保存はしない）
    history: list[dict[str, str]] = []
    # 入力欄の今の引数（JSON の文字列のまま）
    current_args: str = ""


class SimulatorProposeOut(BaseModel):
    reply: str
    # 既定値の項目も含めた引数の全体。提案しない場合は None
    args: dict[str, Any] | None


class SimulationTestRun(BaseModel):
    args: dict[str, Any] = {}
    # シミュレーションを続けて実行する回数（LLM シミュレータの内側の回数ではない）
    times: int = Field(default=1, ge=1, le=20)


class SimulationRunOut(BaseModel):
    id: int
    simulator: str
    caller: str
    conversation_id: int | None
    message_id: int | None
    dialogue_id: int | None
    dialogue_message_id: int | None
    parallel_candidate_id: int | None = None
    agent_id: str
    args: dict[str, Any]
    params: dict[str, Any] | None
    status: str
    result: dict[str, Any] | None
    detail: dict[str, Any] | None
    error_count: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class SimulationRawCallOut(BaseModel):
    id: int
    label: str
    exchanges: list[dict[str, Any]]
    error: str | None
    created_at: datetime


class SimulationRunDetail(SimulationRunOut):
    raw_calls: list[SimulationRawCallOut]


class SimulationSettingsOut(BaseModel):
    values: dict[str, Any]
    defaults: dict[str, Any]
    descriptions: dict[str, str]


class ParallelNew(BaseModel):
    bot_id: int


class ParallelStart(BaseModel):
    # 分かれる位置（この Agent の発言まで写す）
    message_id: int


class ParallelRoundCreate(BaseModel):
    content: str = Field(min_length=1)
    count: int = Field(default=10, ge=1, le=50)


class ParallelCandidateOut(BaseModel):
    id: int
    index: int
    status: str
    text: str | None
    parts: list[dict[str, Any]] | None
    agent_state: dict[str, Any] | None
    error: str | None
    raw_call_id: int | None
    created_at: datetime
    finished_at: datetime | None
    # この候補を採用して作った会話
    conversation_ids: list[int]


class ParallelRoundOut(BaseModel):
    id: int
    content: str
    count: int
    created_at: datetime
    candidates: list[ParallelCandidateOut]


class ParallelConversationOut(BaseModel):
    id: int
    bot_id: int
    bot_name: str
    bot_version: int
    source_kind: str
    created_at: datetime
    message_count: int
    round_count: int
    # 分かれる位置の Agent の発言（一覧での見分け用）
    preview: str


class ParallelConversationDetail(ParallelConversationOut):
    messages: list[MessageOut]
    rounds: list[ParallelRoundOut]
