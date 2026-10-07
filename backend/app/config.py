from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder values shipped in this repo (config defaults, .env.example, README).
# They are fine for local dev but must never reach a public deployment.
_PLACEHOLDER_SECRET_KEYS = {"dev-secret-change-me", "change-this-to-a-long-random-string"}
_PLACEHOLDER_ADMIN_PASSWORDS = {"admin123"}
_MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DATABASE_URL: str = "sqlite:///./fraud_detection.db"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    # Comma-separated list, e.g. "https://your-app.vercel.app,http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    # "production" turns on the insecure-defaults check below.
    APP_ENV: str = "development"
    # Render sets RENDER=true on every service, so a Render deploy is treated as
    # production even if APP_ENV was never configured.
    RENDER: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() == "production" or self.RENDER

    @property
    def cors_origins(self) -> list[str]:
        # Browsers send Origin without a trailing slash, so strip one if it was
        # pasted in from the address bar - otherwise the origin never matches.
        return [o.strip().rstrip("/") for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self):
        if not self.is_production:
            return self
        problems = []
        if self.SECRET_KEY in _PLACEHOLDER_SECRET_KEYS:
            problems.append("SECRET_KEY is a placeholder value (anyone could forge login tokens)")
        elif len(self.SECRET_KEY) < _MIN_SECRET_KEY_LENGTH:
            problems.append(f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters")
        if not self.ADMIN_PASSWORD or self.ADMIN_PASSWORD in _PLACEHOLDER_ADMIN_PASSWORDS:
            problems.append("ADMIN_PASSWORD is unset or the published default")
        if problems:
            raise ValueError(
                "Refusing to start in production with insecure settings: "
                + "; ".join(problems)
                + ". Set these environment variables on your host (see DEPLOYMENT.md)."
            )
        return self


settings = Settings()
