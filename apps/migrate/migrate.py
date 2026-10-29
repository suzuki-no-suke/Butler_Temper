"""マイグレーションの実行。通常の DB（main）と RAW 用の DB（raw）を扱う。

使い方（apps/backend の環境で実行する）:
    python migrate.py upgrade                 # 両方を最新にする
    python migrate.py revision main "説明"    # main の差分からマイグレーションを作る
    python migrate.py current
    python migrate.py check                   # モデル定義と DB に差分が無いか確かめる
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from bt_backend.config import get_settings

HERE = Path(__file__).resolve().parent
TARGETS = ("main", "raw")


def config_for(target: str) -> Config:
    settings = get_settings()
    settings.bt_data_dir.mkdir(parents=True, exist_ok=True)
    config = Config(str(HERE / "alembic.ini"), ini_section=target)
    url = settings.database_url if target == "main" else settings.raw_database_url
    config.set_main_option("sqlalchemy.url", url)
    return config


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        sys.exit(1)
    action = argv[0]
    if action == "upgrade":
        for target in TARGETS:
            command.upgrade(config_for(target), "head")
    elif action == "current":
        for target in TARGETS:
            print(f"[{target}]")
            command.current(config_for(target))
    elif action == "check":
        for target in TARGETS:
            command.check(config_for(target))
    elif action == "revision" and len(argv) == 3 and argv[1] in TARGETS:
        command.revision(config_for(argv[1]), message=argv[2], autogenerate=True)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
