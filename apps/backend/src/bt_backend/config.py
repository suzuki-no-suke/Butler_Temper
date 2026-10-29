"""環境変数から読む設定。ローカルでは secrets/secrets.env を読み込む。"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/backend/src/bt_backend/config.py から見たリポジトリのルート
REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _env_file() -> Path:
    return Path(os.environ.get("BT_ENV_FILE", REPO_ROOT / "secrets" / "secrets.env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_file(), extra="ignore")

    bt_data_dir: Path = REPO_ROOT / "data"
    # 未指定なら data フォルダ内の SQLite を使う
    bt_database_url: str | None = None
    bt_raw_database_url: str | None = None
    bt_cors_origins: list[str] = ["*"]

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None

    @property
    def database_url(self) -> str:
        return self.bt_database_url or f"sqlite:///{self.bt_data_dir / 'app.db'}"

    @property
    def raw_database_url(self) -> str:
        return self.bt_raw_database_url or f"sqlite:///{self.bt_data_dir / 'raw.db'}"

    @property
    def snapshot_dir(self) -> Path:
        return self.bt_data_dir / "agent_snapshots"


@lru_cache
def get_settings() -> Settings:
    return Settings()
