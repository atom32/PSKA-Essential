#!/usr/bin/env python3
"""Initialize the first-user PSKA dogfooding workspace.

The default action creates human-owned folders and note templates only. It does
not register roots, scan files, write source files, create reviews, or write
durable memory unless the caller explicitly opts into HTTP registration.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


DEFAULT_ROOT = Path.home() / "PSKA-Dogfood"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
MANIFEST_NAME = "PSKA_DOGFOOD_MANIFEST.json"


@dataclass(frozen=True)
class DogfoodDirectory:
    relative_path: str
    label: str
    permission_mode: str
    first_week: bool = False


DIRECTORIES: tuple[DogfoodDirectory, ...] = (
    DogfoodDirectory("daily", "PSKA Dogfood daily notes", "sidecar_write", first_week=True),
    DogfoodDirectory("decisions", "PSKA Dogfood decision records", "sidecar_write", first_week=True),
    DogfoodDirectory("projects", "PSKA Dogfood project states", "sidecar_write"),
    DogfoodDirectory("projects/pska", "PSKA project state", "sidecar_write", first_week=True),
    DogfoodDirectory("projects/hermes", "Hermes project state", "sidecar_write"),
    DogfoodDirectory("projects/eidolia", "Eidolia project state", "sidecar_write"),
    DogfoodDirectory("health", "PSKA Dogfood health and cognition logs", "read_only"),
    DogfoodDirectory("private-archive", "PSKA Dogfood private archive", "read_only"),
    DogfoodDirectory("reading", "PSKA Dogfood reading notes", "sidecar_write"),
    DogfoodDirectory("creative", "PSKA Dogfood creative notes", "sidecar_write", first_week=True),
    DogfoodDirectory("company", "PSKA Dogfood company context", "read_only"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first-user PSKA dogfooding workspace.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Workspace root to create.")
    parser.add_argument("--date", default=_today(), help="Template date, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing files.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing generated template files.")
    parser.add_argument("--register", action="store_true", help="Register first-week folders as PSKA source roots.")
    parser.add_argument("--register-all", action="store_true", help="Register every generated folder as a source root.")
    parser.add_argument("--scan", action="store_true", help="Scan registered roots after registration.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL, help="PSKA Product API base URL.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    payload = initialize_workspace(
        args.root,
        date=args.date,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )
    if args.register or args.register_all:
        registration_plan = registration_roots(
            args.root,
            register_all=args.register_all,
        )
        payload["registration_plan"] = [item.copy() for item in registration_plan]
        if not args.dry_run:
            registration = register_source_roots(
                args.api_base_url,
                registration_plan,
                scan=args.scan,
                timeout=args.timeout,
            )
            payload["registration"] = registration
            apply_registration_data_flow(payload, registration, scan_requested=args.scan)

    print(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if any(item.get("status") == "error" for item in payload.get("registration", [])):
        return 2
    return 0


def initialize_workspace(
    root: Path,
    *,
    date: str,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    normalized_date = _validate_date(date)
    root = root.expanduser().resolve()
    directories = [_directory_payload(root, spec) for spec in DIRECTORIES]
    files = _template_files(root, normalized_date)
    data_flow = {
        "writes_user_template_files": not dry_run,
        "writes_source_registry": False,
        "scans_source_roots": False,
        "writes_source_files": False,
        "creates_review": False,
        "writes_memory_directly": False,
    }
    payload: dict[str, Any] = {
        "schema": "pska.dogfood_workspace_init.v1",
        "status": "planned" if dry_run else "created",
        "root": str(root),
        "date": normalized_date,
        "directories": directories,
        "files": [{"path": str(path), "template": name} for name, path, _content in files],
        "registration_defaults": {
            "mode": "first_week",
            "paths": [spec.relative_path for spec in DIRECTORIES if spec.first_week],
        },
        "data_flow": data_flow,
        "next_actions": [
            {
                "action": "open_hermes_webui",
                "description": "Open Hermes WebUI and select the generated first-week source roots.",
            },
            {
                "action": "source_recall_smoke",
                "description": "Search for '今天完成了什么' or 'PSKA 当前边界' from the PSKA panel.",
            },
            {
                "action": "first_run_checklist",
                "description": "Mark runtime, recovery, writeback, selected scope, and rehearsal items in the Memory page.",
            },
        ],
    }
    if dry_run:
        return payload

    root.mkdir(parents=True, exist_ok=True)
    for item in directories:
        Path(item["absolute_path"]).mkdir(parents=True, exist_ok=True)
    file_results = []
    for name, path, content in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        if existed and not overwrite:
            status = "skipped_existing"
        else:
            path.write_text(content, encoding="utf-8")
            status = "updated" if existed else "created"
        file_results.append({"path": str(path), "template": name, "status": status})
    manifest = _manifest_payload(root, normalized_date, directories)
    manifest_path = root / MANIFEST_NAME
    manifest_existed = manifest_path.exists()
    if not manifest_existed or overwrite:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_status = "updated" if manifest_existed else "created"
    else:
        manifest_status = "skipped_existing"
    manifest_result = {"path": str(manifest_path), "template": MANIFEST_NAME, "status": manifest_status}
    payload["files"] = file_results + [manifest_result]
    payload["data_flow"]["writes_user_template_files"] = any(
        item["status"] in {"created", "updated"} for item in payload["files"]
    )
    return payload


def registration_roots(root: Path, *, register_all: bool = False) -> list[dict[str, Any]]:
    root = root.expanduser().resolve()
    selected = DIRECTORIES if register_all else tuple(spec for spec in DIRECTORIES if spec.first_week)
    return [_directory_payload(root, spec) for spec in selected]


def register_source_roots(
    api_base_url: str,
    roots: list[dict[str, Any]],
    *,
    scan: bool = False,
    timeout: float = 10.0,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for root in roots:
        try:
            registered = _post_json(
                api_base_url,
                "/api/sources/roots",
                {
                    "path": root["absolute_path"],
                    "kind": "local_folder",
                    "permission_mode": root["permission_mode"],
                    "label": root["label"],
                },
                timeout=timeout,
                urlopen_fn=urlopen_fn,
            )
            root_payload = registered.get("root") or {}
            result: dict[str, Any] = {
                "path": root["absolute_path"],
                "permission_mode": root["permission_mode"],
                "status": "registered",
                "root_id": root_payload.get("root_id"),
            }
            if scan and result["root_id"]:
                scan_result = _post_json(
                    api_base_url,
                    f"/api/sources/roots/{result['root_id']}/scan",
                    {"max_files": 200, "max_bytes": 1_000_000, "extractor": "auto"},
                    timeout=timeout,
                    urlopen_fn=urlopen_fn,
                )
                result["scan"] = scan_result.get("scan") or scan_result
            results.append(result)
        except Exception as exc:  # pragma: no cover - exact urllib errors are platform-dependent.
            results.append(
                {
                    "path": root["absolute_path"],
                    "permission_mode": root["permission_mode"],
                    "status": "error",
                    "error": str(exc),
                }
            )
    return results


def apply_registration_data_flow(
    payload: dict[str, Any],
    registration: list[dict[str, Any]],
    *,
    scan_requested: bool,
) -> dict[str, Any]:
    payload["data_flow"]["writes_source_registry"] = any(item.get("status") == "registered" for item in registration)
    payload["data_flow"]["scans_source_roots"] = scan_requested and any("scan" in item for item in registration)
    payload["data_flow"]["writes_source_files"] = False
    payload["data_flow"]["creates_review"] = False
    payload["data_flow"]["writes_memory_directly"] = False
    return payload


def _post_json(
    api_base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    urlopen_fn: Callable[..., Any],
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{api_base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen_fn(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _directory_payload(root: Path, spec: DogfoodDirectory) -> dict[str, Any]:
    return {
        "relative_path": spec.relative_path,
        "absolute_path": str(root / spec.relative_path),
        "label": spec.label,
        "permission_mode": spec.permission_mode,
        "first_week": spec.first_week,
    }


def _template_files(root: Path, date: str) -> list[tuple[str, Path, str]]:
    return [
        ("README.md", root / "README.md", _root_readme(date)),
        ("daily note", root / "daily" / f"{date}.md", _daily_template(date)),
        ("health log", root / "health" / f"{date}.md", _health_template(date)),
        ("PSKA project state", root / "projects" / "pska" / "project-state.md", _pska_project_state(date)),
        ("decision template", root / "decisions" / "README.md", _decision_readme()),
        ("creative README", root / "creative" / "README.md", _creative_readme()),
        ("private archive README", root / "private-archive" / "README.md", _private_archive_readme()),
        ("company README", root / "company" / "README.md", _company_readme()),
    ]


def _manifest_payload(root: Path, date: str, directories: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "pska.dogfood_workspace_manifest.v1",
        "root": str(root),
        "date": date,
        "directories": directories,
        "data_flow": {
            "source_of_truth": "user_owned_files",
            "writes_source_registry": False,
            "writes_memory_directly": False,
            "safe_to_rebuild_source_index": True,
        },
    }


def _root_readme(date: str) -> str:
    return f"""# PSKA Dogfood

创建日期：{date}

这个目录是第一用户自用资料根目录。它不是新的聊天前端，也不是自动记忆库。

使用原则：

- 先写原始记录，再让 PSKA 召回和整理。
- 私密内容默认只归档，不进入长期记忆。
- 决策和项目状态要保留来源。
- 值得长期影响回答的内容，先进入审核，再写入记忆。

建议第一周只注册这些目录：

- `daily/`
- `decisions/`
- `projects/pska/`
- `creative/`

在 Hermes WebUI 的 PSKA 面板里选中这些 source roots 后，先搜索：

```text
今天完成了什么
PSKA 当前边界
```
"""


def _daily_template(date: str) -> str:
    return f"""# {date}

## 今天发生

- 

## 承诺和待办

- 

## 身体和情绪

- 睡眠：
- 精力：
- 记忆：
- 脾气：
- 身体：

## 值得沉淀

- 

## 只归档，不写长期记忆

- 
"""


def _health_template(date: str) -> str:
    return f"""# {date} 健康和认知状态

这只是个人时间线记录，不是医学诊断。

## 指标

- 睡眠：好 / 一般 / 差
- 精力：好 / 一般 / 差
- 记忆：正常 / 有点卡 / 明显异常
- 脾气：平稳 / 易烦 / 明显失控
- 身体：

## 一句话备注

- 

## 需要以后回顾的变化

- 
"""


def _pska_project_state(date: str) -> str:
    return f"""# PSKA 项目状态

## 时间

{date}

## 当前目标

把 PSKA 做成个人外部认知系统：帮助长期保存、找回和审查资料、记忆、判断和创作上下文。

## 当前边界

- 日常入口是 Hermes WebUI。
- PSKA 没有独立前端。
- PSKA 负责资料范围、来源、记忆、审核、任务和追踪。
- MCP 使用 HTTP 连接。
- 长期记忆不能绕过审核边界。

## 最近进展

- 客户实操演示主片已生成。
- 演示包含对话工作台、资料范围、记忆审核、财报案例、小说续写和 Eidolia 创作画布。

## 近期问题

- dogfooding 要从每天真实记录开始，而不是继续堆功能。
- 需要证明 Source Recall 能找回这里的每日、决策和项目状态文件。

## 下一步最小动作

- 在 Hermes WebUI 里选择第一周 source roots。
- 搜索“PSKA 当前边界”和“今天完成了什么”。
- 从一条来源证据起草一条记忆候选，但不要直接写长期记忆。
"""


def _decision_readme() -> str:
    return """# 决策记录

每条重要决策建议单独建一个 Markdown 文件。

模板：

```markdown
# 决策：标题

## 时间

## 背景

## 备选项

## 当前判断

## 证据

## 风险

## 以后如何验证
```
"""


def _creative_readme() -> str:
    return """# 创作资料

这里保存可以被 PSKA 和 Eidolia 找回的创作设定、母题、续写问题和读者反馈。

注意：

- thought 和 artifact 仍然是 Eidolia 的主要画布节点。
- PSKA 只负责来源、记忆候选和追踪。
- 私密人生素材默认先抽象成母题，不要无关暴露具体人物细节。
"""


def _private_archive_readme() -> str:
    return """# 私密档案

这里保存只在明确要求时才召回的个人资料。

默认原则：

- 只归档，不自动写长期记忆。
- 不在普通技术、公司、产品问答里主动使用。
- 需要使用时先列来源和使用理由。
"""


def _company_readme() -> str:
    return """# 公司资料

这里保存公司介绍、产品线、项目材料和对外文本。

默认建议使用 read_only 注册；如果确实要让 PSKA 添加标签或评论，再改为 sidecar_write。
"""


def _validate_date(value: str) -> str:
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"invalid --date, expected YYYY-MM-DD: {value}") from exc
    return parsed.isoformat()


def _today() -> str:
    return dt.date.today().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
