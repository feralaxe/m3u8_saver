from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv_ints(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(item.strip()) for item in value.split(",") if item.strip()}


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_user_ids: set[int]
    permanent_allowed_user_ids: set[int]
    data_dir: Path
    temp_dir: Path
    max_video_bytes: int
    ffmpeg_timeout_seconds: int
    http_timeout_seconds: float
    transcode_video: bool
    preferred_accel: str
    default_user_agent: str
    default_accept_language: str
    source_cookie: str
    log_level: str
    log_file: Path | None
    log_max_bytes: int
    log_backup_count: int

    @property
    def database_path(self) -> Path:
        return self.data_dir / "bot.sqlite3"


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    temp_dir = Path(os.getenv("TEMP_DIR", "./tmp")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        telegram_bot_token=token,
        admin_user_ids=_csv_ints(os.getenv("ADMIN_USER_IDS")),
        permanent_allowed_user_ids=_csv_ints(os.getenv("PERMANENT_ALLOWED_USER_IDS")),
        data_dir=data_dir,
        temp_dir=temp_dir,
        max_video_bytes=int(os.getenv("MAX_VIDEO_BYTES", str(2 * 1024 * 1024 * 1024))),
        ffmpeg_timeout_seconds=int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "7200")),
        http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "20")),
        transcode_video=_bool(os.getenv("TRANSCODE_VIDEO"), False),
        preferred_accel=os.getenv("PREFERRED_ACCEL", "auto").strip().lower(),
        default_user_agent=os.getenv(
            "DEFAULT_USER_AGENT",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125 Safari/537.36",
        ),
        default_accept_language=os.getenv(
            "DEFAULT_ACCEPT_LANGUAGE",
            "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        ),
        source_cookie=os.getenv("SOURCE_COOKIE", "").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        log_file=Path(log_file).resolve() if (log_file := os.getenv("LOG_FILE", "").strip()) else None,
        log_max_bytes=int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024))),
        log_backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5")),
    )
