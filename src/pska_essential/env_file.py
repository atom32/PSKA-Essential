from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Sequence


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def env_file_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--env-file",
        default=os.getenv("PSKA_ENV_FILE", ""),
        help="Load explicit PSKA environment configuration before startup.",
    )
    return parser


def preload_env_file(argv: Sequence[str] | None = None) -> argparse.ArgumentParser:
    parser = env_file_arg_parser()
    cli_args = list(sys.argv[1:] if argv is None else argv)
    if any(arg in {"-h", "--help"} for arg in cli_args):
        return parser
    args, _ = parser.parse_known_args(cli_args)
    if args.env_file:
        load_env_file(args.env_file)
    return parser


def load_env_file(path: str | os.PathLike[str], *, override: bool = False) -> dict[str, str]:
    env_path = Path(path).expanduser()
    if not env_path.is_file():
        raise FileNotFoundError(f"env file not found: {env_path}")

    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid env file line {line_number}: expected KEY=VALUE")
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _ENV_NAME.match(name):
            raise ValueError(f"invalid env file line {line_number}: invalid variable name {name!r}")
        value = _parse_value(raw_value)
        if override or name not in os.environ:
            os.environ[name] = value
        loaded[name] = value
    return loaded


def _parse_value(raw_value: str) -> str:
    value = _strip_inline_comment(raw_value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _strip_inline_comment(value: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index]
    return value
