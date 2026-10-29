"""会話コンテキストの組み立て（文字数による切り出し）。"""

from collections.abc import Sequence

from bt_backend.agents.types import ChatTurn


def split_by_chars(
    turns: Sequence[ChatTurn], max_chars: int
) -> tuple[list[ChatTurn], list[ChatTurn]]:
    """新しい発言から数えて max_chars 文字までを recent、それより前を older に分ける。

    最後の発言（今回の利用者の発言）は文字数を超えても必ず recent に入れる。
    LLM API は利用者の発言から始まる必要があるため、recent の先頭が BOT の発言なら older に回す。
    """
    recent: list[ChatTurn] = []
    total = 0
    for turn in reversed(turns):
        if recent and total + len(turn.content) > max_chars:
            break
        recent.insert(0, turn)
        total += len(turn.content)
    older = list(turns[: len(turns) - len(recent)])
    while len(recent) > 1 and recent[0].role != "user":
        older.append(recent.pop(0))
    return older, recent


def to_messages(turns: Sequence[ChatTurn]) -> list[dict[str, str]]:
    return [{"role": t.role, "content": t.content} for t in turns]


def transcript(turns: Sequence[ChatTurn], user_label: str, bot_label: str) -> str:
    return "\n".join(f"{user_label if t.role == 'user' else bot_label}: {t.content}" for t in turns)
