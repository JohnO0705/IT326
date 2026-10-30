# TaskBuddy

First working version of the IT 326 group project: a Tkinter desktop, a FastAPI
backend, and the school's Oracle 19c database. An explicit local demo uses SQLite
so you can try the application before configuring Oracle.

## Try the application first

On Windows, extract the project into a normal folder and double-click
**StartDemo.bat**. Keep the project files together. The first launch creates a
virtual environment and downloads the packages in `requirements.txt`.

You need **Python 3.10 or newer**, including Tkinter, and internet access for
the initial download. The standard Python Windows installer includes Tkinter.
This is a Python application, not a packaged Windows executable.

Alternatively, open PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_demo.py
```

If `py` is unavailable but `python` works, use `python -m venv .venv` for the first
command. The remaining commands stay the same.

Select **Create an account**, enter your own application username, email, and
password, then add a task. Close and reopen the demo, log in again, and the task
will still be there.

Demo data stays on this computer in `data/taskbuddy-demo.db`. The footer identifies
demo mode. Demo accounts and tasks are separate from Oracle and do not transfer
automatically. Oracle remains the normal configuration in `.env.example`.

## Connect the school's Oracle database

Follow `SQLStudentDirections.docx`. Connect to the ISU VPN when working off
campus. Confirm the professor's credentials work in SQL Developer first.

1. Install the Python packages using the commands above.
2. Copy the example configuration:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Open `.env` in VS Code and fill in these values locally:

   ```text
   TASKBUDDY_DB_USERNAME=your_team_database_username
   TASKBUDDY_DB_PASSWORD=your_team_database_password
   ```

   Keep `TASKBUDDY_DB=oracle`. The host is `10.110.10.90`, port `1521`, and
   **SID** `oracle`. This is a SID connection, not a service-name connection.
   Enclose a password containing `#` or spaces in double quotes. `.env` is
   excluded from Git; the actual credentials are not in this project.

4. Create the TaskBuddy tables:

   ```powershell
   .\.venv\Scripts\python.exe setup_database.py
   ```

   This creates missing `TB_` tables and indexes and preserves existing objects.
   It does not delete data or migrate existing table definitions.

5. Start the backend in one terminal and keep it running:

   ```powershell
   .\.venv\Scripts\python.exe run_server.py
   ```

6. Open a second terminal in the same folder and start the desktop:

   ```powershell
   .\.venv\Scripts\python.exe run_desktop.py
   ```

The footer should say **Connected to Oracle**. Create a TaskBuddy account inside
the application. The professor's Oracle login connects the backend to the
database; TaskBuddy users have their own accounts in `TB_USERS`.

The backend uses `python-oracledb` in Thin mode. SQL Developer is a development
tool for tables and SQL; it does not need to be running while you use the app.

## What works

- Account creation and case-insensitive username login.
- Argon2 password hashing, expiring sessions, and server-side logout.
- Separate task lists for each account.
- Creating, viewing, and editing tasks and descriptions.
- Completing and reopening tasks.
- Pinning and unpinning; pinned tasks appear first.
- Hiding tasks and viewing or unhiding them in Hidden tasks.
- Searching titles/descriptions, filtering by completion, and sorting.
- Recently Deleted, seven-day recovery, restoration, and permanent clearing.
- Saving accounts and tasks across desktop and backend restarts.

Expired deleted tasks are purged when that user's task data is accessed. They
cannot be recovered after seven days. There is no separate background cleanup
service yet. Restore returns a task to My tasks, including one previously hidden.

## Later milestones

These user features are not exposed in the API or desktop yet:

- Editing or deleting accounts and Forgot Password.
- Adding, editing, and deleting persisted subtasks.
- Scheduling reminders and sending emails.
- Exporting tasks to JSON.
- The unit test suite, which is deliberately deferred.

`Subtask.py` and `Reminder.py` contain domain objects, and the schema includes
their tables as a foundation. These features are not complete merely because
the classes and tables exist. The desktop only shows implemented actions.

## Walk through the code

| File or folder | Responsibility |
| --- | --- |
| `run_demo.py` | Starts the API and desktop together with local demo storage. |
| `run_server.py` | Starts the backend using `.env`. |
| `run_desktop.py` | Starts the desktop against the configured API address. |
| `ITask.py`, `Task.py`, `Subtask.py` | Shared task interface and its implementations. |
| `User.py`, `Reminder.py`, `TaskFilter.py` | Account data, reminder data, filtering and sorting. |
| `desktop/app.py` | Forms, task views, dialogs, and button actions. |
| `desktop/api_client.py` | HTTP requests and the session token held in memory. |
| `backend/main.py` | API routes and authentication requirements. |
| `backend/schemas.py` | Incoming validation and public response fields. |
| `backend/services.py` | Coordinates account and task operations. |
| `backend/repository.py` | Reads and writes data using parameterized SQL. |
| `backend/database.py` | Oracle connections and the optional demo adapter. |
| `backend/security.py` | Password hashing and random session tokens. |
| `sql/oracle_schema.sql` | Schema for the school database. |

### Accounts and sessions

The registration form sends a request to `POST /auth/register`. FastAPI validates
it, `AccountService` hashes the password, and the repository inserts the account
into `TB_USERS`. The original password is not stored.

Registration also signs the user in. Login checks the stored password hash and
creates a session. A random token stays in desktop memory; only its SHA-256 hash
is saved in `TB_SESSIONS`. Protected requests carry that token. Logout deletes
the corresponding session from the database. Sessions expire after 12 hours by
default. Multiple simultaneous logins are supported.

Closing the window discards its token. Its database session expires naturally;
expired session rows are cleaned up when a new session is created.

### Tasks

The task dialog sends its request to the API. The API obtains the current user
from the session; the desktop cannot choose another task owner. `TaskService`
creates or changes a `Task`, and the repository saves it. Every task lookup and
update includes the signed-in user's ID.

After a save, the desktop reloads the task list. Network requests run in worker
threads; results return through a queue, and Tkinter widgets are updated on the
main thread so the window remains responsive.

Delete calls `Task.deleteTask()`, marks the task deleted, and sets a recovery
deadline seven days later. Restore clears the deletion fields. Permanently
clearing Recently Deleted removes all deleted tasks for that account, including
ones excluded by the current search or filter.

### Updated class model

`Task` and `Subtask` implement `ITask`. `TaskFilter` is used by the API for actual
filtering and sorting. Service and repository classes coordinate sessions and
database work around the domain classes.

The implementation adds `isCompleted`, `createdAt`, and `updatedAt` to Task to
support completion and sorting, plus a `TB_SESSIONS` support table. Reflect these
decisions in the next class diagram and explanation.

## Database tables

| Table | Data |
| --- | --- |
| `TB_USERS` | Usernames, emails, password hashes, and creation times. |
| `TB_TASKS` | Tasks, owners, state flags, and timestamps. |
| `TB_SESSIONS` | Hashed session tokens and expiration times. |
| `TB_SUBTASKS` | Foundation for subtasks belonging to tasks. |
| `TB_REMINDERS` | Foundation for a reminder attached to a task or subtask. |

Backend timestamps are UTC. API timestamps include a time zone; the desktop
displays dates in local time. Oracle booleans use `NUMBER(1)` with 0/1 constraints
for the Oracle 19c target.

## API documentation

With the normal backend running, open `http://127.0.0.1:8000/docs`. Registration
and login return an `access_token`. Paste that token into **Authorize** to try
protected routes as that user. `GET /health` also queries the selected database.
The combined demo prints its own API documentation address in the terminal.

## Setup help

- **Python/py not found:** install Python, then reopen the terminal.
- **Missing modules:** install `requirements.txt` with the same virtual
  environment Python used to launch the app.
- **Server unavailable:** start the backend before the desktop and check
  `TASKBUDDY_API_URL`. Use `run_demo.py` for the combined local demo.
- **Oracle connection fails:** check the professor's credentials, SID, and
  campus/VPN access. Confirm the account works in SQL Developer first.
- **Tables not found:** run `setup_database.py`, then restart the backend.
- **Table creation denied:** the school must grant the database account the
  necessary privileges; Python code cannot grant those privileges.
- **Port 8000 is in use:** stop the existing backend or change both
  `TASKBUDDY_API_PORT` and `TASKBUDDY_API_URL` to the same new port.

The default API address refers to the same computer as the desktop. Shared
backend hosting is a separate deployment step; this version does not deploy a
public server. A backend using the school database needs campus/VPN access.

## Verification so far

The API and actual Tkinter screens were exercised with the local demo database,
including account separation, task operations, recovery, logout, and persistence
across a backend restart. No unit test suite is included. The Oracle connection
and schema are implemented, but the live school database must still be verified
from a computer with campus/VPN access. The Windows batch launcher also needs
its first run on your Windows computer.

## Continue in GitHub

This version was built from `JohnO0705/IT326` and retains its original class
filenames. The download does not contain a `.git` directory. Copy its contents
into your existing local clone on a new branch, review the changes, and run the
application before committing. `.env`, local data, and virtual environments are
excluded by `.gitignore`. This build has not pushed changes to the team repo.

## Development credit

This implementation was prepared with assistance from OpenAI Codex. The team
should review, understand, adapt, and validate it and describe its own
contributions and the AI assistance in the course documentation.

Technical references:

- [FastAPI security and password hashing](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [Official python-oracledb connection documentation](https://python-oracledb.readthedocs.io/en/stable/user_guide/connection_handling.html)
