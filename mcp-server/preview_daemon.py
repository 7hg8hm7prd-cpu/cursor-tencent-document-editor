#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detachable present/edit HTTP daemon for md/html."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from preview_server import DEFAULT_PORT, serve_forever  # noqa: E402


def main() -> int:
    port = int(os.environ.get("DOCUMENT_PREVIEW_PORT", DEFAULT_PORT) or DEFAULT_PORT)
    try:
        serve_forever(port)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
