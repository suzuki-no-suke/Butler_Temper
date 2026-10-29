"""Agent が一つも無いとき、各 AgentCore の既定の Agent 設定で Agent を作る。"""

from sqlmodel import Session, select

from bt_backend.agents import list_agents
from bt_backend.db import get_engine
from bt_backend.models import Bot, BotVersion


def seed() -> int:
    with Session(get_engine()) as session:
        if session.exec(select(Bot)).first() is not None:
            return 0
        agents = list_agents()
        for agent in agents:
            bot = Bot(name=agent.name, agent_id=agent.id)
            session.add(bot)
            session.flush()
            assert bot.id is not None
            session.add(
                BotVersion(
                    bot_id=bot.id, version=1, settings=agent.default_settings, note="既定の設定"
                )
            )
        session.commit()
        return len(agents)


if __name__ == "__main__":
    created = seed()
    print(
        f"Agent を {created} 件作成しました"
        if created
        else "Agent が既にあるため作成しませんでした"
    )
