"""TaskBuddy screens. Network work stays off Tkinter's main thread."""

from datetime import datetime
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

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


class TaskDialog(tk.Toplevel):
    def __init__(self, app: "TaskBuddyApp", task: dict | None = None):
        super().__init__(app)
        self.app = app
        self.task = task
        self.title("Edit task" if task else "Add task")
        self.configure(background=WHITE)
        left = max(0, app.winfo_rootx() + (app.winfo_width() - 600) // 2)
        top = max(0, app.winfo_rooty() + (app.winfo_height() - 460) // 2)
        self.geometry(f"600x460+{left}+{top}")
        self.minsize(500, 400)
        self.transient(app)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(self, style="Card.TFrame", padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        ttk.Label(frame, text="Edit task" if task else "Add a task", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 20))
        ttk.Label(frame, text="Title", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self.title_var = tk.StringVar(value=task["title"] if task else "")
        self.title_entry = ttk.Entry(frame, textvariable=self.title_var)
        self.title_entry.grid(row=2, column=0, sticky="ew", pady=(6, 14))
        ttk.Label(frame, text="Description", style="Card.TLabel").grid(row=3, column=0, sticky="w")
        self.description = tk.Text(frame, wrap="word", font=("Segoe UI", 11), height=7,
                                   relief="solid", borderwidth=1, highlightthickness=0, padx=10, pady=10)
        self.description.grid(row=4, column=0, sticky="nsew", pady=(6, 10))
        if task:
            self.description.insert("1.0", task["description"])
        self.error_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.error_var, style="Error.TLabel", wraplength=530).grid(row=5, column=0, sticky="w", pady=(0, 8))
        buttons = ttk.Frame(frame, style="Card.TFrame")
        buttons.grid(row=6, column=0, sticky="e")
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self.close)
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(buttons, text="Save task", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="left")
        self.bind("<Escape>", lambda event: self.close())
        self.bind("<Control-Return>", lambda event: self.save())
        self.title_entry.focus_set()

    def close(self):
        if not self.save_button.instate(["disabled"]):
            self.app.dialog = None
            self.destroy()

    def save(self):
        title = self.title_var.get().strip()
        description = self.description.get("1.0", "end-1c")
        if not title or len(title) > 200:
            self.error_var.set("Enter a title containing 1 to 200 characters.")
            return
        if len(description) > 10000:
            self.error_var.set("Keep the description under 10,000 characters.")
            return
        self.error_var.set("")
        self.save_button.state(["disabled"])
        self.cancel_button.state(["disabled"])
        action = (lambda: self.app.api.update_task(self.task["task_id"], title=title, description=description)) if self.task else (lambda: self.app.api.create_task(title, description))

        def saved(result):
            self.app.dialog = None
            self.destroy()
            self.app.load_tasks("Task saved.")

        def failed(error):
            if self.winfo_exists():
                self.save_button.state(["!disabled"])
                self.cancel_button.state(["!disabled"])
                self.error_var.set(str(error))

        if not self.app.submit(action, saved, "Saving task...", failed):
            self.save_button.state(["!disabled"])
            self.cancel_button.state(["!disabled"])


class TaskBuddyApp(tk.Tk):
    def __init__(self, api_url: str):
        super().__init__()
        self.api = ApiClient(api_url)
        self.title("TaskBuddy")
        self.geometry("1160x760")
        self.minsize(1000, 650)
        self.configure(background=BACKGROUND)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.results = queue.Queue()
        self.generation = 0
        self.busy = False
        self.closing = False
        self.user = None
        self.dialog = None
        self.tasks_by_id = {}
        self.view = "active"
        self.server_description = "Checking connection..."
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

    def show_login(self, mode: str = "login", message: str = ""):
        self.reset_screen()
        self.user = None
        self.api.token = None
        self.tasks_by_id = {}
        self.auth_mode = mode
        card = ttk.Frame(self.shell, style="Card.TFrame", padding=28)
        card.place(relx=0.5, rely=0.48, anchor="center", width=470)
        ttk.Label(card, text="TaskBuddy", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(card, text="Create your account" if mode == "register" else "Log in to your account", style="Muted.TLabel").pack(anchor="w", pady=(6, 18))
        self.login_username = self.auth_field(card, "Username")
        if mode == "register":
            ttk.Label(card, text="3-40 letters, numbers, periods, underscores or hyphens", style="Muted.TLabel", wraplength=410).pack(anchor="w", pady=(0, 6))
            self.register_email = self.auth_field(card, "Email")
        self.login_password = self.auth_field(card, "Password", password=True)
        if mode == "register":
            ttk.Label(card, text="Use 8-128 characters.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
            self.register_confirm = self.auth_field(card, "Confirm password", password=True)
        self.login_error = tk.StringVar(value=message)
        ttk.Label(card, textvariable=self.login_error, style="Error.TLabel", wraplength=410).pack(anchor="w", pady=(4, 8))
        self.auth_button = ttk.Button(card, text="Create account" if mode == "register" else "Log in", style="Primary.TButton", command=self.authenticate)
        self.auth_button.pack(fill="x")
        toggle = ttk.Button(card, text="Already have an account? Log in" if mode == "register" else "New to TaskBuddy? Create an account",
                            command=lambda: self.show_login("login" if mode == "register" else "register"))
        toggle.pack(fill="x", pady=(8, 0))
        self.action_widgets = [self.auth_button, toggle]
        self.connection_var = tk.StringVar(value=self.server_description)
        ttk.Label(self.shell, textvariable=self.connection_var, style="Footer.TLabel").pack(side="bottom", pady=(0, 6))
        ttk.Label(self.shell, text=self.api.base_url, style="Footer.TLabel").pack(side="bottom", pady=(0, 4))
        self.status_var = self.connection_var
        self.bind("<Return>", lambda event: self.authenticate() if not self.user else None)
        self.login_username.focus_set()

        def connected(result):
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
        username = self.login_username.get().strip()
        password = self.login_password.get()
        if not username or not password:
            self.login_error.set("Enter your username and password.")
            return
        if self.auth_mode == "register":
            if password != self.register_confirm.get():
                self.login_error.set("The passwords do not match.")
                return
            email = self.register_email.get().strip()
            action = lambda: self.api.register(username, email, password)
        else:
            action = lambda: self.api.login(username, password)
        self.login_error.set("")

        def authenticated(result):
            self.login_password.delete(0, "end")
            if self.auth_mode == "register":
                self.register_confirm.delete(0, "end")
            self.user = result["user"]
            self.show_tasks()

        self.submit(action, authenticated, "Signing in...")

    def show_tasks(self):
        self.reset_screen()
        self.view = "active"
        self.tasks_by_id = {}
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
        ttk.Label(sidebar, text=f"Signed in as\n{self.user['username']}", style="Muted.TLabel", wraplength=160).grid(row=6, column=0, sticky="w", pady=(24, 14))
        self.logout_button = ttk.Button(sidebar, text="Log out", command=self.logout)
        self.logout_button.grid(row=7, column=0, sticky="ew")

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

        details = ttk.Frame(content, style="Card.TFrame", padding=(16, 12))
        details.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        details.columnconfigure(0, weight=1)
        self.detail_title = tk.StringVar(value="Select a task to view its details")
        self.detail_meta = tk.StringVar()
        ttk.Label(details, textvariable=self.detail_title, style="Card.TLabel", font=("Segoe UI", 11, "bold"), wraplength=650).grid(row=0, column=0, sticky="w")
        ttk.Label(details, textvariable=self.detail_meta, style="Muted.TLabel", wraplength=650).grid(row=1, column=0, sticky="w", pady=(4, 6))
        self.description_text = tk.Text(details, height=3, wrap="word", font=("Segoe UI", 10),
                                         background=WHITE, foreground=MUTED, borderwidth=0,
                                         highlightthickness=0, state="disabled")
        self.description_text.grid(row=2, column=0, sticky="ew")

        actions = ttk.Frame(content)
        actions.grid(row=5, column=0, sticky="ew", pady=(14, 14))
        self.edit_button = ttk.Button(actions, text="Edit", command=self.edit_task)
        self.complete_button = ttk.Button(actions, text="Complete", command=lambda: self.toggle_task("is_completed"))
        self.pin_button = ttk.Button(actions, text="Pin", command=lambda: self.toggle_task("is_pinned"))
        self.hide_button = ttk.Button(actions, text="Hide", command=lambda: self.toggle_task("is_hidden"))
        self.delete_button = ttk.Button(actions, text="Delete", command=self.delete_task)
        self.restore_button = ttk.Button(actions, text="Restore", command=self.restore_task)
        self.empty_button = ttk.Button(actions, text="Delete all permanently", command=self.empty_deleted)
        for button in [self.edit_button, self.complete_button, self.pin_button, self.hide_button, self.delete_button, self.restore_button, self.empty_button]:
            button.pack(side="left", padx=(0, 8))
        footer = ttk.Frame(content)
        footer.grid(row=6, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Loading tasks...")
        ttk.Label(footer, textvariable=self.status_var, style="Footer.TLabel").pack(side="left")
        ttk.Label(footer, text=self.server_description, style="Footer.TLabel").pack(side="right")
        self.action_widgets = list(self.nav_buttons.values()) + [self.logout_button, self.add_button, self.refresh_button]
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
        normal = [self.edit_button, self.complete_button, self.pin_button, self.hide_button, self.delete_button]
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
        for button in [self.edit_button, self.complete_button, self.pin_button, self.hide_button, self.delete_button, self.restore_button]:
            button.state(["!disabled"] if selected and not self.busy else ["disabled"])
        self.empty_button.state(["!disabled"] if self.tasks_by_id and not self.busy else ["disabled"])
        self.status_combo.configure(state="disabled" if self.busy else "readonly")
        self.sort_combo.configure(state="disabled" if self.busy else "readonly")
        if self.view == "deleted":
            self.add_button.state(["disabled"])

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
        self.detail_meta.set(meta)
        self.description_text.configure(state="normal")
        self.description_text.delete("1.0", "end")
        self.description_text.insert("1.0", (task["description"] or "No description.") if task else "")
        self.description_text.configure(state="disabled")
        self.complete_button.configure(text="Reopen" if task and task["is_completed"] else "Complete")
        self.pin_button.configure(text="Unpin" if task and task["is_pinned"] else "Pin")
        self.hide_button.configure(text="Unhide" if task and task["is_hidden"] else "Hide")
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
