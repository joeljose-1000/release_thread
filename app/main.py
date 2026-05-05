from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from app.api.health import router as health_router
from app.config.settings import get_settings
from app.linear.client import LinearClient
from app.ocr.factory import create_ocr_provider
from app.services.release_service import ReleaseService
from app.slack.commands import register_commands
from app.utils.logging import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)

bolt_app = AsyncApp(
    token=settings.slack_bot_token,
    signing_secret=settings.slack_signing_secret,
)

linear_client = LinearClient(
    api_key=settings.linear_api_key,
    timeout=settings.request_timeout,
    max_concurrency=settings.linear_max_concurrency,
)

ocr_provider = create_ocr_provider(
    provider_name=settings.ocr_provider,
    openai_api_key=settings.openai_api_key,
)

release_service = ReleaseService(
    settings=settings,
    linear_client=linear_client,
    ocr_provider=ocr_provider,
)

register_commands(bolt_app, release_service)

handler = AsyncSlackRequestHandler(bolt_app)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app_starting", port=settings.port, ocr=settings.ocr_provider)
    yield
    logger.info("app_shutting_down")


api = FastAPI(
    title="Release Assistant",
    description="Slack-integrated release summary agent",
    version="1.0.0",
    lifespan=lifespan,
)

api.include_router(health_router)


@api.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@api.post("/slack/commands")
async def slack_commands(req: Request):
    return await handler.handle(req)


def start_socket_mode() -> None:
    """Start the app in Socket Mode (alternative to HTTP endpoints)."""
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    async def _run() -> None:
        socket_handler = AsyncSocketModeHandler(bolt_app, settings.slack_app_token)
        logger.info("starting_socket_mode")
        await socket_handler.start_async()

    asyncio.run(_run())


if __name__ == "__main__":
    if settings.slack_socket_mode:
        start_socket_mode()
    else:
        import uvicorn

        uvicorn.run(
            "app.main:api",
            host="0.0.0.0",
            port=settings.port,
            reload=False,
        )
