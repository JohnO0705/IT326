"""Start a local API and desktop together using an explicit SQLite demo."""

from dataclasses import replace
import socket
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import uvicorn

from backend.config import Settings
from backend.main import create_app
from desktop.app import TaskBuddyApp


def main() -> int:
    settings = replace(Settings.from_env(), database_backend="sqlite")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    print(f"TaskBuddy local demo. Database: {settings.sqlite_path}")
    print(f"Local API documentation: {url}/docs")
    local_http = build_opener(ProxyHandler({}))
    try:
        for _ in range(100):
            try:
                with local_http.open(url + "/health", timeout=0.3):
                    break
            except (OSError, URLError):
                if not thread.is_alive():
                    raise RuntimeError("The local API could not start. Check the messages above.")
                time.sleep(0.1)
        else:
            raise RuntimeError("The local API did not become ready.")
        TaskBuddyApp(url).mainloop()
        return 0
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
