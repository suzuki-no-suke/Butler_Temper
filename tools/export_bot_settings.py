"""BOT 設定を JSON テキストに書き出す。

BOT ごとに一つの JSON ファイル（全バージョンの設定を含む）を書き出す。
書き出し先は既定で <data>/exports/bot_settings。同じ名前のファイルは上書きする。
会話用エージェントは、同じ形で書き出し先の conversation_agents フォルダに書き出す。

使い方（リポジトリ直下で実行）:
    npm run export:bots
    npm run export:bots -- 書き出し先のフォルダ
"""

import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from bt_backend.agents import UnknownAgent, get_agent_info, get_conversation_agent_info
from bt_backend.config import get_settings
from bt_backend.db import get_engine
from bt_backend.models import Bot, BotVersion, ConversationBot, ConversationBotVersion


def bot_document(session: Session, bot: Bot) -> dict[str, Any]:
    try:
        agent: dict[str, Any] = {
            "id": bot.agent_id,
            "name": get_agent_info(bot.agent_id).name,
            "models": get_agent_info(bot.agent_id).models,
        }
    except UnknownAgent:
        agent = {"id": bot.agent_id}
    versions = session.exec(
        select(BotVersion).where(BotVersion.bot_id == bot.id).order_by(col(BotVersion.version))
    )
    return {
        "id": bot.id,
        "name": bot.name,
        "agent": agent,
        "unavailable_reason": bot.unavailable_reason,
        "created_at": bot.created_at.isoformat(),
        "versions": [
            {
                "version": v.version,
                "note": v.note,
                "created_at": v.created_at.isoformat(),
                "settings": v.settings,
            }
            for v in versions
        ],
    }


def conversation_bot_document(session: Session, bot: ConversationBot) -> dict[str, Any]:
    try:
        info = get_conversation_agent_info(bot.agent_id)
        agent: dict[str, Any] = {"id": bot.agent_id, "name": info.name, "models": info.models}
    except UnknownAgent:
        agent = {"id": bot.agent_id}
    versions = session.exec(
        select(ConversationBotVersion)
        .where(ConversationBotVersion.bot_id == bot.id)
        .order_by(col(ConversationBotVersion.version))
    )
    return {
        "id": bot.id,
        "name": bot.name,
        "agent": agent,
        "unavailable_reason": bot.unavailable_reason,
        "created_at": bot.created_at.isoformat(),
        "versions": [
            {
                "version": v.version,
                "note": v.note,
                "created_at": v.created_at.isoformat(),
                "settings": v.settings,
            }
            for v in versions
        ],
    }


def _write(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    conversation_dir = out_dir / "conversation_agents"
    written: list[Path] = []
    with Session(get_engine()) as session:
        for bot in session.exec(select(Bot).order_by(col(Bot.id))):
            written.append(_write(out_dir / f"bot-{bot.id}.json", bot_document(session, bot)))
        for cbot in session.exec(select(ConversationBot).order_by(col(ConversationBot.id))):
            conversation_dir.mkdir(exist_ok=True)
            written.append(
                _write(
                    conversation_dir / f"conversation-bot-{cbot.id}.json",
                    conversation_bot_document(session, cbot),
                )
            )
    return written


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0]) if argv else get_settings().bt_data_dir / "exports" / "bot_settings"
    written = export(out_dir)
    print(f"{len(written)} 件の BOT 設定（会話用エージェントを含む）を {out_dir} に書き出しました")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
