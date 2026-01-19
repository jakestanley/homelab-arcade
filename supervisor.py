import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def start_process(args, env=None, cwd=None):
    return subprocess.Popen(args, env=env, cwd=cwd)


def main() -> None:
    root = Path(__file__).resolve().parent
    python = sys.executable

    portal_env = os.environ.copy()
    portal_env.setdefault("PORTAL_PORT", "80")

    dummy_env = os.environ.copy()
    dummy_env.setdefault("DUMMY_PORT", "5001")

    cs2_env = os.environ.copy()
    cs2_env.setdefault("WEB_PORT", "5000")

    processes = [
        start_process([python, str(root / "portal_server.py")], env=portal_env, cwd=str(root)),
        start_process([python, str(root / "cs2" / "server.py")], env=cs2_env, cwd=str(root)),
        start_process([python, str(root / "dummy_server.py")], env=dummy_env, cwd=str(root)),
    ]

    def shutdown(_signum=None, _frame=None):
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        deadline = time.time() + 10
        for proc in processes:
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.2)
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for proc in processes:
                if proc.poll() is not None:
                    shutdown()
            time.sleep(1)
    finally:
        shutdown()


if __name__ == "__main__":
    main()
