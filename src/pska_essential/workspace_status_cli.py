from __future__ import annotations

import argparse
import json

from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable
from pska_essential.env_file import preload_env_file
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.workspace_status import build_workspace_status


def main(argv: list[str] | None = None) -> int:
    env_parser = preload_env_file(argv)
    parser = argparse.ArgumentParser(description="Print PSKA workspace status and next actions.", parents=[env_parser])
    parser.add_argument("--dataset-page-size", type=int, default=30)
    parser.add_argument("--review-limit", type=int, default=50)
    parser.add_argument("--workflow-limit", type=int, default=50)
    args = parser.parse_args(argv)

    status = build_workspace_status(
        service=build_service_from_env(),
        gateway=build_kb_gateway_from_env(),
        dataset_page_size=args.dataset_page_size,
        review_limit=args.review_limit,
        workflow_limit=args.workflow_limit,
    )
    print(json.dumps(to_jsonable(status), ensure_ascii=False, indent=2))
    return 2 if status.get("status") == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
