"""マイグレーションの実行。通常の DB（main）と RAW 用の DB（raw）を扱う。

alembic.ini の main / raw の節が、それぞれの環境にあたる。接続先は bt_backend の設定
（環境変数）から読むので、alembic.ini には書かない。alembic.ini は Windows では
OS の文字コード（cp932）で読まれるため、ASCII 以外の文字を書いてはならない。

使い方（apps/backend の環境で実行する）:
    python migrate.py upgrade                 # 両方を最新にする
    python migrate.py revision main "説明"    # main の差分からマイグレーションを作る
    python migrate.py current
    python migrate.py check                   # モデル定義とマイグレーションに差分が無いか確かめる
"""

import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

from bt_backend.config import get_settings

HERE = Path(__file__).resolve().parent
TARGETS = ("main", "raw")


def config_for(target: str, url: str | None = None) -> Config:
    if url is None:
        settings = get_settings()
        settings.bt_data_dir.mkdir(parents=True, exist_ok=True)
        url = settings.database_url if target == "main" else settings.raw_database_url
    config = Config(str(HERE / "alembic.ini"), ini_section=target)
    config.set_main_option("sqlalchemy.url", url)
    return config


def check() -> None:
    """一時的な SQLite にマイグレーションを流し、モデル定義との差分が無いか確かめる。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for target in TARGETS:
            config = config_for(target, f"sqlite:///{(Path(tmp) / f'{target}.db').as_posix()}")
            command.upgrade(config, "head")
            command.check(config)


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
        check()
    elif action == "revision" and len(argv) == 3 and argv[1] in TARGETS:
        command.revision(config_for(argv[1]), message=argv[2], autogenerate=True)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
