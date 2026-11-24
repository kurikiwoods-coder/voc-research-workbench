"""Run three real cold starts on this OS, each with a fresh, private SQLite directory."""

from pathlib import Path
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


def main():
    http = build_opener(ProxyHandler({}))
    for cycle in range(1, 4):
        with tempfile.TemporaryDirectory(prefix="voc-start-") as d:
            with socket.socket() as slot:
                slot.bind(("127.0.0.1", 0))
                port = slot.getsockname()[1]
            env = {**os.environ, "VOC_DATA_DIR": d}
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.dashboard.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "error",
                ],
                cwd=ROOT,
                env=env,
            )
            try:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError("Service stopped during startup")
                    try:
                        with http.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as reply:
                            health = json.load(reply)
                        break
                    except (URLError, ConnectionError, TimeoutError):
                        time.sleep(0.2)
                else:
                    raise TimeoutError("Service did not become ready")
                assert health == {"status": "ok", "schema_version": 3}
                with http.open(f"http://127.0.0.1:{port}/api/workspace") as reply:
                    assert json.load(reply)["history"] == []
                print(f"{platform.system()} cold start {cycle}/3: PASS", flush=True)
            finally:
                process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
