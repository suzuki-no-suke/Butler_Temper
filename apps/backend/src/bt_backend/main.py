from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bt_backend.api import (
    bots,
    comments,
    conversation_bots,
    conversations,
    dialogues,
    settings_chat,
    templates,
)
from bt_backend.config import get_settings
from bt_backend.snapshot import current_source_hash


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 起動時に Agents のソースをバックアップしておく
    current_source_hash()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Butler Temper", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().bt_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(bots.router)
    app.include_router(conversations.router)
    app.include_router(comments.router)
    app.include_router(settings_chat.router)
    app.include_router(conversation_bots.router)
    app.include_router(templates.router)
    app.include_router(dialogues.router)
    return app


app = create_app()
