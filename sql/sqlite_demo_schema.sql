-- Optional local demo only. The Oracle schema is oracle_schema.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE tb_users (
    user_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(40) NOT NULL,
    username_key VARCHAR(40) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    security_question VARCHAR(200),
	security_answer_hash VARCHAR(512),
	UNIQUE (username_key)
);
CREATE TABLE tb_tasks (
    task_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    is_pinned BOOLEAN DEFAULT '0' NOT NULL,
    is_hidden BOOLEAN DEFAULT '0' NOT NULL,
    is_deleted BOOLEAN DEFAULT '0' NOT NULL,
    is_completed BOOLEAN DEFAULT '0' NOT NULL,
    deleted_at VARCHAR(40),
    expires_at VARCHAR(40),
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    FOREIGN KEY(user_id) REFERENCES tb_users (user_id) ON DELETE CASCADE,
	CHECK (is_pinned IN (0, 1)),
	CHECK (is_hidden IN (0, 1)),
	CHECK (is_deleted IN (0, 1)),
	CHECK (is_completed IN (0, 1))
);
CREATE INDEX tb_tasks_user_idx ON tb_tasks(user_id, is_deleted, is_hidden);

CREATE TABLE tb_sessions (
    token_hash VARCHAR(64) NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at VARCHAR(40) NOT NULL,
    PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES tb_users (user_id) ON DELETE CASCADE
);

CREATE INDEX  tb_sessions_user_idx ON tb_sessions(user_id);

CREATE TABLE tb_subtasks (
    subtask_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	task_id INTEGER NOT NULL,
	order_position INTEGER DEFAULT '0' NOT NULL,
	user_id INTEGER NOT NULL,
	title VARCHAR(200) NOT NULL,
	description TEXT,
	is_pinned BOOLEAN DEFAULT '0' NOT NULL,
	is_hidden BOOLEAN DEFAULT '0' NOT NULL,
	is_deleted BOOLEAN DEFAULT '0' NOT NULL,
	is_completed BOOLEAN DEFAULT '0' NOT NULL,
	deleted_at VARCHAR(40),
	expires_at VARCHAR(40),
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	FOREIGN KEY(task_id) REFERENCES tb_tasks (task_id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES tb_users (user_id) ON DELETE CASCADE,
	CHECK (is_pinned IN (0, 1)),
	CHECK (is_hidden IN (0, 1)),
	CHECK (is_deleted IN (0, 1)),
	CHECK (is_completed IN (0, 1))
);

CREATE INDEX tb_subtasks_task_idx ON tb_subtasks (task_id, order_position);

CREATE TABLE tb_reminders (
    reminder_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	task_id INTEGER,
	subtask_id INTEGER,
	reminder_date VARCHAR(40) NOT NULL,
	email VARCHAR(254) NOT NULL,
	is_sent BOOLEAN DEFAULT '0' NOT NULL,
	sent_at VARCHAR(40),
	CONSTRAINT tb_reminder_parent_ck CHECK ((task_id IS NOT NULL AND subtask_id IS NULL) OR (task_id IS NULL AND subtask_id IS NOT NULL)),
	UNIQUE (task_id),
	FOREIGN KEY(task_id) REFERENCES tb_tasks (task_id) ON DELETE CASCADE,
	UNIQUE (subtask_id),
	FOREIGN KEY(subtask_id) REFERENCES tb_subtasks (subtask_id) ON DELETE CASCADE,
	CHECK (is_sent IN (0, 1))
);
