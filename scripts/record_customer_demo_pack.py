#!/usr/bin/env python3
"""Record all customer-facing Hermes WebUI demo clips, then build the pack."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / "scripts" / "record_hermes_pska_extension_demo.cjs"
CUSTOMER_BUILDER = ROOT / "scripts" / "build_customer_demo_video.py"
CUSTOMER_PACKAGER = ROOT / "scripts" / "package_customer_demo_assets.py"
CUSTOMER_VERIFIER = ROOT / "scripts" / "verify_hermes_extension_demo_pack.py"
DEFAULT_PLAYWRIGHT_NODE_PATHS = [
    Path("/tmp/pska-playwright-recorder/node_modules"),
    Path("/tmp/pska-playwright/node_modules"),
]


@dataclass(frozen=True)
class RecordingStep:
    title: str
    command: list[str]


@dataclass(frozen=True)
class DemoRecording:
    title: str
    case_id: str
    output_basename: str | None
    dwell_scale: str
    wait_for_llm_ms: str
    tail_pad_ms: str | None = None


RECORDINGS = [
    DemoRecording(
        title="核心长版",
        case_id="core",
        output_basename="hermes_pska_extension_demo_long",
        dwell_scale="4",
        wait_for_llm_ms="75000",
        tail_pad_ms="15000",
    ),
    DemoRecording(
        title="财报调研案例",
        case_id="finance_report_research",
        output_basename=None,
        dwell_scale="2.5",
        wait_for_llm_ms="30000",
    ),
    DemoRecording(
        title="网文续写和创作画布案例",
        case_id="webnovel_author",
        output_basename=None,
        dwell_scale="2.5",
        wait_for_llm_ms="30000",
    ),
]


def main() -> int:
    args = parse_args(sys.argv[1:])
    env = build_env(args)
    steps = build_steps(args)
    if args.dry_run:
        for step in steps:
            print(f"[dry-run] {step.title}")
            print(format_command(step.command))
        return 0
    if args.preflight_only:
        run_preflight(args, env)
        print("preflight passed")
        return 0
    if not args.skip_preflight:
        run_preflight(args, env)
    for step in steps:
        print(f"\n==> {step.title}")
        subprocess.run(step.command, cwd=ROOT, env=env, check=True)
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record core, finance, and Eidolia customer demo clips, then build the delivery pack.",
    )
    parser.add_argument("--base-url", default=os.environ.get("HERMES_WEBUI_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument(
        "--pska-api-base-url",
        default=os.environ.get("PSKA_PRODUCT_API_BASE_URL", "http://127.0.0.1:8765"),
    )
    parser.add_argument("--eidolia-base-url", default=os.environ.get("EIDOLIA_BASE_URL", "http://127.0.0.1:8797"))
    default_node = os.environ.get("NODE_PATH") or default_node_path()
    parser.add_argument(
        "--playwright-module",
        default=os.environ.get("PSKA_PLAYWRIGHT_MODULE") or default_playwright_module(default_node),
    )
    parser.add_argument("--node-path", default=default_node)
    parser.add_argument("--storage-state", default=os.environ.get("HERMES_WEBUI_STORAGE_STATE"))
    parser.add_argument("--password", default=os.environ.get("HERMES_WEBUI_PASSWORD"))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--slow-mo", default=None)
    parser.add_argument("--keep-raw", action="store_true")
    parser.add_argument("--no-seed-demo-data", action="store_true")
    parser.add_argument("--no-seed-eidolia-data", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def default_node_path() -> str | None:
    for path in DEFAULT_PLAYWRIGHT_NODE_PATHS:
        if path.exists():
            return str(path)
    return None


def default_playwright_module(node_path: str | None) -> str:
    if node_path:
        root = Path(node_path)
        if (root / "playwright").exists():
            return "playwright"
        if (root / "playwright-core").exists():
            return "playwright-core"
    return "playwright"


def build_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    if args.node_path:
        env["NODE_PATH"] = str(args.node_path)
    if args.password:
        env["HERMES_WEBUI_PASSWORD"] = str(args.password)
    if args.storage_state:
        env["HERMES_WEBUI_STORAGE_STATE"] = str(args.storage_state)
    return env


def run_preflight(args: argparse.Namespace, env: dict[str, str]) -> None:
    failures: list[str] = []
    warnings: list[str] = []

    for script in [RECORDER, CUSTOMER_BUILDER, CUSTOMER_PACKAGER, CUSTOMER_VERIFIER]:
        if not script.exists():
            failures.append(f"missing script: {script}")

    if not shutil.which("node"):
        failures.append("missing Node.js: install node or add it to PATH")
    if not shutil.which("ffmpeg"):
        failures.append("missing ffmpeg: install ffmpeg or add it to PATH")
    if not shutil.which("ffprobe"):
        failures.append("missing ffprobe: install ffmpeg with ffprobe or add it to PATH")
    if shutil.which("ffmpeg"):
        if not ffmpeg_has_filter("overlay"):
            failures.append("ffmpeg is missing the overlay filter required for hard-subtitled delivery video")
        if not ffmpeg_has_encoder("libx264"):
            failures.append("ffmpeg is missing the libx264 encoder required for MP4 delivery videos")
    if not python_module_available("PIL"):
        failures.append("missing Pillow: install pillow for hard-subtitled delivery video generation")

    playwright_module = args.playwright_module or "playwright"
    node_path = str(args.node_path or "").strip()
    if node_path and not Path(node_path).exists():
        warnings.append(f"NODE_PATH does not exist yet: {node_path}")
    if shutil.which("node") and not can_resolve_node_module(playwright_module, env):
        failures.append(
            f"cannot resolve Playwright module '{playwright_module}'; set NODE_PATH or pass --playwright-module"
        )

    if not args.password and not args.storage_state:
        warnings.append("no Hermes password or storage state provided; this only works when WebUI auth is disabled")

    check_http(args.base_url.rstrip("/") + "/health", "Hermes WebUI", failures)
    check_http(args.pska_api_base_url.rstrip("/") + "/api/health", "PSKA API", failures)
    if not args.no_seed_eidolia_data:
        check_http(args.eidolia_base_url.rstrip("/") + "/api/agent/health", "Eidolia", failures)

    for warning in warnings:
        print(f"preflight warning: {warning}", file=sys.stderr)
    if failures:
        print("preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise SystemExit(2)


def can_resolve_node_module(module_name: str, env: dict[str, str]) -> bool:
    result = subprocess.run(
        ["node", "-e", "require.resolve(process.argv[1])", module_name],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def python_module_available(module_name: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ffmpeg_has_filter(filter_name: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0 and re_search_ffmpeg_name(result.stdout, filter_name)


def ffmpeg_has_encoder(encoder_name: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0 and re_search_ffmpeg_name(result.stdout, encoder_name)


def re_search_ffmpeg_name(text: str, name: str) -> bool:
    return any(line.split()[-1:] == [name] or f" {name} " in line for line in text.splitlines())


def check_http(url: str, label: str, failures: list[str]) -> None:
    try:
        with urlopen(url, timeout=3) as response:
            if response.status >= 400:
                failures.append(f"{label} returned HTTP {response.status}: {url}")
    except (OSError, URLError) as error:
        failures.append(f"{label} is not reachable at {url}: {error}")


def build_steps(args: argparse.Namespace) -> list[RecordingStep]:
    steps = [RecordingStep(recording.title, build_recording_command(recording, args)) for recording in RECORDINGS]
    steps.extend(
        [
            RecordingStep("合成客户主片", [sys.executable, str(CUSTOMER_BUILDER)]),
            RecordingStep("打包客户交付件", [sys.executable, str(CUSTOMER_PACKAGER)]),
            RecordingStep(
                "验证客户演示包",
                [
                    sys.executable,
                    str(CUSTOMER_VERIFIER),
                    "--all-videos",
                    "--require-video",
                    "--require-delivery-pack",
                ],
            ),
        ]
    )
    return steps


def build_recording_command(recording: DemoRecording, args: argparse.Namespace) -> list[str]:
    command = [
        "node",
        str(RECORDER),
        "--case",
        recording.case_id,
        "--detailed",
        "--dwell-scale",
        recording.dwell_scale,
        "--wait-for-llm-ms",
        recording.wait_for_llm_ms,
        "--base-url",
        str(args.base_url),
        "--pska-api-base-url",
        str(args.pska_api_base_url),
        "--eidolia-base-url",
        str(args.eidolia_base_url),
    ]
    if recording.output_basename:
        command.extend(["--output-basename", recording.output_basename])
    if recording.tail_pad_ms:
        command.extend(["--tail-pad-ms", recording.tail_pad_ms])
    if args.playwright_module:
        command.extend(["--playwright-module", str(args.playwright_module)])
    if args.storage_state:
        command.extend(["--storage-state", str(args.storage_state)])
    if args.headed:
        command.append("--headed")
    if args.slow_mo:
        command.extend(["--slow-mo", str(args.slow_mo)])
    if args.keep_raw:
        command.append("--keep-raw")
    if args.no_seed_demo_data:
        command.append("--no-seed-demo-data")
    if args.no_seed_eidolia_data:
        command.append("--no-seed-eidolia-data")
    return command


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


if __name__ == "__main__":
    raise SystemExit(main())
