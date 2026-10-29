"""Small DB-API adapter. Oracle is normal; SQLite is an explicit local demo."""

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3

import oracledb

from backend.config import PROJECT_ROOT, Settings


def read_datetime(value) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool = None

    @property
    def is_oracle(self) -> bool:
        return self.settings.database_backend == "oracle"

    def _oracle_params(self):
        self.settings.require_oracle_credentials()
        return oracledb.ConnectParams(
            host=self.settings.database_host,
            port=self.settings.database_port,
            sid=self.settings.database_sid,
            tcp_connect_timeout=8,
            retry_count=0,
        )

    def open(self) -> None:
        if self.is_oracle:
            self.pool = oracledb.create_pool(
                user=self.settings.database_username,
                password=self.settings.database_password,
                params=self._oracle_params(),
                min=1,
                max=4,
                increment=1,
                getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
                wait_timeout=5000,
            )
            try:
                self.fetch_all("SELECT user_id FROM tb_users WHERE 1 = 0")
            except oracledb.DatabaseError as error:
                self.close()
                if error.args and getattr(error.args[0], "code", None) == 942:
                    raise RuntimeError(
                        "TaskBuddy tables were not found. Run python setup_database.py first."
                    ) from error
                raise
        else:
            self.initialize_schema()

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close(force=True)
            self.pool = None

    def _sqlite_connection(self):
        self.settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.settings.sqlite_path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def connection(self):
        if self.is_oracle:
            if self.pool is None:
                raise RuntimeError("The database connection pool is not open.")
            connection = self.pool.acquire()
            connection.call_timeout = 10000
        else:
            connection = self._sqlite_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def bind_datetime(self, value: datetime | None):
        if value is None:
            return None
        utc_value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return utc_value if self.is_oracle else utc_value.isoformat(timespec="microseconds")

    @staticmethod
    def _rows(cursor) -> list[dict]:
        names = [column[0].lower() for column in cursor.description]
        result = []
        for row in cursor.fetchall():
            result.append({
                name: value.read() if isinstance(value, oracledb.LOB) else value
                for name, value in zip(names, row)
            })
        return result

    def fetch_all(self, sql: str, parameters: dict | None = None) -> list[dict]:
        with self.connection() as connection:
            with_cursor = connection.cursor()
            try:
                with_cursor.execute(sql, parameters or {})
                return self._rows(with_cursor)
            finally:
                with_cursor.close()

    def fetch_one(self, sql: str, parameters: dict | None = None) -> dict | None:
        rows = self.fetch_all(sql, parameters)
        return rows[0] if rows else None

    def execute(self, sql: str, parameters: dict | None = None) -> int:
        with self.connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, parameters or {})
                return cursor.rowcount
            finally:
                cursor.close()

    def insert_id(self, sql: str, parameters: dict, id_column: str) -> int:
        with self.connection() as connection:
            cursor = connection.cursor()
            try:
                if self.is_oracle:
                    result = cursor.var(oracledb.NUMBER)
                    cursor.execute(
                        sql + f" RETURNING {id_column} INTO :result_id",
                        {**parameters, "result_id": result},
                    )
                    return int(result.getvalue()[0])
                cursor.execute(sql, parameters)
                return int(cursor.lastrowid)
            finally:
                cursor.close()

    def initialize_schema(self) -> list[str]:
        """Create missing tables only. Existing project data is preserved."""
        if not self.is_oracle:
            connection = self._sqlite_connection()
            try:
                connection.executescript((PROJECT_ROOT / "sql/sqlite_demo_schema.sql").read_text())
                connection.commit()
            finally:
                connection.close()
            return ["Local demo tables are ready."]

        script = (PROJECT_ROOT / "sql/oracle_schema.sql").read_text()
        script = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("--"))
        messages = []
        connection = oracledb.connect(
            user=self.settings.database_username,
            password=self.settings.database_password,
            params=self._oracle_params(),
        )
        connection.call_timeout = 10000
        try:
            with connection.cursor() as cursor:
                for statement in script.split(";"):
                    statement = statement.strip()
                    if not statement:
                        continue
                    name = statement.split()[2]
                    try:
                        cursor.execute(statement)
                        messages.append(f"Created {name}.")
                    except oracledb.DatabaseError as error:
                        if error.args and getattr(error.args[0], "code", None) == 955:
                            messages.append(f"{name} already exists; preserved existing data.")
                        else:
                            raise
        finally:
            connection.close()
        return messages

    def ping(self) -> None:
        self.fetch_all("SELECT 1 AS ready FROM dual" if self.is_oracle else "SELECT 1 AS ready")


DATABASE_ERRORS = (oracledb.DatabaseError, sqlite3.DatabaseError)


def is_duplicate(error: Exception) -> bool:
    if isinstance(error, sqlite3.IntegrityError):
        return "UNIQUE constraint failed" in str(error)
    return isinstance(error, oracledb.IntegrityError) and bool(error.args) and getattr(error.args[0], "code", None) == 1
