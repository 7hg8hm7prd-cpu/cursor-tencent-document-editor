#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry for editor-sdk-bridge / manual smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bridge import (  # noqa: E402
    document_convert,
    document_edit,
    document_present,
    document_preview,
    sdk_status,
)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="document-editor-cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("present")
    p.add_argument("file_path")
    p.add_argument("--no-open", action="store_true")
    p.add_argument(
        "--target",
        choices=["cursor", "browser", "auto"],
        default="cursor",
        help="Open in Cursor Simple Browser (default) or system browser",
    )

    p = sub.add_parser("preview")
    p.add_argument("file_path")
    p.add_argument("--format", default=None)

    p = sub.add_parser("edit")
    p.add_argument("file_path")
    p.add_argument("--format", default=None)
    p.add_argument("--content-format", default=None)
    p.add_argument("--content", default=None)
    p.add_argument("--stdin", action="store_true")

    p = sub.add_parser("convert")
    p.add_argument("file_path")
    p.add_argument("--to", dest="to_format", required=True)
    p.add_argument("--output", default=None)
    p.add_argument("--from-format", default=None)

    sub.add_parser("status")

    args = ap.parse_args(argv)

    if args.cmd == "present":
        _print(
            document_present(
                args.file_path,
                open_browser=not args.no_open,
                target=args.target,
            )
        )
        return 0
    if args.cmd == "preview":
        _print(document_preview(args.file_path, args.format))
        return 0
    if args.cmd == "edit":
        content = args.content
        if args.stdin or content is None:
            content = sys.stdin.read()
        _print(document_edit(args.file_path, content, args.format, args.content_format))
        return 0
    if args.cmd == "convert":
        _print(
            document_convert(
                args.file_path,
                args.to_format,
                args.output,
                args.from_format,
            )
        )
        return 0
    if args.cmd == "status":
        _print(sdk_status())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
