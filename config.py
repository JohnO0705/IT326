"""Read local configuration without placing credentials in source code."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        if not 1 <= port <= 65535 or not 1 <= hours <= 168:
            raise ValueError("Use a valid API port and a session duration of 1 to 168 hours.")
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
        )

    def require_oracle_credentials(self) -> None:
        if not self.database_username or not self.database_password:
            raise ValueError(
                "Copy .env.example to .env and fill in the database username and password "
                "from your professor. To try the local demo first, run python run_demo.py."
            )
