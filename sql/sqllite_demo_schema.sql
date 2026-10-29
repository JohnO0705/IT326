-- Optional local demo only. The Oracle schema is oracle_schema.sql.
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS tb_users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    username_key TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tb_tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES tb_users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0, 1)),
    is_hidden INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1)),
    deleted_at TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tb_tasks_user_idx ON tb_tasks(user_id, is_deleted, is_hidden);
CREATE TABLE IF NOT EXISTS tb_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES tb_users(user_id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tb_sessions_user_idx ON tb_sessions(user_id);
CREATE TABLE IF NOT EXISTS tb_subtasks (
    subtask_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tb_tasks(task_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    order_position INTEGER NOT NULL DEFAULT 0,
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1))
);
CREATE TABLE IF NOT EXISTS tb_reminders (
    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER UNIQUE REFERENCES tb_tasks(task_id) ON DELETE CASCADE,
    subtask_id INTEGER UNIQUE REFERENCES tb_subtasks(subtask_id) ON DELETE CASCADE,
    reminder_date TEXT NOT NULL,
    email TEXT NOT NULL,
    is_sent INTEGER NOT NULL DEFAULT 0 CHECK (is_sent IN (0, 1)),
    CHECK ((task_id IS NOT NULL AND subtask_id IS NULL) OR
           (task_id IS NULL AND subtask_id IS NOT NULL))
);
