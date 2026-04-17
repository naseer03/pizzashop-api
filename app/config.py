from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://root:root@127.0.0.1:3306/pizzashop_api"
    # If set, this name wins (fixes Windows env DATABASE_URL overriding .env, or awkward DB names).
    mysql_database: str | None = Field(default=None, validation_alias="MYSQL_DATABASE")
    jwt_secret_key: str = "change-me-in-production-use-openssl-rand"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    cors_origins: str = "*"
    # Local menu image uploads (served under media_url_prefix).
    media_root: str = Field(default="data/uploads", validation_alias="MEDIA_ROOT")
    media_url_prefix: str = Field(
        default="/v1/media/menu-items",
        validation_alias="MEDIA_URL_PREFIX",
        description="Public URL path prefix for saved menu item images.",
    )
    max_upload_mb: int = Field(default=5, ge=1, le=50, validation_alias="MAX_UPLOAD_MB")


settings = Settings()
