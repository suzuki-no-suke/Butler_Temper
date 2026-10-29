"""DB 接続。通常の DB と RAW 用の DB の二つを持つ。"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from bt_backend.config import get_settings


def _make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        get_settings().bt_data_dir.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


@lru_cache
def get_engine() -> Engine:
    return _make_engine(get_settings().database_url)


@lru_cache
def get_raw_engine() -> Engine:
    return _make_engine(get_settings().raw_database_url)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def get_raw_session() -> Iterator[Session]:
    with Session(get_raw_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
RawSessionDep = Annotated[Session, Depends(get_raw_session)]
