from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    telegram_bot_token: str
    telegram_group_chat_id: int
    otp_pepper: str = Field(min_length=16)
    brevo_api_key: str
    brevo_from_email: str
    brevo_from_name: str
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = ""
    public_base_url: str = ""
    http_port: int = 8080
    email_dev_mode: bool = False
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
