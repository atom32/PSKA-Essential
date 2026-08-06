#!/usr/bin/env python3
"""Post-deploy smoke checks for PSKA full compose.

The script intentionally uses only stdlib so it can run on a fresh WSL host.
It verifies the browser-facing WebUI path, extension sidecar proxy, PSKA API,
Eidolia Hermes Gateway backend, optional dataset readiness, and optional
Eidolia async generation.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import http.cookiejar
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def env_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class SmokeClient:
    def __init__(self, base_url: str, password: str, timeout: int = 90) -> None:
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def raw(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Any | None = None,
        browser: bool = False,
        timeout: int | None = None,
    ) -> tuple[int, str]:
        headers = {"Accept": "application/json"}
        if browser:
            headers.update(
                {
                    "Origin": self.base_url,
                    "Referer": self.base_url + "/",
                    "Sec-Fetch-Site": "same-origin",
                }
            )
        if self.csrf:
            headers["X-Hermes-CSRF-Token"] = self.csrf
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                return int(response.status), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read().decode("utf-8", "replace")

    def json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Any | None = None,
        browser: bool = False,
        timeout: int | None = None,
    ) -> tuple[int, dict[str, Any]]:
        status, text = self.raw(path, method=method, payload=payload, browser=browser, timeout=timeout)
        if not text.strip():
            return status, {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"raw": text[:1200]}
        return status, parsed if isinstance(parsed, dict) else {"value": parsed}

    def login(self) -> dict[str, Any]:
        status, body = self.json("/api/auth/login", method="POST", payload={"password": self.password})
        if status != 200 or body.get("ok") is not True:
            raise RuntimeError(f"WebUI login failed: status={status} body={body}")
        status, shell = self.raw("/")
        if status != 200:
            raise RuntimeError(f"WebUI shell failed after login: status={status}")
        match = re.search(r"[a-f0-9]{64}", shell)
        if not match:
            raise RuntimeError("Could not find WebUI CSRF token in authenticated shell")
        self.csrf = match.group(0)
        return {"status": status, "cookie_count": len(self.jar), "csrf": "present"}

    def consent_extensions(self) -> dict[str, Any]:
        results = {}
        for extension_id in ("pska-mini", "eidolia"):
            status, body = self.json(
                "/api/extensions/sidecar-proxy-consent",
                method="POST",
                payload={"id": extension_id, "approved": True},
                browser=True,
            )
            if status != 200:
                raise RuntimeError(f"Consent failed for {extension_id}: status={status} body={body}")
            results[extension_id] = {"status": status}
        return results


def assert_ok(name: str, condition: bool, detail: Any) -> dict[str, Any]:
    if not condition:
        raise RuntimeError(f"{name} failed: {detail}")
    return {"ok": True, "detail": detail}


def compact_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": dataset.get("dataset_id") or dataset.get("id"),
        "name": dataset.get("name"),
        "document_count": dataset.get("document_count"),
        "chunk_count": dataset.get("chunk_count"),
        "embedding_model": dataset.get("embedding_model"),
    }


def resolve_config_path(env_file: Path, raw: str | None, fallback: str) -> Path:
    value = raw or fallback
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = env_file.resolve().parent / path
    return path


def check_generated_ragflow_embedding_config(env_file: Path, env: dict[str, str]) -> dict[str, Any]:
    suite_home = resolve_config_path(env_file, env.get("PSKA_SUITE_HOME"), ".runtime")
    service_conf = Path(env.get("PSKA_RAGFLOW_SERVICE_CONF", "")) if env.get("PSKA_RAGFLOW_SERVICE_CONF") else suite_home / "ragflow-service_conf.yaml.template"
    if not service_conf.is_absolute():
        service_conf = env_file.resolve().parent / service_conf
    if not service_conf.exists():
        return {"skipped": True, "reason": f"not found: {service_conf}"}
    text = service_conf.read_text(encoding="utf-8")
    expected_model = env.get("EMBEDDING_MODEL_ID") or "BAAI/bge-small-en-v1.5"
    ok = (
        "embedding_model:" in text
        and f"name: '{expected_model}'" in text
        and "factory: 'Builtin'" in text
        and "base_url: 'http://pska-embedding:80'" in text
    )
    if not ok:
        raise RuntimeError(
            "Generated RAGFlow embedding config is incomplete; run ./bootstrap.sh init with a version "
            "that writes name/factory/base_url for the Builtin TEI embedding model."
        )
    return {"ok": True, "file": str(service_conf), "model": expected_model, "factory": "Builtin"}


def run_local_command(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, text=True, capture_output=True, timeout=timeout)


def check_eidolia_archive_tools(env: dict[str, str]) -> dict[str, Any]:
    project = env.get("PSKA_FULL_PROJECT") or "pska-full"
    ps = run_local_command(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=eidolia",
            "--format",
            "{{.Names}}",
        ]
    )
    if ps.returncode != 0:
        raise RuntimeError(f"docker ps failed while checking Eidolia archive tools: {ps.stderr.strip()[:500]}")
    eidolia_container = (ps.stdout.strip().splitlines() or [""])[0]
    if not eidolia_container:
        raise RuntimeError(f"Eidolia container not found for project {project}")

    command = """
set -eu
zip_path="$(command -v zip)"
unzip_path="$(command -v unzip)"
printf 'zip=%s\\nunzip=%s\\n' "$zip_path" "$unzip_path"
""".strip()
    result = run_local_command(["docker", "exec", eidolia_container, "sh", "-lc", command])
    if result.returncode != 0:
        raise RuntimeError(
            "Eidolia archive tools are missing; rebuild the Eidolia image after updating InfinityCanvas. "
            f"stderr={result.stderr.strip()[:500]}"
        )
    tools: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            tools[key] = value
    return {"ok": True, "container": eidolia_container, "tools": tools}


def check_ragflow_embedding_model_tables(env: dict[str, str]) -> dict[str, Any]:
    project = env.get("RAGFLOW_PROJECT") or "ragflow"
    model = env.get("EMBEDDING_MODEL_ID") or "BAAI/bge-small-en-v1.5"
    ps = run_local_command(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=mysql",
            "--format",
            "{{.Names}}",
        ]
    )
    if ps.returncode != 0:
        return {"skipped": True, "reason": "docker ps failed", "stderr": ps.stderr.strip()[:500]}
    mysql_container = (ps.stdout.strip().splitlines() or [""])[0]
    if not mysql_container:
        return {"skipped": True, "reason": f"RAGFlow MySQL container not found for project {project}"}

    literal_model = "'" + model.replace("\\", "\\\\").replace("'", "''") + "'"
    sql = f"""
SELECT
  (SELECT COUNT(*) FROM llm_factories WHERE name='Builtin' AND status='1') AS builtin_factories,
  (SELECT COUNT(*) FROM llm WHERE fid='Builtin' AND llm_name={literal_model} AND model_type='embedding' AND status='1') AS builtin_models,
  (SELECT COUNT(*) FROM tenant) AS tenants,
  (SELECT COUNT(*) FROM tenant_llm WHERE llm_factory='Builtin' AND llm_name={literal_model} AND model_type='embedding' AND status='1') AS tenant_models,
  (SELECT COUNT(*) FROM tenant_model_provider WHERE provider_name='Builtin') AS ui_providers,
  (
    SELECT COUNT(*)
    FROM tenant_model_instance i
    JOIN tenant_model_provider p ON p.id=i.provider_id
    WHERE p.provider_name='Builtin' AND i.instance_name='default' AND i.status='active'
  ) AS ui_instances,
  (
    SELECT COUNT(*)
    FROM tenant_model m
    JOIN tenant_model_provider p ON p.id=m.provider_id
    JOIN tenant_model_instance i ON i.id=m.instance_id
    WHERE p.provider_name='Builtin'
      AND i.instance_name='default'
      AND m.model_name={literal_model}
      AND m.model_type='embedding'
      AND m.status='active'
  ) AS ui_models,
  (
    SELECT COUNT(*)
    FROM tenant
    WHERE embd_id=CONCAT({literal_model}, '@default@Builtin')
  ) AS tenant_default_models;
""".strip()
    command = f'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D rag_flow -N -B -e {shlex.quote(sql)}'
    result = run_local_command(["docker", "exec", mysql_container, "sh", "-lc", command])
    if result.returncode != 0:
        raise RuntimeError(f"RAGFlow model table check failed: {result.stderr.strip()[:800]}")
    parts = result.stdout.strip().split()
    if len(parts) < 8:
        raise RuntimeError(f"RAGFlow model table check returned unexpected output: {result.stdout.strip()[:800]}")
    (
        factory_count,
        model_count,
        tenant_count,
        tenant_model_count,
        ui_provider_count,
        ui_instance_count,
        ui_model_count,
        tenant_default_count,
    ) = [int(item) for item in parts[:8]]
    ok = (
        factory_count >= 1
        and model_count >= 1
        and tenant_model_count >= tenant_count
        and ui_provider_count >= tenant_count
        and ui_instance_count >= tenant_count
        and ui_model_count >= tenant_count
        and tenant_default_count >= tenant_count
    )
    if not ok:
        raise RuntimeError(
            "RAGFlow Builtin embedding is not visible to the model settings API; run ./bootstrap.sh ragflow-model-sync."
        )
    return {
        "ok": True,
        "model": model,
        "factory": "Builtin",
        "builtin_factories": factory_count,
        "builtin_models": model_count,
        "tenants": tenant_count,
        "tenant_models": tenant_model_count,
        "ui_providers": ui_provider_count,
        "ui_instances": ui_instance_count,
        "ui_models": ui_model_count,
        "tenant_default_models": tenant_default_count,
    }


def check_eidolia_generation(client: SmokeClient) -> dict[str, Any]:
    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    project_id = f"pska-smoke-eidolia-{stamp}"
    project_payload = {
        "id": project_id,
        "name": "PSKA smoke Eidolia",
        "description": "Post-deploy Hermes Gateway async generation smoke test.",
        "template": "blank",
        "smartStarter": False,
        "main": "# PSKA smoke Eidolia\n\n",
        "background": "This project verifies WebUI sidecar -> Eidolia -> Hermes Gateway.",
        "notes": "",
    }
    status, body = client.json(
        "/api/extensions/eidolia/sidecar/api/projects",
        method="POST",
        payload=project_payload,
        browser=True,
        timeout=120,
    )
    if status != 200:
        raise RuntimeError(f"Eidolia project create failed: status={status} body={body}")

    note = "PSKA smoke evidence: WebUI sidecar HTTP reaches Eidolia, and Eidolia should call Hermes Gateway."
    task = "Generate one concise thought confirming what this smoke evidence proves. Keep it factual."
    workspace = {
        "version": 1,
        "layoutVersion": 2,
        "projectId": project_id,
        "updatedAt": _dt.datetime.now(_dt.UTC).isoformat(),
        "settings": {"systemPrompt": "You are a concise verification assistant."},
        "nodes": [
            {
                "id": "artifact-smoke-evidence",
                "type": "note",
                "position": {"x": 80, "y": 80},
                "data": {
                    "kind": "artifact",
                    "subtype": "evidence",
                    "capabilities": ["editable", "context_source"],
                    "title": "Smoke evidence",
                    "content": note,
                    "summary": note,
                    "charCount": len("".join(note.split())),
                    "stats": {"chars": len(note), "non_whitespace_chars": len("".join(note.split()))},
                    "source": "smoke-test",
                },
            },
            {
                "id": "thought-smoke-task",
                "type": "thought",
                "position": {"x": 560, "y": 110},
                "data": {
                    "kind": "thought",
                    "subtype": "analysis",
                    "capabilities": ["editable", "runnable", "context_source"],
                    "title": "Smoke generation task",
                    "content": task,
                    "summary": task,
                    "charCount": len("".join(task.split())),
                    "stats": {"chars": len(task), "non_whitespace_chars": len("".join(task.split()))},
                    "origin": "smoke-test",
                    "source": "smoke-test",
                },
            },
        ],
        "edges": [
            {
                "id": "edge-smoke",
                "source": "artifact-smoke-evidence",
                "target": "thought-smoke-task",
                "type": "default",
                "label": "evidence",
                "data": {"relation": "supports", "domain": "evidence"},
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 0.75},
    }
    status, body = client.json(
        "/api/extensions/eidolia/sidecar/api/workspace",
        method="PUT",
        payload=workspace,
        browser=True,
        timeout=120,
    )
    if status != 200:
        raise RuntimeError(f"Eidolia workspace save failed: status={status} body={body}")

    status, body = client.json(
        "/api/extensions/eidolia/sidecar/api/agent/runs",
        method="POST",
        payload={
            "projectId": project_id,
            "flowId": "derive_thought",
            "outputMode": "thought",
            "backend": "hermes_gateway",
            "async": True,
            "asyncRun": True,
            "selectedNodeIds": ["thought-smoke-task", "artifact-smoke-evidence"],
            "startNodeId": "thought-smoke-task",
            "target": "Create a smoke-test thought",
            "requirements": "Mention that Eidolia used Hermes Gateway, based only on the provided smoke evidence.",
            "generation": {"targetWords": 120, "temperature": 0.2, "contextBudgetTokens": 4000},
        },
        browser=True,
        timeout=120,
    )
    if status != 200 or not body.get("run_id"):
        raise RuntimeError(f"Eidolia run start failed: status={status} body={body}")
    run_id = str(body["run_id"])
    final: dict[str, Any] | None = None
    for _ in range(60):
        time.sleep(5)
        status, poll = client.json(f"/api/extensions/eidolia/sidecar/api/agent/runs/{run_id}", browser=True, timeout=60)
        if status != 200:
            raise RuntimeError(f"Eidolia run poll failed: status={status} body={poll}")
        if poll.get("status") in {"completed", "failed", "cancelled"}:
            final = poll
            break
    if final is None:
        raise RuntimeError(f"Eidolia run did not finish: run_id={run_id}")
    if final.get("status") != "completed":
        raise RuntimeError(f"Eidolia run did not complete: {final}")
    status, workspace_body = client.json(
        f"/api/extensions/eidolia/sidecar/api/workspace?project={project_id}",
        browser=True,
        timeout=60,
    )
    return {
        "project_id": project_id,
        "run_id": run_id,
        "status": final.get("status"),
        "workspace_nodes": len(workspace_body.get("nodes") or []) if status == 200 else None,
        "workspace_edges": len(workspace_body.get("edges") or []) if status == 200 else None,
        "content_preview": str(final.get("content") or "")[:300],
    }


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    default_env = script_dir / ".env"
    env_path = Path(os.getenv("PSKA_FULL_ENV_FILE", str(default_env)))
    env = {**load_env_file(env_path), **os.environ}

    parser = argparse.ArgumentParser(description="Run PSKA full compose post-deploy smoke checks.")
    parser.add_argument("--env-file", default=str(env_path))
    parser.add_argument("--base-url")
    parser.add_argument("--password")
    parser.add_argument("--dataset-name", action="append", default=[])
    parser.add_argument("--run-eidolia", action="store_true")
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser()
    env.update(load_env_file(env_file))
    base_url = args.base_url or env.get("PSKA_SMOKE_BASE_URL") or f"http://127.0.0.1:{env.get('HERMES_WEBUI_PORT', '8787')}"
    password = args.password or env.get("PSKA_SMOKE_WEBUI_PASSWORD") or env.get("HERMES_WEBUI_PASSWORD", "")
    run_eidolia = args.run_eidolia or env_bool(env.get("PSKA_SMOKE_RUN_EIDOLIA"), False)
    dataset_names = args.dataset_name or [
        item.strip()
        for item in env.get("PSKA_SMOKE_DATASET_NAMES", "").split(",")
        if item.strip()
    ]
    if not password or password == "change-me":
        raise RuntimeError("WebUI password is required; set HERMES_WEBUI_PASSWORD or --password.")

    client = SmokeClient(base_url, password)
    results: dict[str, Any] = {"base_url": base_url, "checks": {}}

    results["checks"]["login"] = client.login()
    status, ext = client.json("/api/extensions/status")
    sidecar_ids = [item.get("id") for item in ext.get("sidecars") or []]
    results["checks"]["extensions"] = assert_ok(
        "extensions",
        status == 200 and {"pska-mini", "eidolia"}.issubset(set(sidecar_ids)),
        {"status": status, "sidecars": sidecar_ids, "manifest": (ext.get("manifest") or {}).get("status")},
    )
    results["checks"]["sidecar_consent"] = client.consent_extensions()

    status, pska = client.json("/api/extensions/pska-mini/sidecar/api/health", browser=True)
    results["checks"]["pska_health"] = assert_ok(
        "pska_health",
        status == 200 and pska.get("ok") is True,
        {"status": status, "providers": pska.get("providers"), "error": pska.get("error")},
    )

    status, eidolia = client.json("/api/extensions/eidolia/sidecar/api/agent/health", browser=True)
    results["checks"]["eidolia_agent"] = assert_ok(
        "eidolia_agent",
        status == 200
        and eidolia.get("ok") is True
        and eidolia.get("backend") == "hermes_gateway"
        and eidolia.get("agent_ready") is True,
        {
            "status": status,
            "backend": eidolia.get("backend"),
            "agent_ready": eidolia.get("agent_ready"),
            "api_base": eidolia.get("api_base"),
            "error": eidolia.get("error") or eidolia.get("ready_error"),
        },
    )
    results["checks"]["eidolia_archive_tools"] = check_eidolia_archive_tools(env)

    status, datasets_body = client.json("/api/extensions/pska-mini/sidecar/api/kb/datasets", browser=True, timeout=120)
    datasets = datasets_body.get("datasets") or datasets_body.get("items") or []
    results["checks"]["datasets"] = assert_ok(
        "datasets",
        status == 200,
        {"status": status, "count": len(datasets), "datasets": [compact_dataset(item) for item in datasets]},
    )

    readiness_results = []
    by_name = {str(item.get("name") or ""): item for item in datasets}
    for name in dataset_names:
        dataset = by_name.get(name)
        if not dataset:
            readiness_results.append({"name": name, "found": False})
            continue
        dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or "")
        status, readiness = client.json(
            "/api/extensions/pska-mini/sidecar/api/kb/readiness",
            method="POST",
            payload={"dataset_ids": [dataset_id]},
            browser=True,
            timeout=120,
        )
        body = readiness.get("readiness") or {}
        readiness_results.append(
            {
                "name": name,
                "id": dataset_id,
                "found": True,
                "status_code": status,
                "ready": body.get("ready"),
                "status": body.get("status"),
                "message": body.get("message"),
            }
        )
    if dataset_names:
        results["checks"]["dataset_readiness"] = readiness_results

    if env.get("EMBEDDING_ENABLED", "1") != "0":
        results["checks"]["ragflow_embedding_config"] = check_generated_ragflow_embedding_config(env_file, env)
        results["checks"]["ragflow_embedding_model_tables"] = check_ragflow_embedding_model_tables(env)

    if run_eidolia:
        results["checks"]["eidolia_generation"] = check_eidolia_generation(client)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
