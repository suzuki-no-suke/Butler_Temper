"""初期データを作る。

- Agent が一つも無いとき、各 AgentCore の既定の Agent 設定で Agent を作る
- 会話用エージェントが一つも無いとき、会話用エージェントの各 AgentCore の既定の設定で作る
- テンプレートが一つも無いとき、会話用エージェントの既定の設定が使う台本のサンプルを作る
"""

from sqlmodel import Session, select

from bt_backend.agents import list_agents, list_conversation_agents
from bt_backend.db import get_engine
from bt_backend.models import (
    Bot,
    BotVersion,
    ConversationBot,
    ConversationBotVersion,
    Template,
    TemplateVersion,
)

SAMPLE_TEMPLATE_NAME = "台本サンプル"
SAMPLE_TEMPLATE = """\
あなたは屋敷の主人です。相手はあなたに仕える執事です。
1. 朝の挨拶をして、今日の予定を尋ねる
2. 午後に入っている来客の予定について、気が進まない理由を話す
3. どう断ればよいか、執事に相談する
4. 執事の提案に一度は反論し、最後は受け入れる
5. 断ったあとの空いた時間に何をするか、執事と話す"""


def seed() -> dict[str, int]:
    """作った件数を、種類ごとに返す。"""
    created = {"agents": 0, "conversation_agents": 0, "templates": 0}
    with Session(get_engine()) as session:
        if session.exec(select(Bot)).first() is None:
            for agent in list_agents():
                bot = Bot(name=agent.name, agent_id=agent.id)
                session.add(bot)
                session.flush()
                assert bot.id is not None
                session.add(
                    BotVersion(
                        bot_id=bot.id, version=1, settings=agent.default_settings, note="既定の設定"
                    )
                )
                created["agents"] += 1
        if session.exec(select(ConversationBot)).first() is None:
            for core in list_conversation_agents():
                cbot = ConversationBot(name=core.name, agent_id=core.id)
                session.add(cbot)
                session.flush()
                assert cbot.id is not None
                session.add(
                    ConversationBotVersion(
                        bot_id=cbot.id, version=1, settings=core.default_settings, note="既定の設定"
                    )
                )
                created["conversation_agents"] += 1
        if session.exec(select(Template)).first() is None:
            template = Template(name=SAMPLE_TEMPLATE_NAME)
            session.add(template)
            session.flush()
            assert template.id is not None
            session.add(
                TemplateVersion(
                    template_id=template.id, version=1, content=SAMPLE_TEMPLATE, note="サンプル"
                )
            )
            created["templates"] += 1
        session.commit()
    return created


if __name__ == "__main__":
    created = seed()
    labels = {
        "agents": "Agent ",
        "conversation_agents": "会話用エージェント",
        "templates": "テンプレート",
    }
    for key, label in labels.items():
        print(
            f"{label}を {created[key]} 件作成しました"
            if created[key]
            else f"{label}が既にあるため作成しませんでした"
        )
