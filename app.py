"""TaskBuddy screens. Network work stays off Tkinter's main thread."""

from datetime import datetime, timedelta, timezone
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from desktop.api_client import ApiClient, ApiError

BACKGROUND = "#f3f5fa"
WHITE = "#ffffff"
INK = "#1e293b"
MUTED = "#64748b"
BLUE = "#315cda"
ERROR = "#b42318"

SORT_OPTIONS = {"Newest first": "newest", "Oldest first": "oldest",
                "Title A-Z": "title_asc", "Title Z-A": "title_desc"}
STATUS_OPTIONS = {"All statuses": "all", "Incomplete": "open", "Completed": "completed"}
VIEW_TITLES = {"active": "My tasks", "hidden": "Hidden tasks", "deleted": "Recently deleted"}


def readable_date(value: str | None) -> str:
    if not value:
        return ""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%b %d, %Y %I:%M %p")


def dialog_body(dialog, app, title, width, height):
    dialog.app = app
    dialog.title(title)
    dialog.configure(background=WHITE)
    left = max(0, app.winfo_rootx() + (app.winfo_width() - width) // 2)
    top = max(0, app.winfo_rooty() + (app.winfo_height() - height) // 2)
    dialog.geometry(f"{width}x{height}+{left}+{top}")
    dialog.minsize(width - 50, height - 60)
    dialog.transient(app)
    dialog.grab_set()
    dialog.protocol("WM_DELETE_WINDOW", dialog.close)
    dialog.bind("<Escape>", lambda event: dialog.close())
    frame = ttk.Frame(dialog, style="Card.TFrame", padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 14))
    dialog.error_var = tk.StringVar(dialog)
    dialog.buttons = []
    return frame


def entry_field(parent, label, value="", password=False):
    ttk.Label(parent, text=label, style="Card.TLabel").pack(anchor="w")
    entry = ttk.Entry(parent, show="*" if password else "")
    entry.pack(fill="x", pady=(4, 9))
    entry.insert(0, value)
    return entry


def submit_dialog(dialog, action, on_success, message):
    dialog.error_var.set("")
    for button in dialog.buttons:
        button.state(["disabled"])

    def failed(error):
        if dialog.winfo_exists():
            for button in dialog.buttons:
                button.state(["!disabled"])
            dialog.error_var.set(str(error))

    if not dialog.app.submit(action, on_success, message, failed):
        for button in dialog.buttons:
            button.state(["!disabled"])


class TaskDialog(tk.Toplevel):
    def __init__(self, app, item=None, parent_task=None):
        super().__init__(app)
        self.item = item
        self.kind = "subtask" if parent_task is not None else "task"
        self.parentTaskId = parent_task["task_id"] if parent_task else None
        title = ("Edit " if item else "Add ") + self.kind
        frame = dialog_body(self, app, title, 620, 560 if parent_task else 500)
        self.title_entry = entry_field(frame, "Title", item["title"] if item else "")
        self.title_var = tk.StringVar(self, value=self.title_entry.get())
        ttk.Label(frame, text="Description", style="Card.TLabel").pack(anchor="w")
        self.description = tk.Text(frame, wrap="word", font=("Segoe UI", 11), height=6,
                                   relief="solid", borderwidth=1, padx=10, pady=8)
        self.description.pack(fill="both", expand=True, pady=(5, 10))
        if item:
            self.description.insert("1.0", item.get("description", ""))
        self.order_var = tk.IntVar(self, value=(item["order_position"] + 1) if item and parent_task else
                                  len(parent_task.get("subtasks", [])) + 1 if parent_task else 1)
        if parent_task:
            row = ttk.Frame(frame, style="Card.TFrame")
            row.pack(fill="x", pady=(0, 10))
            ttk.Label(row, text="Position", style="Card.TLabel").pack(side="left")
            ttk.Spinbox(row, from_=1, to=10001, textvariable=self.order_var, width=7).pack(side="left", padx=10)
        ttk.Label(frame, textvariable=self.error_var, style="Error.TLabel", wraplength=565).pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(frame, style="Card.TFrame")
        buttons.pack(anchor="e")
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self.close)
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(buttons, text="Save", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="left")
        self.buttons = [self.cancel_button, self.save_button]
        self.bind("<Control-Return>", lambda event: self.save())
        self.title_entry.focus_set()

    def close(self):
        if not self.app.busy:
            self.app.dialog = None
            self.destroy()

    def save(self):
        if self.app.busy:
            return
        title = self.title_entry.get().strip()
        description = self.description.get("1.0", "end-1c")
        if not 1 <= len(title) <= 200 or len(description) > 10000:
            self.error_var.set("Use a title of 1-200 characters and a description under 10,000 characters.")
            return
        details = {"title": title, "description": description}
        if self.kind == "subtask":
            try:
                position = self.order_var.get()
            except (tk.TclError, ValueError):
                position = 0
            if not 1 <= position <= 10001:
                self.error_var.set("Choose a position of 1 or greater.")
                return
            details["order_position"] = position - 1
            if self.item:
                action = lambda: self.app.api.update_subtask(self.item["subtask_id"], **details)
            else:
                action = lambda: self.app.api.create_subtask(self.parentTaskId, **details)
        elif self.item:
            action = lambda: self.app.api.update_task(self.item["task_id"], **details)
        else:
            action = lambda: self.app.api.create_task(title, description)

        def saved(result):
            self.app.dialog = None
            self.destroy()
            self.app.load_tasks("Saved.")

        submit_dialog(self, action, saved, "Saving...")


class AccountDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.account = app.user
        frame = dialog_body(self, app, "Account settings", 620, 750)
        self.username = entry_field(frame, "Username", self.account["username"])
        self.email = entry_field(frame, "Email", self.account["email"])
        self.current_password = entry_field(frame, "Current password (required)", password=True)
        self.new_password = entry_field(frame, "New password (optional)", password=True)
        self.confirm_password = entry_field(frame, "Confirm new password", password=True)
        ttk.Label(frame, text="Leave the recovery fields blank to keep your current question.",
                  style="Muted.TLabel", wraplength=565).pack(anchor="w", pady=(2, 8))
        self.question = entry_field(frame, "Recovery question (optional)")
        self.answer = entry_field(frame, "Recovery answer (optional)", password=True)
        ttk.Label(frame, textvariable=self.error_var, style="Error.TLabel", wraplength=565).pack(anchor="w", pady=(2, 8))
        row = ttk.Frame(frame, style="Card.TFrame")
        row.pack(fill="x", side="bottom")
        delete = ttk.Button(row, text="Delete account", command=self.delete_account)
        delete.pack(side="left")
        cancel = ttk.Button(row, text="Cancel", command=self.close)
        cancel.pack(side="right", padx=(8, 0))
        save = ttk.Button(row, text="Save changes", style="Primary.TButton", command=self.save)
        save.pack(side="right")
        self.buttons = [delete, cancel, save]

    def close(self):
        if not self.app.busy:
            self.app.dialog = None
            self.destroy()

    def save(self):
        if self.app.busy:
            return
        password = self.current_password.get()
        if not password:
            self.error_var.set("Enter your current password.")
            return
        details = {"username": self.username.get().strip(), "email": self.email.get().strip(),
                   "current_password": password}
        new = self.new_password.get()
        if new or self.confirm_password.get():
            if new != self.confirm_password.get():
                self.error_var.set("The new passwords do not match.")
                return
            details["new_password"] = new
        question, answer = self.question.get().strip(), self.answer.get().strip()
        if question or answer:
            if not question or not answer:
                self.error_var.set("Enter both a recovery question and its answer.")
                return
            details.update(security_question=question, security_answer=answer)

        def saved(user):
            self.app.user = user
            self.app.account_name_var.set("Signed in as\n" + user["username"])
            self.app.dialog = None
            self.destroy()
            self.app.status_var.set("Account updated.")

        submit_dialog(self, lambda: self.app.api.edit_account(details), saved, "Updating account...")

    def delete_account(self):
        if self.app.busy:
            return
        password = self.current_password.get()
        if not password:
            self.error_var.set("Enter your current password to delete your account.")
            return
        if not messagebox.askyesno("Delete account", "Permanently delete your account and all its tasks, subtasks and reminders?\nThis cannot be undone.", parent=self):
            return

        def deleted(result):
            self.app.dialog = None
            self.destroy()
            self.app.show_login(message="Your account was deleted.")

        submit_dialog(self, lambda: self.app.api.delete_account(password), deleted, "Deleting account...")


class ReminderDialog(tk.Toplevel):
    def __init__(self, app, item, item_type="task"):
        super().__init__(app)
        self.itemId = item["task_id"] if item_type == "task" else item["subtask_id"]
        self.itemType = item_type
        self.reminder = item.get("reminder")
        frame = dialog_body(self, app, "Edit reminder" if self.reminder else "Set reminder", 620, 490)
        ttk.Label(frame, text=item["title"], style="Card.TLabel", wraplength=565).pack(anchor="w", pady=(0, 12))
        date = datetime.fromisoformat(self.reminder["reminder_date"].replace("Z", "+00:00")).astimezone() if self.reminder else datetime.now().astimezone() + timedelta(hours=1)
        self.date_entry = entry_field(frame, "Local date and time (YYYY-MM-DD HH:MM)", date.strftime("%Y-%m-%d %H:%M"))
        self.email_entry = entry_field(frame, "Send reminder to", self.reminder["email"] if self.reminder else app.user["email"])
        text = "Email reminders are sent while the backend is running."
        if not app.email_reminders_enabled:
            text = "Email delivery has not been configured on this server. You can save a reminder, but it will not be emailed until delivery is configured."
        if self.reminder and self.reminder.get("sent_at"):
            text += "\nLast sent: " + readable_date(self.reminder["sent_at"]) + ". Choose a new time to send it again."
        ttk.Label(frame, text=text, style="Muted.TLabel", wraplength=565).pack(anchor="w", pady=(6, 12))
        ttk.Label(frame, textvariable=self.error_var, style="Error.TLabel", wraplength=565).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(frame, style="Card.TFrame")
        row.pack(fill="x", side="bottom")
        if self.reminder:
            delete = ttk.Button(row, text="Delete reminder", command=self.delete_reminder)
            delete.pack(side="left")
            self.buttons.append(delete)
        cancel = ttk.Button(row, text="Cancel", command=self.close)
        cancel.pack(side="right", padx=(8, 0))
        save = ttk.Button(row, text="Save reminder", style="Primary.TButton", command=self.save)
        save.pack(side="right")
        self.buttons += [cancel, save]

    def close(self):
        if not self.app.busy:
            self.app.dialog = None
            self.destroy()

    def saved(self, result):
        self.app.dialog = None
        self.destroy()
        self.app.load_tasks("Reminder updated.")

    def save(self):
        if self.app.busy:
            return
        try:
            date = datetime.strptime(self.date_entry.get().strip(), "%Y-%m-%d %H:%M").astimezone()
        except ValueError:
            self.error_var.set("Use YYYY-MM-DD HH:MM, for example 2026-12-15 14:30.")
            return
        if date <= datetime.now().astimezone():
            self.error_var.set("Choose a future date and time.")
            return
        details = {"reminder_date": date.astimezone(timezone.utc).isoformat(),
                   "email": self.email_entry.get().strip()}
        if self.reminder:
            action = lambda: self.app.api.update_reminder(self.reminder["reminder_id"], details)
        else:
            action = lambda: self.app.api.set_reminder(self.itemType, self.itemId, details)
        submit_dialog(self, action, self.saved, "Saving reminder...")

    def delete_reminder(self):
        if self.app.busy or not self.reminder:
            return
        if messagebox.askyesno("Delete reminder", "Delete this scheduled reminder?", parent=self):
            reminder_id = self.reminder["reminder_id"]
            submit_dialog(self, lambda: self.app.api.delete_reminder(reminder_id),
                          self.saved, "Deleting reminder...")


class TaskBuddyApp(tk.Tk):
    def __init__(self, api_url: str):
        super().__init__()
        self.api = ApiClient(api_url)
        self.title("TaskBuddy")
        self.geometry("1240x860")
        self.minsize(1060, 740)
        self.configure(background=BACKGROUND)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.results = queue.Queue()
        self.generation = 0
        self.busy = False
        self.closing = False
        self.user = None
        self.dialog = None
        self.tasks_by_id = {}
        self.subtasks_by_id = {}
        self.view = "active"
        self.server_description = "Checking connection..."
        self.email_reminders_enabled = False
        self.search_timer = None
        self.action_widgets = []
        self.shell = None
        self.configure_styles()
        self.poll_timer = self.after(70, self.drain_results)
        self.show_login()

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background=WHITE)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=("Segoe UI", 11))
        style.configure("Card.TLabel", background=WHITE, foreground=INK)
        style.configure("Muted.TLabel", background=WHITE, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Footer.TLabel", background=BACKGROUND, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Heading.TLabel", background=WHITE, foreground=INK, font=("Segoe UI", 25, "bold"))
        style.configure("Section.TLabel", background=WHITE, foreground=INK, font=("Segoe UI", 17, "bold"))
        style.configure("Info.TLabel", background=WHITE, foreground=BLUE, font=("Segoe UI", 10))
        style.configure("Error.TLabel", background=WHITE, foreground=ERROR, font=("Segoe UI", 10))
        style.configure("TEntry", padding=8, font=("Segoe UI", 11))
        style.configure("TCombobox", padding=6, font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 10), background=WHITE, foreground=INK)
        style.map("TButton", background=[("active", "#e9edf7")], foreground=[("disabled", "#94a3b8")])
        style.configure("Primary.TButton", background=BLUE, foreground=WHITE, borderwidth=0)
        style.map("Primary.TButton", background=[("disabled", "#9aace8"), ("active", "#2348b5")], foreground=[("disabled", WHITE)])
        style.configure("Nav.TButton", anchor="w", borderwidth=0, padding=(15, 11), background=WHITE)
        style.configure("SelectedNav.TButton", anchor="w", padding=(15, 11), background="#eaf0ff", foreground=BLUE)
        style.configure("Treeview", rowheight=38, background=WHITE, fieldbackground=WHITE, foreground=INK,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", padding=(8, 10), font=("Segoe UI", 10, "bold"), background="#edf1f8", foreground=MUTED)
        style.map("Treeview", background=[("selected", "#dfe8ff")], foreground=[("selected", "#17317a")])

    def reset_screen(self):
        self.generation += 1
        self.busy = False
        if self.search_timer:
            self.after_cancel(self.search_timer)
            self.search_timer = None
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.destroy()
        self.dialog = None
        if self.shell:
            self.shell.destroy()
        self.shell = ttk.Frame(self)
        self.shell.pack(fill="both", expand=True)
        self.action_widgets = []

    def show_login(self, mode="login", message=""):
        self.reset_screen()
        self.user = None
        self.api.token = None
        self.tasks_by_id = {}
        self.subtasks_by_id = {}
        self.auth_mode = mode
        card = ttk.Frame(self.shell, style="Card.TFrame", padding=28)
        card.place(relx=0.5, rely=0.48, anchor="center", width=500)
        ttk.Label(card, text="TaskBuddy", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(card, text="Create your account" if mode == "register" else "Log in to your account",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 18))
        self.login_username = self.auth_field(card, "Username")
        if mode == "register":
            ttk.Label(card, text="3-40 letters, numbers, periods, underscores or hyphens",
                      style="Muted.TLabel", wraplength=440).pack(anchor="w", pady=(0, 6))
            self.register_email = self.auth_field(card, "Email")
        self.login_password = self.auth_field(card, "Password", password=True)
        if mode == "register":
            ttk.Label(card, text="Use 8-128 characters.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
            self.register_confirm = self.auth_field(card, "Confirm password", password=True)
            self.register_question = self.auth_field(card, "Recovery question")
            self.register_answer = self.auth_field(card, "Recovery answer", password=True)
            ttk.Label(card, text="Choose an answer you will remember. Answers are not case sensitive.",
                      style="Muted.TLabel", wraplength=440).pack(anchor="w", pady=(0, 5))
        self.login_error = tk.StringVar(value=message)
        style = "Info.TLabel" if message.startswith(("Password updated", "Your account was deleted")) else "Error.TLabel"
        ttk.Label(card, textvariable=self.login_error, style=style, wraplength=440).pack(anchor="w", pady=(4, 8))
        self.auth_button = ttk.Button(card, text="Create account" if mode == "register" else "Log in",
                                     style="Primary.TButton", command=self.authenticate)
        self.auth_button.pack(fill="x")
        toggle = ttk.Button(card, text="Already have an account? Log in" if mode == "register" else "New to TaskBuddy? Create an account",
                            command=lambda: self.show_login("login" if mode == "register" else "register"))
        toggle.pack(fill="x", pady=(8, 0))
        self.action_widgets = [self.auth_button, toggle]
        if mode == "login":
            forgot = ttk.Button(card, text="Forgot password?", command=self.show_password_reset)
            forgot.pack(fill="x", pady=(6, 0))
            self.action_widgets.append(forgot)
        self.connection_var = tk.StringVar(value=self.server_description)
        ttk.Label(self.shell, textvariable=self.connection_var, style="Footer.TLabel").pack(side="bottom", pady=(0, 6))
        ttk.Label(self.shell, text=self.api.base_url, style="Footer.TLabel").pack(side="bottom", pady=(0, 4))
        self.status_var = self.connection_var
        self.bind("<Return>", lambda event: self.authenticate() if not self.user else None)
        self.login_username.focus_set()

        def connected(result):
            self.email_reminders_enabled = result.get("email_reminders", False)
            self.server_description = "Local demo - data is saved on this computer" if result["database"] == "sqlite" else "Connected to Oracle"
            self.connection_var.set(self.server_description)

        def unavailable(error):
            self.connection_var.set("Server unavailable - start the backend, then log in")

        self.submit(self.api.health, connected, "Checking connection...", unavailable)

    @staticmethod
    def auth_field(parent, label: str, password: bool = False):
        ttk.Label(parent, text=label, style="Card.TLabel").pack(anchor="w")
        entry = ttk.Entry(parent, show="*" if password else "")
        entry.pack(fill="x", pady=(4, 9))
        return entry

    def authenticate(self):
        if self.busy:
            return
        username, password = self.login_username.get().strip(), self.login_password.get()
        if not username or not password:
            self.login_error.set("Enter your username and password.")
            return
        if self.auth_mode == "register":
            if password != self.register_confirm.get():
                self.login_error.set("The passwords do not match.")
                return
            email = self.register_email.get().strip()
            question, answer = self.register_question.get().strip(), self.register_answer.get().strip()
            if not question or not answer:
                self.login_error.set("Enter a recovery question and its answer.")
                return
            action = lambda: self.api.register(username, email, password, question, answer)
        else:
            action = lambda: self.api.login(username, password)
        self.login_error.set("")

        def authenticated(result):
            self.login_password.delete(0, "end")
            if self.auth_mode == "register":
                self.register_confirm.delete(0, "end")
                self.register_answer.delete(0, "end")
            self.user = result["user"]
            self.show_tasks()

        self.submit(action, authenticated, "Signing in...")

    def show_tasks(self):
        self.reset_screen()
        self.view = "active"
        self.tasks_by_id = {}
        self.subtasks_by_id = {}
        self.shell.columnconfigure(1, weight=1)
        self.shell.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self.shell, style="Card.TFrame", padding=(18, 28))
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(5, weight=1)
        ttk.Label(sidebar, text="TaskBuddy", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 32))
        self.nav_buttons = {}
        for row, (view, title) in enumerate(VIEW_TITLES.items(), 1):
            button = ttk.Button(sidebar, text=title, style="Nav.TButton", command=lambda value=view: self.switch_view(value))
            button.grid(row=row, column=0, sticky="ew", pady=3)
            self.nav_buttons[view] = button
        self.account_name_var = tk.StringVar(value="Signed in as\n" + self.user["username"])
        ttk.Label(sidebar, textvariable=self.account_name_var, style="Muted.TLabel", wraplength=160).grid(row=6, column=0, sticky="w", pady=(24, 14))
        self.logout_button = ttk.Button(sidebar, text="Log out", command=self.logout)
        self.account_button = ttk.Button(sidebar, text="Account settings", command=self.show_account_settings)
        self.account_button.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        self.export_button = ttk.Button(sidebar, text="Export tasks to JSON", command=self.export_tasks)
        self.export_button.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        self.logout_button.grid(row=9, column=0, sticky="ew")

        content = ttk.Frame(self.shell, padding=24)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        header = ttk.Frame(content)
        header.grid(row=0, column=0, sticky="ew", pady=(2, 22))
        header.columnconfigure(0, weight=1)
        self.view_title = tk.StringVar()
        ttk.Label(header, textvariable=self.view_title, font=("Segoe UI", 25, "bold")).grid(row=0, column=0, sticky="w")
        self.add_button = ttk.Button(header, text="+ Add task", style="Primary.TButton", command=self.add_task)
        self.add_button.grid(row=0, column=1, sticky="e")

        controls = ttk.Frame(content)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        controls.columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(controls, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_var.trace_add("write", self.queue_search)
        self.search_entry.bind("<Return>", lambda event: self.load_tasks())
        self.status_filter = tk.StringVar(value="All statuses")
        self.status_combo = ttk.Combobox(controls, textvariable=self.status_filter, values=list(STATUS_OPTIONS), state="readonly", width=14)
        self.status_combo.grid(row=0, column=1, padx=(0, 10))
        self.status_combo.bind("<<ComboboxSelected>>", lambda event: self.load_tasks())
        self.sort_var = tk.StringVar(value="Newest first")
        self.sort_combo = ttk.Combobox(controls, textvariable=self.sort_var, values=list(SORT_OPTIONS), state="readonly", width=15)
        self.sort_combo.grid(row=0, column=2, padx=(0, 10))
        self.sort_combo.bind("<<ComboboxSelected>>", lambda event: self.load_tasks())
        self.refresh_button = ttk.Button(controls, text="Refresh", command=self.load_tasks)
        self.refresh_button.grid(row=0, column=3)
        ttk.Label(content, text="Search task titles and descriptions", style="Footer.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 10))

        list_card = ttk.Frame(content, style="Card.TFrame")
        list_card.grid(row=3, column=0, sticky="nsew")
        list_card.rowconfigure(0, weight=1)
        list_card.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(list_card, columns=("status", "title", "updated"), show="headings", selectmode="browse", height=8)
        for column, label in [("status", "Status"), ("title", "Task"), ("updated", "Updated")]:
            self.tree.heading(column, text=label, anchor="w")
        self.tree.column("status", width=90, minwidth=80, stretch=False)
        self.tree.column("title", width=380, minwidth=160)
        self.tree.column("updated", width=175, minwidth=160, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_card, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure("completed", foreground=MUTED)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.selection_changed())
        self.tree.bind("<Double-1>", lambda event: self.edit_task())
        self.empty_label = ttk.Label(list_card, text="", style="Muted.TLabel", justify="center", anchor="center")

        self.details_tabs = ttk.Notebook(content, height=210)
        self.details_tabs.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        details = ttk.Frame(self.details_tabs, style="Card.TFrame", padding=(16, 12))
        self.details_tabs.add(details, text="Task details")
        details.columnconfigure(0, weight=1)
        self.detail_title = tk.StringVar(value="Select a task to view its details")
        self.detail_meta = tk.StringVar()
        ttk.Label(details, textvariable=self.detail_title, style="Card.TLabel", font=("Segoe UI", 11, "bold"), wraplength=650).grid(row=0, column=0, sticky="w")
        ttk.Label(details, textvariable=self.detail_meta, style="Muted.TLabel", wraplength=650).grid(row=1, column=0, sticky="w", pady=(4, 6))
        self.description_text = tk.Text(details, height=3, wrap="word", font=("Segoe UI", 10),
                                         background=WHITE, foreground=MUTED, borderwidth=0,
                                         highlightthickness=0, state="disabled")
        self.description_text.grid(row=2, column=0, sticky="ew")
        self.build_subtask_panel()

        actions = ttk.Frame(content)
        actions.grid(row=5, column=0, sticky="ew", pady=(14, 14))
        self.edit_button = ttk.Button(actions, text="Edit", command=self.edit_task)
        self.complete_button = ttk.Button(actions, text="Complete", command=lambda: self.toggle_task("is_completed"))
        self.pin_button = ttk.Button(actions, text="Pin", command=lambda: self.toggle_task("is_pinned"))
        self.hide_button = ttk.Button(actions, text="Hide", command=lambda: self.toggle_task("is_hidden"))
        self.delete_button = ttk.Button(actions, text="Delete", command=self.delete_task)
        self.reminder_button = ttk.Button(actions, text="Reminder", command=self.manage_reminder)
        self.restore_button = ttk.Button(actions, text="Restore", command=self.restore_task)
        self.empty_button = ttk.Button(actions, text="Delete all permanently", command=self.empty_deleted)
        for button in [self.edit_button, self.complete_button, self.pin_button, self.hide_button, self.delete_button, self.reminder_button, self.restore_button, self.empty_button]:
            button.pack(side="left", padx=(0, 8))
        footer = ttk.Frame(content)
        footer.grid(row=6, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Loading tasks...")
        ttk.Label(footer, textvariable=self.status_var, style="Footer.TLabel").pack(side="left")
        ttk.Label(footer, text=self.server_description, style="Footer.TLabel").pack(side="right")
        self.action_widgets = list(self.nav_buttons.values()) + [self.logout_button, self.account_button, self.export_button, self.add_button, self.refresh_button]
        self.bind("<Control-n>", lambda event: self.add_task())
        self.bind("<F5>", lambda event: self.load_tasks())
        self.update_view_controls()
        self.load_tasks()

    def switch_view(self, view: str):
        if self.busy:
            return
        self.view = view
        self.update_view_controls()
        self.load_tasks()

    def update_view_controls(self):
        if not self.user:
            return
        self.view_title.set(VIEW_TITLES[self.view])
        for view, button in self.nav_buttons.items():
            button.configure(style="SelectedNav.TButton" if view == self.view else "Nav.TButton")
        normal = [self.edit_button, self.complete_button, self.pin_button, self.hide_button, self.delete_button, self.reminder_button]
        deleted = [self.restore_button, self.empty_button]
        for button in normal + deleted:
            button.pack_forget()
        for button in deleted if self.view == "deleted" else normal:
            button.pack(side="left", padx=(0, 8))
        self.update_buttons()

    def update_buttons(self):
        for widget in self.action_widgets:
            widget.state(["disabled"] if self.busy else ["!disabled"])
        if not self.user or not hasattr(self, "tree"):
            return
        selected = self.selected_task()
        for button in [self.edit_button, self.complete_button, self.pin_button, self.hide_button,
                       self.delete_button, self.reminder_button, self.restore_button]:
            button.state(["!disabled"] if selected and not self.busy else ["disabled"])
        self.empty_button.state(["!disabled"] if self.tasks_by_id and not self.busy else ["disabled"])
        self.status_combo.configure(state="disabled" if self.busy else "readonly")
        self.sort_combo.configure(state="disabled" if self.busy else "readonly")
        if self.view == "deleted":
            self.add_button.state(["disabled"])
        if hasattr(self, "subtask_add_button"):
            editable = bool(selected and self.view != "deleted" and not self.busy)
            self.subtask_add_button.state(["!disabled"] if editable else ["disabled"])
            child = self.selected_subtask()
            for button in self.subtask_action_buttons:
                button.state(["!disabled"] if editable and child else ["disabled"])
            self.subtask_complete_button.configure(text="Reopen" if child and child["is_completed"] else "Complete")

    def selected_task(self):
        selection = self.tree.selection()
        return self.tasks_by_id.get(selection[0]) if selection else None

    def queue_search(self, *args):
        if self.search_timer:
            self.after_cancel(self.search_timer)
        self.search_timer = self.after(350, self.finish_search)

    def finish_search(self):
        self.search_timer = None
        if self.busy:
            self.search_timer = self.after(150, self.finish_search)
        else:
            self.load_tasks()

    def load_tasks(self, message: str = ""):
        if not self.user or self.busy:
            return
        selected = self.selected_task()
        selected_id = str(selected["task_id"]) if selected else None
        params = {"view": self.view, "search": self.search_var.get(),
                  "sort": SORT_OPTIONS[self.sort_var.get()], "completion": STATUS_OPTIONS[self.status_filter.get()]}

        def loaded(tasks):
            self.tasks_by_id = {str(task["task_id"]): task for task in tasks}
            for item in self.tree.get_children():
                self.tree.delete(item)
            for task_id, task in self.tasks_by_id.items():
                title = ("Pinned | " if task["is_pinned"] else "") + task["title"]
                state = "Deleted" if task["is_deleted"] else "Done" if task["is_completed"] else "Open"
                self.tree.insert("", "end", iid=task_id, values=(state, title, readable_date(task["updated_at"])), tags=("completed",) if task["is_completed"] else ())
            if selected_id in self.tasks_by_id:
                self.tree.selection_set(selected_id)
                self.tree.see(selected_id)
            if tasks:
                self.empty_label.place_forget()
            else:
                empty = "No matching tasks." if self.search_var.get() else {
                    "active": "No tasks yet.\nAdd a task to get started.",
                    "hidden": "No hidden tasks.",
                    "deleted": "Recently Deleted is empty.\nDeleted tasks can be restored for seven days.",
                }[self.view]
                self.empty_label.configure(text=empty)
                self.empty_label.place(relx=0.5, rely=0.45, anchor="center")
            count = f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}"
            self.status_var.set(f"{message}  {count}".strip())
            self.selection_changed()

        self.submit(lambda: self.api.tasks(**params), loaded, "Loading tasks...")

    def selection_changed(self):
        task = self.selected_task()
        self.detail_title.set(task["title"] if task else "Select a task to view its details")
        meta = ""
        if task:
            meta = "Created " + readable_date(task["created_at"])
            if task["expires_at"]:
                meta += "   |   Recovery ends " + readable_date(task["expires_at"])
            if task.get("reminder"):
                reminder = task["reminder"]
                meta += "   |   Reminder " + ("sent " + readable_date(reminder["sent_at"]) if reminder["sent_at"] else readable_date(reminder["reminder_date"]))
        self.detail_meta.set(meta)
        self.description_text.configure(state="normal")
        self.description_text.delete("1.0", "end")
        self.description_text.insert("1.0", (task["description"] or "No description.") if task else "")
        self.description_text.configure(state="disabled")
        self.complete_button.configure(text="Reopen" if task and task["is_completed"] else "Complete")
        self.pin_button.configure(text="Unpin" if task and task["is_pinned"] else "Pin")
        self.hide_button.configure(text="Unhide" if task and task["is_hidden"] else "Hide")
        self.reminder_button.configure(text="Edit reminder" if task and task.get("reminder") else "Set reminder")
        self.load_subtasks()
        self.update_buttons()

    def add_task(self):
        if not self.user or self.busy or self.view == "deleted":
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        self.dialog = TaskDialog(self)

    def edit_task(self):
        if self.busy or self.view == "deleted":
            return
        task = self.selected_task()
        if task:
            if self.dialog and self.dialog.winfo_exists():
                self.dialog.lift()
                return
            self.dialog = TaskDialog(self, task)

    def toggle_task(self, field: str):
        task = self.selected_task()
        if task and not self.busy:
            self.submit(lambda: self.api.update_task(task["task_id"], **{field: not task[field]}),
                        lambda result: self.load_tasks("Task updated."), "Updating task...")

    def delete_task(self):
        task = self.selected_task()
        if not task or self.busy:
            return
        if messagebox.askyesno("Delete task", "Move this task to Recently Deleted?\nYou can restore it for seven days.", parent=self):
            self.submit(lambda: self.api.delete_task(task["task_id"]), lambda result: self.load_tasks("Task moved to Recently Deleted."), "Deleting task...")

    def restore_task(self):
        task = self.selected_task()
        if task and not self.busy:
            self.submit(lambda: self.api.restore_task(task["task_id"]), lambda result: self.load_tasks("Task restored to My tasks."), "Restoring task...")

    def empty_deleted(self):
        if self.busy:
            return
        if messagebox.askyesno("Permanently delete tasks", "Permanently delete ALL tasks in Recently Deleted, including any hidden by your search or filter?\nThis cannot be undone.", parent=self):
            self.submit(self.api.empty_deleted, lambda result: self.load_tasks(f"Permanently deleted {result['deleted_count']} tasks."), "Deleting tasks...")

    def logout(self):
        if not self.busy:
            self.submit(
                self.api.logout, lambda result: self.show_login(), "Logging out...",
                lambda error: self.show_login(message="Signed out on this computer. The server could not be reached."),
            )

    def submit(self, action, on_success, message: str, on_error=None) -> bool:
        if self.busy or self.closing:
            return False
        generation = self.generation
        self.busy = True
        self.status_var.set(message)
        self.update_buttons()

        def worker():
            try:
                result = action()
                self.results.put((generation, on_success, on_error, result, None))
            except Exception as error:
                self.results.put((generation, on_success, on_error, None, error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def drain_results(self):
        while True:
            try:
                generation, on_success, on_error, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation or self.closing:
                continue
            self.busy = False
            self.update_buttons()
            if error:
                self.status_var.set("The request could not finish.")
                if isinstance(error, ApiError) and error.status_code == 401 and self.user:
                    self.show_login(message="Your session has ended. Please log in again.")
                elif on_error:
                    on_error(error)
                elif not self.user:
                    self.login_error.set(str(error))
                else:
                    messagebox.showerror("TaskBuddy", str(error), parent=self)
            else:
                on_success(result)
        if not self.closing:
            self.poll_timer = self.after(70, self.drain_results)

    def close(self):
        self.closing = True
        self.api.token = None
        self.after_cancel(self.poll_timer)
        if self.search_timer:
            self.after_cancel(self.search_timer)
        self.destroy()

    def build_subtask_panel(self):
        self.subtask_frame = ttk.Frame(self.details_tabs, style="Card.TFrame", padding=10)
        self.details_tabs.add(self.subtask_frame, text="Subtasks (0)")
        self.subtask_frame.columnconfigure(0, weight=1)
        self.subtask_frame.rowconfigure(1, weight=1)
        bar = ttk.Frame(self.subtask_frame, style="Card.TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.subtask_add_button = ttk.Button(bar, text="+ Add subtask", command=self.add_subtask)
        self.subtask_add_button.pack(side="left", padx=(0, 7))
        edit = ttk.Button(bar, text="Edit", command=self.edit_subtask)
        self.subtask_complete_button = ttk.Button(bar, text="Complete", command=self.toggle_subtask)
        delete = ttk.Button(bar, text="Delete", command=self.delete_subtask)
        reminder = ttk.Button(bar, text="Reminder", command=lambda: self.manage_reminder("subtask"))
        self.subtask_action_buttons = [edit, self.subtask_complete_button, delete, reminder]
        for button in self.subtask_action_buttons:
            button.pack(side="left", padx=(0, 7))
        self.subtask_tree = ttk.Treeview(self.subtask_frame, columns=("position","status","title","reminder"),
                                        show="headings", selectmode="browse", height=3)
        for name,label,width in [("position","Order",55),("status","Status",80),("title","Subtask",330),("reminder","Reminder",190)]:
            self.subtask_tree.heading(name,text=label,anchor="w")
            self.subtask_tree.column(name,width=width,minwidth=45,stretch=name=="title")
        self.subtask_tree.grid(row=1,column=0,sticky="nsew")
        scrollbar=ttk.Scrollbar(self.subtask_frame,orient="vertical",command=self.subtask_tree.yview)
        scrollbar.grid(row=1,column=1,sticky="ns")
        self.subtask_tree.configure(yscrollcommand=scrollbar.set)
        self.subtask_tree.bind("<<TreeviewSelect>>",lambda event:self.update_buttons())
        self.subtask_tree.bind("<Double-1>",lambda event:self.edit_subtask())

    def load_subtasks(self):
        previous = self.subtask_tree.selection()
        task = self.selected_task()
        children = task.get("subtasks", []) if task else []
        self.subtasks_by_id = {str(child["subtask_id"]):child for child in children}
        for item in self.subtask_tree.get_children():
            self.subtask_tree.delete(item)
        for item_id, child in self.subtasks_by_id.items():
            reminder=child.get("reminder")
            date=("Sent" if reminder.get("sent_at") else readable_date(reminder["reminder_date"])) if reminder else ""
            self.subtask_tree.insert("","end",iid=item_id,values=(
                child["order_position"]+1,"Done" if child["is_completed"] else "Open",child["title"],date))
        if previous and previous[0] in self.subtasks_by_id:
            self.subtask_tree.selection_set(previous[0])
        self.details_tabs.tab(self.subtask_frame,text=f"Subtasks ({len(children)})")

    def selected_subtask(self):
        selected = self.subtask_tree.selection()
        return self.subtasks_by_id.get(selected[0]) if selected else None

    def add_subtask(self):
        task = self.selected_task()
        if self.busy or self.view == "deleted" or not task:
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        self.dialog=TaskDialog(self,parent_task=task)

    def edit_subtask(self):
        child = self.selected_subtask()
        parent = self.selected_task()
        if self.busy or self.view == "deleted" or not child:
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        self.dialog=TaskDialog(self,child,parent_task=parent)

    def toggle_subtask(self):
        child = self.selected_subtask()
        if child and not self.busy and self.view != "deleted":
            self.submit(lambda:self.api.update_subtask(child["subtask_id"],is_completed=not child["is_completed"]),
                        lambda result:self.load_tasks("Subtask updated."),"Updating subtask...")

    def delete_subtask(self):
        child = self.selected_subtask()
        if not child or self.busy or self.view == "deleted":
            return
        if messagebox.askyesno("Delete subtask","Permanently delete this subtask and its reminder?",parent=self):
            self.submit(lambda:self.api.delete_subtask(child["subtask_id"]),
                        lambda result:self.load_tasks("Subtask deleted."),"Deleting subtask...")

    def manage_reminder(self, item_type="task"):
        item=self.selected_task() if item_type=="task" else self.selected_subtask()
        if not item or self.busy or self.view=="deleted":
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        self.dialog=ReminderDialog(self,item,item_type)

    def show_account_settings(self):
        if not self.user or self.busy:
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        self.dialog=AccountDialog(self)

    def export_tasks(self):
        if not self.user or self.busy:
            return
        path=filedialog.asksaveasfilename(parent=self,title="Export tasks",defaultextension=".json",
                                        initialfile="taskbuddy-tasks.json",filetypes=[("JSON files","*.json")])
        if not path:
            return

        def saved(data):
            try:
                with open(path,"w",encoding="utf-8") as file:
                    json.dump(data,file,ensure_ascii=False,indent=2)
            except OSError as error:
                messagebox.showerror("Export tasks",f"The file could not be saved: {error}",parent=self)
                return
            self.status_var.set("Tasks exported to "+path)

        self.submit(self.api.export_tasks,saved,"Exporting tasks...")

    def show_password_reset(self):
        self.reset_screen()
        self.user=None
        self.api.token=None
        self.auth_mode="recovery"
        self.recovery_for=None
        card=ttk.Frame(self.shell,style="Card.TFrame",padding=28)
        card.place(relx=.5,rely=.48,anchor="center",width=510)
        ttk.Label(card,text="Reset your password",style="Section.TLabel").pack(anchor="w",pady=(0,15))
        self.recovery_username=entry_field(card,"Username")
        self.recovery_question_var=tk.StringVar(value="Enter your username, then load your question.")
        load=ttk.Button(card,text="Load recovery question",command=self.load_recovery_question)
        load.pack(fill="x",pady=(0,10))
        ttk.Label(card,textvariable=self.recovery_question_var,style="Muted.TLabel",wraplength=450).pack(anchor="w",pady=(0,10))
        self.recovery_answer=entry_field(card,"Recovery answer",password=True)
        self.recovery_password=entry_field(card,"New password",password=True)
        self.recovery_confirm=entry_field(card,"Confirm new password",password=True)
        self.login_error=tk.StringVar()
        ttk.Label(card,textvariable=self.login_error,style="Error.TLabel",wraplength=450).pack(anchor="w",pady=(4,10))
        save=ttk.Button(card,text="Reset password",style="Primary.TButton",command=self.finish_password_reset)
        save.pack(fill="x")
        back=ttk.Button(card,text="Back to login",command=self.show_login)
        back.pack(fill="x",pady=(8,0))
        self.status_var=tk.StringVar()
        ttk.Label(card,textvariable=self.status_var,style="Muted.TLabel").pack(anchor="w",pady=(10,0))
        self.action_widgets=[load,save,back]
        self.bind("<Return>",lambda event:self.finish_password_reset())
        self.recovery_username.focus_set()

    def load_recovery_question(self):
        if self.busy:
            return
        username=self.recovery_username.get().strip()
        if not username:
            self.login_error.set("Enter your username.")
            return
        self.login_error.set("")

        def loaded(result):
            self.recovery_for=username
            self.recovery_question_var.set(result["security_question"])
            self.status_var.set("Answer your question, then choose a new password.")
            self.recovery_answer.focus_set()

        self.submit(lambda:self.api.recovery_question(username),loaded,"Loading question...",
                    lambda error:self.login_error.set(str(error)))

    def finish_password_reset(self):
        if self.busy:
            return
        username=self.recovery_username.get().strip()
        if username!=self.recovery_for:
            self.login_error.set("Load the recovery question for this username first.")
            return
        password=self.recovery_password.get()
        answer=self.recovery_answer.get()
        if password!=self.recovery_confirm.get():
            self.login_error.set("The new passwords do not match.")
            return
        if not 8 <= len(password) <= 128 or not answer.strip():
            self.login_error.set("Enter your answer and a new password of 8-128 characters.")
            return
        self.login_error.set("")
        self.submit(lambda:self.api.reset_password(username,answer,password),
                    lambda result:self.show_login(message="Password updated. Sign in with your new password."),
                    "Updating password...",lambda error:self.login_error.set(str(error)))
