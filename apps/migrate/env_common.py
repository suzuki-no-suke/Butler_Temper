"""main / raw の env.py から共通で使う処理。"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool


def run(metadata: MetaData) -> None:
    config = context.config
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    url = config.get_main_option("sqlalchemy.url")
    # SQLite は ALTER に制約があるため batch モードを使う
    batch = bool(url and url.startswith("sqlite"))
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=metadata, render_as_batch=batch)
        with context.begin_transaction():
            context.run_migrations()
        return
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, render_as_batch=batch)
        with context.begin_transaction():
            context.run_migrations()
