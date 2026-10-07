#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

from md_codec import html_to_md, md_to_html  # noqa: E402


class MdCodecTests(unittest.TestCase):
    def test_headings_and_emphasis(self):
        html = md_to_html("# Title\n\nhello **bold** and *em*\n")
        self.assertIn("<h1>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>em</em>", html)
        md = html_to_md(html)
        self.assertIn("# Title", md)
        self.assertIn("**bold**", md)

    def test_table_roundtrip(self):
        src = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        html = md_to_html(src)
        self.assertIn("<table>", html)
        self.assertIn("<th>", html)
        md = html_to_md(html)
        self.assertIn("| A | B |", md)
        self.assertIn("| 1 | 2 |", md)

    def test_task_list(self):
        html = md_to_html("- [ ] todo\n- [x] done\n")
        self.assertIn('type="checkbox"', html)
        self.assertIn("checked", html)
        md = html_to_md(html)
        self.assertIn("- [ ]", md)
        self.assertIn("- [x]", md)

    def test_footnote_defs(self):
        src = "See note[^f1].\n\n[^f1]: body text\n"
        html = md_to_html(src)
        self.assertIn('data-fn="f1"', html)
        self.assertIn("footnotes", html)
        md = html_to_md(html)
        self.assertIn("[^f1]", md)
        self.assertIn("[^f1]: body text", md)

    def test_image_and_link(self):
        html = md_to_html("[x](http://a) ![y](img.png)\n")
        self.assertIn('<a href="http://a">', html)
        self.assertIn('<img src="img.png"', html)
        md = html_to_md(html)
        self.assertIn("[x](http://a)", md)
        self.assertIn("![y](img.png)", md)


if __name__ == "__main__":
    unittest.main()
