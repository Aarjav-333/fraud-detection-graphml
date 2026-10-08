import os
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder values shipped in this repo (config defaults, .env.example, README).
# They are fine for local dev but must never reach a public deployment.
_PLACEHOLDER_SECRET_KEYS = ("dev-secret-change-me", "change-this-to-a-long-random-string")
_PLACEHOLDER_ADMIN_PASSWORDS = ("admin123",)
_MIN_SECRET_KEY_LENGTH = 32
_MIN_SECRET_KEY_DISTINCT_CHARS = 10  # rejects "aaaa...", still allows hex keys
_MIN_ADMIN_PASSWORD_LENGTH = 12

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DATABASE_URL: str = "sqlite:///./fraud_detection.db"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    # Comma-separated list, e.g. "https://your-app.vercel.app,http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Only "development" allows the placeholder secrets above. Anything else
    # (including unset) is treated as production, so a deploy that forgets
    # this variable fails closed instead of running with public defaults.
    APP_ENV: str = "production"
    # Where pipeline outputs go: saved_models/ (models, rings, results) and
    # processed/features.csv. Empty keeps them in their usual places
    # (app/ml/saved_models, data/processed); the demo scenario points it at
    # its own copy so it never touches these. Relative to backend/.
    PIPELINE_OUTPUT_DIR: str = ""

    # hide_input_in_errors keeps secret values out of validation errors/logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.strip().lower() == "development"

    @property
    def saved_models_dir(self) -> str:
        if self.PIPELINE_OUTPUT_DIR:
            return os.path.normpath(os.path.join(BACKEND_DIR, self.PIPELINE_OUTPUT_DIR, "saved_models"))
        return os.path.join(BACKEND_DIR, "app", "ml", "saved_models")

    @property
    def processed_dir(self) -> str:
        if self.PIPELINE_OUTPUT_DIR:
            return os.path.normpath(os.path.join(BACKEND_DIR, self.PIPELINE_OUTPUT_DIR, "processed"))
        return os.path.join(BACKEND_DIR, "data", "processed")

    @property
    def cors_origins(self) -> list[str]:
        # Browsers send Origin as lowercase scheme://host[:port] with no path or
        # trailing slash, so reduce each entry to that - a URL pasted from the
        # address bar (e.g. https://My-App.vercel.app/rules) then still matches.
        origins = []
        for entry in self.ALLOWED_ORIGINS.split(","):
            entry = entry.strip()
            parts = urlsplit(entry)
            if parts.scheme and parts.netloc:
                entry = f"{parts.scheme}://{parts.netloc}".lower()
            else:
                entry = entry.rstrip("/")  # "*" or a malformed entry, kept as-is
            if entry:
                origins.append(entry)
        return origins


def _insecure_setting_problems(s: Settings) -> list[str]:
    problems = []

    key = s.SECRET_KEY
    if key != key.strip():
        problems.append("SECRET_KEY has leading/trailing whitespace")
    elif any(p in key.lower() for p in _PLACEHOLDER_SECRET_KEYS):
        problems.append("SECRET_KEY contains a placeholder value (anyone could forge login tokens)")
    elif len(key) < _MIN_SECRET_KEY_LENGTH:
        problems.append(f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters")
    elif len(set(key)) < _MIN_SECRET_KEY_DISTINCT_CHARS:
        problems.append("SECRET_KEY is too repetitive to be random")

    password = s.ADMIN_PASSWORD
    if password != password.strip():
        problems.append("ADMIN_PASSWORD has leading/trailing whitespace")
    elif any(p in password.lower() for p in _PLACEHOLDER_ADMIN_PASSWORDS):
        problems.append("ADMIN_PASSWORD contains the published default (admin123)")
    elif len(password) < _MIN_ADMIN_PASSWORD_LENGTH:
        problems.append(f"ADMIN_PASSWORD must be at least {_MIN_ADMIN_PASSWORD_LENGTH} characters")

    return problems


settings = Settings()

if not settings.is_development:
    _problems = _insecure_setting_problems(settings)
    if _problems:
        # A plain RuntimeError, not a pydantic error, so no setting values are
        # echoed into deploy logs - only the names of what is wrong.
        raise RuntimeError(
            f"Refusing to start with APP_ENV={settings.APP_ENV!r} and insecure settings: "
            + "; ".join(_problems)
            + ". Set them on your host (see DEPLOYMENT.md), or set APP_ENV=development "
            "for local development."
        )
