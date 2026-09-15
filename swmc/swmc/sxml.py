"""A tiny XML reader/writer for the Stormworks microprocessor format.

``xml.etree.ElementTree`` cannot be used here.  Per the XML spec a conforming
parser normalises literal newlines and tabs inside attribute values to spaces,
which silently mangles the ``script="..."`` attribute of a Lua component (the
whole script collapses onto one line).  The game itself writes those newlines
raw, so we parse and emit them raw too.

The format we have to handle is machine generated and very small: an XML
declaration, elements, double-quoted attributes, no text nodes, no comments,
no CDATA, no namespaces.  Parsing it directly is both safer and simpler than
fighting a general-purpose parser.
"""

from __future__ import annotations

import re
from typing import Iterator, Optional, Tuple, overload

__all__ = ["Element", "parse", "parse_file", "tostring", "escape_attr",
           "ParseError"]

_DECL_RE = re.compile(r"<\?xml[^>]*\?>\s*", re.S)
_TAG_OPEN_RE = re.compile(r"<(/?)([A-Za-z_][\w.\-]*)")
_ATTR_RE = re.compile(r'\s*([A-Za-z_][\w.\-]*)\s*=\s*"([^"]*)"')

# Only these five entities appear in the game's output.  Numeric escapes are
# accepted on input for robustness but are never emitted.
_UNESCAPE = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
_ENTITY_RE = re.compile(r"&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);")


class ParseError(ValueError):
    """Raised when the document is not the shape we expect."""


def _unescape(text: str) -> str:
    if "&" not in text:
        return text

    def sub(m):
        body = m.group(1)
        if body.startswith("#x"):
            return chr(int(body[2:], 16))
        if body.startswith("#"):
            return chr(int(body[1:]))
        if body in _UNESCAPE:
            return _UNESCAPE[body]
        return m.group(0)

    return _ENTITY_RE.sub(sub, text)


def escape_attr(text: str) -> str:
    # Newlines and tabs stay literal: that is what the game writes and what
    # keeps Lua scripts intact.
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class Element:
    """One XML element: a tag, an ordered attribute dict and ordered children."""

    __slots__ = ("tag", "attrib", "children")

    def __init__(self, tag: str, attrib: "dict[str, str] | None" = None,
                 children: "list[Element] | None" = None) -> None:
        self.tag = tag
        self.attrib = dict(attrib) if attrib else {}
        self.children = list(children) if children else []

    # -- container protocol -------------------------------------------------
    def __iter__(self) -> "Iterator[Element]":
        return iter(self.children)

    def __len__(self) -> int:
        return len(self.children)

    def __getitem__(self, i: int) -> "Element":
        return self.children[i]

    def __repr__(self) -> str:
        return "<Element %s %r (%d children)>" % (self.tag, self.attrib, len(self.children))

    # -- lookups ------------------------------------------------------------
    def find(self, tag: str) -> "Element | None":
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def findall(self, tag: str) -> "list[Element]":
        return [c for c in self.children if c.tag == tag]

    @overload
    def get(self, key: str) -> Optional[str]: ...

    @overload
    def get(self, key: str, default: str) -> str: ...

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.attrib.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.attrib[key] = value

    def pop(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.attrib.pop(key, default)

    def iter(self, tag: Optional[str] = None) -> "Iterator[Element]":
        if tag is None or self.tag == tag:
            yield self
        for c in self.children:
            yield from c.iter(tag)

    # -- mutation -----------------------------------------------------------
    def append(self, child: "Element") -> None:
        self.children.append(child)

    def insert(self, index: int, child: "Element") -> None:
        self.children.insert(index, child)

    def remove(self, child: "Element") -> None:
        self.children.remove(child)

    def clear_children(self) -> None:
        self.children = []

    def ensure(self, tag: str) -> "Element":
        """Return the first child with ``tag``, creating it if absent."""
        c = self.find(tag)
        if c is None:
            c = Element(tag)
            self.children.append(c)
        return c

    def copy(self) -> "Element":
        return Element(self.tag, dict(self.attrib), [c.copy() for c in self.children])


def parse(text: str) -> "Tuple[Element, str, str]":
    """Parse a document string and return ``(root, declaration, trailer)``."""
    decl = ""
    m = _DECL_RE.match(text)
    if m:
        decl = m.group(0)
        pos = m.end()
    else:
        pos = 0

    stack: "list[Element]" = []
    root: "Element | None" = None
    n = len(text)
    while pos < n:
        lt = text.find("<", pos)
        if lt < 0:
            break
        if text.startswith("<!--", lt):
            end = text.find("-->", lt)
            if end < 0:
                raise ParseError("unterminated comment at %d" % lt)
            pos = end + 3
            continue
        m = _TAG_OPEN_RE.match(text, lt)
        if not m:
            raise ParseError("malformed tag at offset %d: %r" % (lt, text[lt:lt + 40]))
        closing, tag = m.group(1), m.group(2)
        pos = m.end()

        if closing:
            gt = text.find(">", pos)
            if gt < 0:
                raise ParseError("unterminated close tag %r" % tag)
            if not stack or stack[-1].tag != tag:
                open_tag = stack[-1].tag if stack else None
                raise ParseError("</%s> closes <%s>" % (tag, open_tag))
            stack.pop()
            pos = gt + 1
            continue

        attrib = {}
        while True:
            am = _ATTR_RE.match(text, pos)
            if not am:
                break
            attrib[am.group(1)] = _unescape(am.group(2))
            pos = am.end()

        while pos < n and text[pos] in " \t\r\n":
            pos += 1
        if text.startswith("/>", pos):
            self_close = True
            pos += 2
        elif pos < n and text[pos] == ">":
            self_close = False
            pos += 1
        else:
            raise ParseError("malformed attributes in <%s> near offset %d" % (tag, pos))

        el = Element(tag, attrib)
        if stack:
            stack[-1].append(el)
        elif root is None:
            root = el
        else:
            raise ParseError("multiple root elements (second is <%s>)" % tag)
        if not self_close:
            stack.append(el)

    if stack:
        raise ParseError("unclosed element <%s>" % stack[-1].tag)
    if root is None:
        raise ParseError("no root element")
    return root, decl, ""


def parse_file(path: str) -> "Tuple[Element, str, str]":
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return parse(fh.read())


def tostring(root: "Element",
             decl: str = '<?xml version="1.0" encoding="UTF-8"?>\n',
             indent: str = "\t", trailing_newlines: int = 2) -> str:
    """Serialise back out in the game's own style.

    Self-closing tags are written ``<tag a="1"/>`` with no space before the
    slash, indentation is tabs and lines end with ``\\n`` -- matching what
    Stormworks writes, so saved files stay diff-clean against the game's own.
    """
    out = [decl] if decl else []

    def emit(el, depth):
        pad = indent * depth
        attrs = "".join(' %s="%s"' % (k, escape_attr(v)) for k, v in el.attrib.items())
        if el.children:
            out.append("%s<%s%s>\n" % (pad, el.tag, attrs))
            for c in el.children:
                emit(c, depth + 1)
            out.append("%s</%s>\n" % (pad, el.tag))
        else:
            out.append("%s<%s%s/>\n" % (pad, el.tag, attrs))

    emit(root, 0)
    text = "".join(out)
    if trailing_newlines > 1:
        text += "\n" * (trailing_newlines - 1)
    return text
