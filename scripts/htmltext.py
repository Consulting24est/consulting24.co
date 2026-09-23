#!/usr/bin/env python3
"""
htmltext.py — entity-safe text helpers shared by the page generators.

Why this exists: several generators read text back out of already-rendered HTML
(<h1>, <title>, <meta name="description">). That text is escaped, so escaping it
a second time put the entity itself on the page, e.g. "Panama&#x27;s" instead of
"Panama's" and "Costs &amp; Process" instead of "Costs & Process".

Rule: never escape a string you did not create. Run it through plain() first.
plain() strips every layer of escaping, so esc_text(plain(x)) is stable no matter
how many generate/read-back/regenerate cycles a page has been through.

  esc_text  -> for text nodes   (escapes & < >, leaves quotes readable)
  esc_attr  -> for attributes   (also escapes " and ')
  plain     -> for JSON-LD and JSON payloads, which are never entity-decoded
"""
from __future__ import annotations
import re
from html import escape as _escape
from html.entities import html5

_REF = re.compile(r"&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});")


def _decode(m: re.Match) -> str:
    body = m.group(1)
    if body[0] == "#":
        try:
            cp = int(body[2:], 16) if body[1] in "xX" else int(body[1:])
        except ValueError:
            return m.group(0)
        return chr(cp) if 0 < cp < 0x110000 else m.group(0)
    return html5.get(body + ";", m.group(0))


def plain(s) -> str:
    """Decode character references repeatedly, so any depth of escaping flattens.

    Only full "&name;" / "&#nnn;" forms are decoded, so "AT&T" and a stray "&"
    survive untouched. Decoding only ever shortens the string, so this ends.
    """
    s = "" if s is None else str(s)
    while True:
        out = _REF.sub(_decode, s)
        if out == s:
            return s
        s = out


def esc_text(s) -> str:
    """Escape for a text node, unescaping first so nothing is escaped twice."""
    return _escape(plain(s), quote=False)


def esc_attr(s) -> str:
    """Escape for a double-quoted attribute value, unescaping first."""
    return _escape(plain(s), quote=True)
