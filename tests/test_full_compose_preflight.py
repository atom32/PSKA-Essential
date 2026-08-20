from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "deploy" / "full-compose" / "bootstrap.sh"


class FullComposePreflightTests(unittest.TestCase):
    def test_preflight_passes_without_writing_runtime_when_ports_are_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_file = _write_env(tmp_path / ".env", _free_port_values())
            result = _run_preflight(env_file)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Embedding profile enabled", result.stdout)
            self.assertIn("preflight passed", result.stdout)
            self.assertFalse((tmp_path / ".runtime").exists())

    def test_preflight_fails_when_embedding_port_is_already_in_use(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener, tempfile.TemporaryDirectory() as tmp:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            values = _free_port_values()
            values["EMBEDDING_HOST_PORT"] = str(port)
            env_file = _write_env(Path(tmp) / ".env", values)

            result = _run_preflight(env_file)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL Embedding / TEI", result.stdout)
            self.assertIn(str(port), result.stdout)


def _run_preflight(env_file: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PSKA_FULL_ENV_FILE": str(env_file),
        "PSKA_FULL_PREFLIGHT_SKIP_DOCKER": "1",
    }
    return subprocess.run(
        ["bash", str(BOOTSTRAP), "preflight"],
        cwd=BOOTSTRAP.parent,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _write_env(path: Path, values: dict[str, str]) -> Path:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _free_port_values() -> dict[str, str]:
    ports = _reserve_free_ports(10)
    return {
        "HERMES_WEBUI_PASSWORD": "test-password",
        "HERMES_GATEWAY_API_KEY": "test-gateway-key",
        "HERMES_WEBUI_BIND": "127.0.0.1",
        "HERMES_WEBUI_PORT": str(ports[0]),
        "HERMES_GATEWAY_PORT": str(ports[1]),
        "EMBEDDING_ENABLED": "1",
        "EMBEDDING_HOST_PORT": str(ports[2]),
        "RAGFLOW_API_KEY": "",
        "RAGFLOW_HOST_PORT": str(ports[3]),
        "RAGFLOW_WEB_HTTP_PORT": str(ports[4]),
        "RAGFLOW_WEB_HTTPS_PORT": str(ports[5]),
        "RAGFLOW_MYSQL_PORT": str(ports[6]),
        "RAGFLOW_REDIS_PORT": str(ports[7]),
        "RAGFLOW_MINIO_PORT": str(ports[8]),
        "RAGFLOW_MINIO_CONSOLE_PORT": str(ports[9]),
        "RAGFLOW_ES_PORT": str(_reserve_free_ports(1)[0]),
        "DOC_ENGINE": "elasticsearch",
    }


def _reserve_free_ports(count: int) -> list[int]:
    sockets: list[socket.socket] = []
    try:
        ports: list[int] = []
        for _ in range(count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
            ports.append(sock.getsockname()[1])
        return ports
    finally:
        for sock in sockets:
            sock.close()


if __name__ == "__main__":
    unittest.main()
