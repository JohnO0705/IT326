"""Start the desktop against TASKBUDDY_API_URL in .env."""

import sys

from backend.config import Settings
from desktop.app import TaskBuddyApp


def main() -> int:
    try:
        settings = Settings.from_env()
        TaskBuddyApp(settings.api_url).mainloop()
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
