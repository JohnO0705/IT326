"""Read local configuration without placing credentials in source code."""

from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    database_backend: str = "oracle"
    database_host: str = "10.110.10.90"
    database_port: int = 1521
    database_sid: str = "oracle"
    database_username: str = ""
    database_password: str = ""
    sqlite_path: Path = PROJECT_ROOT / "data" / "taskbuddy-demo.db"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_url: str = "http://127.0.0.1:8000"
    session_hours: int = 12
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    reminder_poll_seconds: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        backend = os.getenv("TASKBUDDY_DB", "oracle").strip().lower()
        if backend not in {"oracle", "sqlite"}:
            raise ValueError("TASKBUDDY_DB must be oracle or sqlite.")
        path = Path(os.getenv("TASKBUDDY_SQLITE_PATH", "data/taskbuddy-demo.db"))
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        port = int(os.getenv("TASKBUDDY_API_PORT", "8000"))
        hours = int(os.getenv("TASKBUDDY_SESSION_HOURS", "12"))
        smtp_port = int(os.getenv("TASKBUDDY_SMTP_PORT", "587"))
        interval = int(os.getenv("TASKBUDDY_REMINDER_POLL_SECONDS", "30"))
        if not 1 <= port <= 65535 or not 1 <= smtp_port <= 65535:
            raise ValueError("Use valid API and SMTP ports.")
        if not 1 <= hours <= 168 or not 5 <= interval <= 3600:
            raise ValueError("Use 1-168 session hours and a 5-3600 second reminder interval.")
        return cls(
            database_backend=backend,
            database_host=os.getenv("TASKBUDDY_DB_HOST", "10.110.10.90").strip(),
            database_port=int(os.getenv("TASKBUDDY_DB_PORT", "1521")),
            database_sid=os.getenv("TASKBUDDY_DB_SID", "oracle").strip(),
            database_username=os.getenv("TASKBUDDY_DB_USERNAME", "").strip(),
            database_password=os.getenv("TASKBUDDY_DB_PASSWORD", ""),
            sqlite_path=path,
            api_host=os.getenv("TASKBUDDY_API_HOST", "127.0.0.1"),
            api_port=port,
            api_url=os.getenv("TASKBUDDY_API_URL", f"http://127.0.0.1:{port}").rstrip("/"),
            session_hours=hours,
            smtp_host=os.getenv("TASKBUDDY_SMTP_HOST", "").strip(),
            smtp_port=smtp_port,
            smtp_username=os.getenv("TASKBUDDY_SMTP_USERNAME", "").strip(),
            smtp_password=os.getenv("TASKBUDDY_SMTP_PASSWORD", ""),
            smtp_from=os.getenv("TASKBUDDY_SMTP_FROM", "").strip(),
            smtp_starttls=env_bool("TASKBUDDY_SMTP_STARTTLS", True),
            smtp_ssl=env_bool("TASKBUDDY_SMTP_SSL", False),
            reminder_poll_seconds=interval,
        )

    def require_oracle_credentials(self) -> None:
        if not self.database_username or not self.database_password:
            raise ValueError("Fill in the Oracle credentials in .env, or run python run_demo.py.")

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    def require_email_settings(self) -> None:
        if not self.email_configured:
            raise ValueError("Set TASKBUDDY_SMTP_HOST and TASKBUDDY_SMTP_FROM to send reminders.")