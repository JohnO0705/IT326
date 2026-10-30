"""Start the API on this computer. Configuration is read from .env."""

import sys

import uvicorn

from backend.config import Settings
from backend.main import create_app


def main() -> int:
    try:
        settings = Settings.from_env()
        if settings.database_backend == "oracle":
            settings.require_oracle_credentials()
        print(f"TaskBuddy API: http://{settings.api_host}:{settings.api_port}")
        print(f"API documentation: http://127.0.0.1:{settings.api_port}/docs")
        uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
