#!/usr/bin/env python3
"""Record all customer-facing Hermes WebUI demo clips, then build the pack."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / "scripts" / "record_hermes_pska_extension_demo.cjs"
CUSTOMER_BUILDER = ROOT / "scripts" / "build_customer_demo_video.py"
CUSTOMER_PACKAGER = ROOT / "scripts" / "package_customer_demo_assets.py"
CUSTOMER_VERIFIER = ROOT / "scripts" / "verify_hermes_extension_demo_pack.py"
DEFAULT_PLAYWRIGHT_NODE_PATH = Path("/tmp/pska-playwright-recorder/node_modules")


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


RECORDINGS = [
    DemoRecording(
        title="核心长版",
        case_id="core",
        output_basename="hermes_pska_extension_demo_long",
        dwell_scale="4",
        wait_for_llm_ms="75000",
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
    parser.add_argument("--playwright-module", default=os.environ.get("PSKA_PLAYWRIGHT_MODULE"))
    parser.add_argument("--node-path", default=os.environ.get("NODE_PATH") or default_node_path())
    parser.add_argument("--storage-state", default=os.environ.get("HERMES_WEBUI_STORAGE_STATE"))
    parser.add_argument("--password", default=os.environ.get("HERMES_WEBUI_PASSWORD"))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--slow-mo", default=None)
    parser.add_argument("--keep-raw", action="store_true")
    parser.add_argument("--no-seed-demo-data", action="store_true")
    parser.add_argument("--no-seed-eidolia-data", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def default_node_path() -> str | None:
    return str(DEFAULT_PLAYWRIGHT_NODE_PATH) if DEFAULT_PLAYWRIGHT_NODE_PATH.exists() else None


def build_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    if args.node_path:
        env["NODE_PATH"] = str(args.node_path)
    if args.password:
        env["HERMES_WEBUI_PASSWORD"] = str(args.password)
    if args.storage_state:
        env["HERMES_WEBUI_STORAGE_STATE"] = str(args.storage_state)
    return env


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
