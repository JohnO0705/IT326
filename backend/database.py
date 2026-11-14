"""Small DB-API adapter. Oracle is normal; SQLite is an explicit local demo."""

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3

import oracledb
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.migrations import missing_columns, upgrade_columns
from backend.orm_mapping import configure_models, metadata

DATABASE_ERRORS = (SQLAlchemyError, sqlite3.DatabaseError, oracledb.DatabaseError)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = None
        self.sessionFactory = None
        
    @property
    def is_oracle(self) -> bool:
        return self.settings.database_backend == "oracle"

    def _create_engine(self) -> None:
        if self.engine is not None:
            return
        configure_models()
        if self.is_oracle:
            self.settings.require_oracle_credentials()
            url = URL.create(
                "oracle+oracledb", username=self.settings.database_username,
                password=self.settings.database_password,
                host=self.settings.database_host, port=self.settings.database_port,
                database=self.settings.database_sid,
            )
            self.engine = create_engine(
                url, pool_size=4, max_overflow=0, pool_timeout=5,
                pool_pre_ping=True, hide_parameters=True,
                connect_args={"tcp_connect_timeout": 8, "retry_count": 0},
            )

            @event.listens_for(self.engine, "connect")
            def oracle_timeout(connection, record):
                connection.call_timeout = 10000
        else:
            self.settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(
                URL.create("sqlite", database=str(self.settings.sqlite_path.resolve())),
                connect_args={"check_same_thread": False, "timeout": 15},
                pool_pre_ping=True, hide_parameters=True,
            )

            @event.listens_for(self.engine, "connect")
            def sqlite_options(connection, record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA busy_timeout = 15000")
                cursor.close()
        self.sessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def open(self) -> None:
        self._create_engine()
        if not self.is_oracle:
            self.initialize_schema()
        else:
            inspector = inspect(self.engine)
            if any(not inspector.has_table(t.name) for t in metadata.sorted_tables) or missing_columns(self.engine):
                raise RuntimeError("Run python setup_database.py to create or upgrade the TaskBuddy tables.")
        self.ping()

    def initialize_schema(self) -> list[str]:
        self._create_engine()
        messages = []
        if not self.is_oracle and missing_columns(self.engine):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            backup = self.settings.sqlite_path.with_name(self.settings.sqlite_path.name + f".before-orm-{stamp}.bak")
            with sqlite3.connect(self.settings.sqlite_path) as source:
                with sqlite3.connect(backup) as destination:
                    source.backup(destination)
            messages.append(f"Preserved a database backup at {backup}")
        metadata.create_all(self.engine)
        messages.extend(upgrade_columns(self.engine))
        return messages + ["TaskBuddy tables are ready."]

    @contextmanager
    def session(self):
        if self.sessionFactory is None:
            raise RuntimeError("The database is not open.")
        with self.sessionFactory.begin() as session:
            yield session

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(select(1))

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close(force=True)
            self.pool = None