from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Slack
    slack_bot_token: str = Field(..., description="Slack bot OAuth token (xoxb-...)")
    slack_signing_secret: str = Field(..., description="Slack app signing secret")
    slack_app_token: str = Field(
        default="",
        description="Slack app-level token for Socket Mode (xapp-...)",
    )
    slack_socket_mode: bool = Field(default=False, description="Enable Socket Mode")

    # Linear
    linear_api_key: str = Field(..., description="Linear personal API key")
    linear_company_slug: str = Field(
        default="company",
        description="Company slug used in Linear URLs",
    )

    # OpenAI (optional)
    openai_api_key: str = Field(default="", description="OpenAI API key for Vision OCR")

    # OCR
    ocr_provider: str = Field(
        default="easyocr",
        description="OCR backend: easyocr | tesseract | vision",
    )

    # Application
    port: int = Field(default=3000, ge=1, le=65535)
    log_level: str = Field(default="INFO")
    fallback_message_count: int = Field(
        default=20,
        ge=1,
        description="Messages to scan when /release is used outside a thread",
    )

    # Concurrency
    linear_max_concurrency: int = Field(
        default=5,
        ge=1,
        description="Max parallel Linear API requests",
    )
    request_timeout: float = Field(default=30.0, gt=0, description="HTTP timeout in seconds")


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
