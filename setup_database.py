"""Create TaskBuddy's missing Oracle tables without deleting existing data."""

import sys

from backend.config import Settings
from backend.database import DATABASE_ERRORS, Database


def main() -> int:
    try:
        settings = Settings.from_env()
        database = Database(settings)
        for message in database.initialize_schema():
            print(message)
        print("Database setup complete.")
        return 0
    except (ValueError, RuntimeError, *DATABASE_ERRORS) as error:
        print(f"Database setup could not finish: {error}", file=sys.stderr)
        print("For Oracle, check .env, the SID, and your campus/VPN connection.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
