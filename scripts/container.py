"""Run the disposable demo database and API, forwarding container shutdown."""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

stopping = False
children: list[subprocess.Popen[bytes]] = []


def stop(signum: int, frame: object) -> None:
    global stopping
    stopping = True


def start(args: list[str]) -> subprocess.Popen[bytes]:
    child = subprocess.Popen(args, start_new_session=True)
    children.append(child)
    return child


def run(args: list[str]) -> None:
    child = start(args)
    while child.poll() is None and not stopping:
        time.sleep(0.1)
    if stopping or child.returncode != 0:
        raise RuntimeError("Startup interrupted or failed")


def main() -> int:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    with tempfile.TemporaryDirectory(prefix="calendar-") as directory:
        database = None
        try:
            if "DATABASE_URL" not in os.environ:
                data = str(Path(directory) / "data")
                run(
                    [
                        "initdb",
                        "-D",
                        data,
                        "--auth-local=peer",
                        "--auth-host=reject",
                        "--encoding=UTF8",
                        "--no-locale",
                    ]
                )
                database = start(
                    [
                        "postgres",
                        "-D",
                        data,
                        "-c",
                        "listen_addresses=",
                        "-c",
                        f"unix_socket_directories={directory}",
                        "-c",
                        "unix_socket_permissions=0700",
                        "-c",
                        "shared_buffers=32MB",
                        "-c",
                        "max_connections=20",
                    ]
                )
                deadline = time.monotonic() + 30
                while True:
                    if stopping or database.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Database startup failed")
                    probe = start(["pg_isready", "-h", directory])
                    while probe.poll() is None and not stopping:
                        time.sleep(0.1)
                    if probe.returncode == 0:
                        break
                    time.sleep(0.2)
                run(["createdb", "-h", directory, "calendar"])
                os.environ["DATABASE_URL"] = (
                    f"postgresql+psycopg://postgres@/calendar?host={directory}"
                )
            run(["alembic", "upgrade", "head"])
            if database is not None:
                run(
                    [
                        "psql",
                        "-X",
                        "-h",
                        directory,
                        "-d",
                        "calendar",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-c",
                        """
                        INSERT INTO event_types (id, name, description, duration_minutes)
                        VALUES (
                            'd0c5f4b98ee747c8b777a63314ef0475',
                            'Знакомство',
                            'Короткая демонстрационная встреча.',
                            30
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                    ]
                )
            api = start(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.app.main:create_app",
                    "--factory",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                    "--timeout-graceful-shutdown",
                    "8",
                ]
            )
            while not stopping:
                if api.poll() is not None or (database is not None and database.poll() is not None):
                    return 1
                time.sleep(0.1)
            return 0
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT if child is database else signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()


if __name__ == "__main__":
    sys.exit(main())
