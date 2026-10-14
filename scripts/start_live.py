#!/usr/bin/env python3
"""Start the existing live services together; fail visibly if any service exits."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main():
    from backend.app.database import engine
    from sqlalchemy import text
    with engine.connect() as db:
        db.execute(text("SELECT 1"))

    print("Shared API/worker database:", engine.url.render_as_string(hide_password=True), flush=True)
    engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    for port in (8000, 5173):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} is already in use. Stop the existing ScrapLink services first.")
    commands = [
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        [sys.executable, "-m", "backend.app.workers.run_worker"],
        ["npm", "--prefix", "frontend", "run", "dev", "--", "--host", "127.0.0.1"],
    ]
    children = []
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for command in commands:
            children.append(subprocess.Popen(command, cwd=ROOT))
        print("ScrapLink: http://127.0.0.1:5173/ — keep this terminal open", flush=True)
        while True:
            for child in children:
                if child.poll() is not None:
                    raise RuntimeError(f"Service exited ({child.returncode}); see its error above")
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
