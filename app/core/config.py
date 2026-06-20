from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Fun With Friends API"

    database_url: str = "sqlite:///./fwf.db"

    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    first_admin_username: str = "admin"
    first_admin_email: str = "admin@example.com"
    first_admin_password: str = "admin123"

    cors_origins: str = "http://localhost:3000"
    # Optional regex to allow dynamic origins, e.g. Netlify preview deploys:
    #   CORS_ORIGIN_REGEX=https://.*\.netlify\.app
    cors_origin_regex: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        # Normalize: drop blanks and any trailing slash. Browsers send the
        # Origin header WITHOUT a trailing slash, and CORSMiddleware matches
        # exactly, so "https://site.app/" would never match "https://site.app".
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
