# TaskBuddy

TaskBuddy is the IT 326 group's desktop task manager. It uses Python, Tkinter,
FastAPI, and SQLAlchemy. SQLite runs the local demo, and Oracle 19c is the school
database target.

## Run the demo

On Windows, extract the project into a normal folder and double-click
**StartDemo.bat**. Keep the files together. You need **Python 3.10 or newer**
with Tkinter, plus internet access for the first package download.

The launcher creates `.venv` inside the project and installs the packages there.
It does not install them globally. Running it again also installs any newly
required packages, including SQLAlchemy.

Alternatively, open PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_demo.py
```

If `py` is unavailable, use `python -m venv .venv` for the first command.
On macOS or Linux, use `python3` to create the environment and
`.venv/bin/python` for the other commands. Tkinter must be installed.

Demo data is saved in `data/taskbuddy-demo.db`. Demo accounts and tasks are
separate from Oracle. Closing and reopening the application keeps saved data.
The demo starts its own local backend and stops it when the window closes.

### Updating an older copy

Close TaskBuddy and its backend before replacing the source files. Keep your
existing `data` folder and local `.env`. Run **StartDemo.bat** again to install
the updated requirements.

The demo automatically adds the new database fields. Before upgrading an older
database, it saves a backup beside it named
`taskbuddy-demo.db.before-orm-<timestamp>.bak`. Accounts, passwords, tasks,
subtasks, reminders, and valid sessions are preserved.

Older accounts do not have a recovery question yet. Sign in and add one in
**Account settings** before using **Forgot password**.

## What works

- Registration, login, logout, and separate task lists for each account.
- Account changes, password changes, and account deletion.
- Password recovery using a question and a hashed answer.
- Creating, viewing, editing, completing, and reopening tasks.
- Pinning, hiding, searching, filtering, and sorting tasks.
- Recently Deleted, seven-day restoration, and permanent clearing.
- Adding, editing, ordering, completing, and deleting saved subtasks.
- Setting, editing, and deleting a reminder for a task or subtask.
- Sending scheduled reminder emails when SMTP is configured.
- Exporting active and hidden tasks, subtasks, and reminders to JSON.
- Keeping saved data after restarting the application.

Complete all subtasks before completing their parent task. Adding an unfinished
subtask or reopening one also reopens the parent. Deleting a subtask permanently
deletes it and its reminder.

Deleting a main task keeps its subtasks and reminders during the seven-day
recovery window. Restore returns it to **My tasks**. Expired deleted tasks are
removed when that user's task data is accessed. Clearing **Recently Deleted**
permanently removes every deleted task for that account, including ones hidden
by the current search or filter.

JSON export includes both **My tasks** and **Hidden tasks**, regardless of the
current search or filter. It leaves out deleted tasks and account credentials.

## Connect to the school database

Use the credentials and connection directions provided for class. Connect to
the ISU VPN when working off campus, and confirm the login in SQL Developer.

1. Install `requirements.txt` in the project virtual environment.
2. Copy `.env.example` to `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Fill in `TASKBUDDY_DB_USERNAME` and `TASKBUDDY_DB_PASSWORD` locally. Keep
   `TASKBUDDY_DB=oracle`. The supplied connection uses host `10.110.10.90`,
   port `1521`, and **SID** `oracle`. Enclose passwords containing `#` or spaces
   in double quotes. Do not upload `.env`.
4. Create or upgrade the TaskBuddy tables:

   ```powershell
   .\.venv\Scripts\python.exe setup_database.py
   ```

   This creates missing tables and adds the new columns to the first-version
   schema. It preserves existing rows. Run this setup explicitly for Oracle;
   normal backend startup does not change the Oracle schema.
5. Start the backend and keep its terminal open:

   ```powershell
   .\.venv\Scripts\python.exe run_server.py
   ```

6. Start the desktop from a second terminal:

   ```powershell
   .\.venv\Scripts\python.exe run_desktop.py
   ```

The footer should say **Connected to Oracle**. The school's database login is
used by the backend. Each person creates a separate TaskBuddy account inside
the application. SQL Developer does not need to stay open.

`python-oracledb` runs in Thin mode through SQLAlchemy. The live school Oracle
connection still needs to be checked from a computer with campus/VPN access.
The SQL files in `sql/` show the current table definitions; use the setup script
to upgrade existing tables.

## Configure email reminders

Reminders can be saved without email configuration. To deliver them, copy
`.env.example` to `.env` if needed and fill in your SMTP provider's settings:

```text
TASKBUDDY_SMTP_HOST=your_provider_smtp_host
TASKBUDDY_SMTP_PORT=587
TASKBUDDY_SMTP_USERNAME=your_smtp_username
TASKBUDDY_SMTP_PASSWORD=your_smtp_password
TASKBUDDY_SMTP_FROM=your_sender_address
TASKBUDDY_SMTP_STARTTLS=true
TASKBUDDY_SMTP_SSL=false
TASKBUDDY_REMINDER_POLL_SECONDS=30
```

Use the host, port, and authentication your provider requires. For a provider
using SSL on port 465, set `TASKBUDDY_SMTP_SSL=true` and
`TASKBUDDY_SMTP_STARTTLS=false`. Keep the real credentials in `.env`.

Restart the backend after changing settings. The same settings work with the
local demo. The backend must stay running for emails to be sent; closing the
combined demo also stops its email worker. Overdue unsent reminders are checked
again after startup.

The worker checks every 30 seconds by default. It sends reminders for unfinished
tasks and subtasks, including hidden tasks. Completed or deleted parent tasks
are skipped. Successfully sent reminders are marked with a timestamp so later
checks do not send them again. Failed deliveries stay pending for another try.
Editing a reminder schedules it again.

Delivery was checked with a local SMTP inbox. Your actual email provider still
needs its credentials and a check with that provider.

## Walk through the code

The desktop sends HTTP requests to FastAPI. Controllers read the request models
and call services. Services apply account and task rules, use domain objects to
change data, and ask the repository to save it. The repository uses SQLAlchemy
to read and write the selected database.

Domain classes contain their attributes and local changes. They do not open
connections or call controllers, services, or repositories. SQLAlchemy mappings
are defined separately in `backend/orm_mapping.py`, keeping database code out
of the domain classes.

| File or folder | Responsibility |
| --- | --- |
| `StartDemo.bat`, `run_demo.py` | Prepare the local environment and run the demo. |
| `run_server.py`, `run_desktop.py` | Run the backend and desktop separately. |
| `ITask.py` | Abstract base with shared task attributes and local changes. |
| `Task.py` | Main task data and its subtask collection. |
| `Subtask.py` | Shared task data plus its parent and position. |
| `User.py` | Account data and local account changes. |
| `Reminder.py` | Schedule, recipient, target, and sent state. |
| `LoginSession.py` | Hashed session token, account ID, and expiration. |
| `TaskFilter.py` | Search, completion filtering, and sorting. |
| `desktop/app.py` | Tkinter screens, dialogs, and button actions. |
| `desktop/api_client.py` | HTTP requests and the bearer token held in memory. |
| `backend/main.py` | Routes, authentication, error responses, and startup. |
| `backend/controllers.py` | AccountController and TaskController. |
| `backend/schemas.py`, `backend/public_data.py` | Input validation and public output fields. |
| `backend/services.py` | AccountService, TaskService, and ReminderService. |
| `backend/repository.py` | SQLAlchemy queries and persistence operations. |
| `backend/orm_mapping.py` | Table definitions and mappings for the domain classes. |
| `backend/database.py`, `backend/migrations.py` | Connections, transactions, and schema upgrades. |
| `backend/security.py` | Argon2 hashes and random session tokens. |
| `backend/email_sender.py`, `backend/reminder_worker.py` | SMTP delivery and scheduled checks. |
| `setup_database.py`, `sql/` | Database setup and reference SQL. |

For example, **Add task** opens `TaskDialog`, which calls `ApiClient.create_task`.
The API passes the request to `TaskController`, then `TaskService`. The service
creates a `Task` and calls the repository. SQLAlchemy maps its attributes to the
task table, and the request's transaction commits before the API returns success.
The desktop then refreshes the list.

The desktop never chooses a task's owner. The backend identifies the signed-in
user from their session and restricts lookups to that account. Passwords and
recovery answers are hashed with Argon2. Only the hash of each session token is
stored in the database; the actual token stays in desktop memory. Sessions
expire after 12 hours by default. Password recovery signs out all sessions, and
an account password change signs out the user's other sessions.

Desktop requests run in worker threads. Results return through a queue, and
Tkinter updates happen on its main thread.

## Database tables

| Table | Data |
| --- | --- |
| `TB_USERS` | Account information, password hash, and recovery question/answer hash. |
| `TB_SESSIONS` | Hashed tokens, owners, and expiration times. |
| `TB_TASKS` | Main tasks, owners, flags, and timestamps. |
| `TB_SUBTASKS` | Subtasks, parents, owners, ordering, and shared task fields. |
| `TB_REMINDERS` | One task or subtask target, schedule, recipient, and sent state. |

`ITask` is abstract and has no table. Its inherited fields are mapped separately
for `Task` and `Subtask`, keeping the existing table layout. Backend times are
UTC; the desktop displays and accepts local time. Deleting an account also
deletes its sessions, tasks, subtasks, and reminders.

## API documentation and setup help

With the backend running, open `http://127.0.0.1:8000/docs`. Registration and login
return an `access_token`; paste it into **Authorize** to try protected routes.
The combined demo prints its own documentation address in the terminal.

- **Missing Python:** install Python, then reopen the terminal.
- **Missing modules:** install `requirements.txt` with the virtual environment's Python.
- **Server unavailable:** start the backend and check `TASKBUDDY_API_URL`, or use the combined demo.
- **Oracle connection fails:** check credentials, SID, and campus/VPN access.
- **Schema needs updating:** run `setup_database.py`, then restart the backend.
- **No reminder email:** check SMTP settings, keep the backend running, and check its terminal for delivery errors.
- **Port 8000 is busy:** stop the other backend or update both `TASKBUDDY_API_PORT` and `TASKBUDDY_API_URL`.

The supplied launchers run a local backend. Shared server hosting is a separate
deployment step.

## Verification

Functional checks covered the API, the actual Tkinter desktop, account
separation, subtasks, recovery, export, deletion/restoration, saved data after
restart, and migration from the original demo schema. Scheduled email delivery
was checked against a local SMTP inbox, including repeat-delivery prevention
and rescheduling.

## Remaining Work

- Set up and test the connection to the school's Oracle database, including saving and loading accounts, tasks, subtasks, and reminders.
- Configure a real email provider and check that scheduled reminder emails arrive.
- Run the updated application on the team's Windows computers and fix any issues found.
- Add unit tests in a later deliverable.
