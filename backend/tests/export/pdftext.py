"""Kleiner PDF-Textleser für die Tests (im Image gibt es keinen PDF-Leser).

Versteht genau das, was reportlab schreibt: Objekte mit (Flate-)Streams, Schriften mit
`/ToUnicode`-Tabelle (eingebettete TrueType-Untermengen) oder Standardschriften, und Text in
`Tj`/`TJ`. Liefert je Seite den Text; Zeilenwechsel bei `Td`, `TD`, `Tm`, `T*`, `ET`.
"""

import base64
import re
import zlib
from dataclasses import dataclass

_OBJECT = re.compile(rb"(\d+) 0 obj(.*?)endobj", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)
_TOKEN = re.compile(
    rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s/\[\]()<>]+|[^\s/\[\]()<>]+", re.S
)


@dataclass
class PdfDocument:
    pages: list[str]
    fonts: list[str]
    embedded_fonts: int

    @property
    def text(self) -> str:
        return "\n".join(self.pages)


def _literal(token: bytes) -> bytes:
    body = token[1:-1]
    out = bytearray()
    i = 0
    escapes = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}
    while i < len(body):
        char = body[i : i + 1]
        if char == b"\\":
            nxt = body[i + 1 : i + 2]
            if nxt in escapes:
                out += escapes[nxt]
                i += 2
            elif nxt.isdigit():
                digits = re.match(rb"[0-7]{1,3}", body[i + 1 : i + 4])
                assert digits is not None
                out.append(int(digits.group(), 8))
                i += 1 + len(digits.group())
            else:
                out += nxt
                i += 2
        else:
            out += char
            i += 1
    return bytes(out)


def _stream(body: bytes) -> bytes | None:
    match = _STREAM.search(body)
    if match is None:
        return None
    data = match.group(1)
    head = body[: match.start()]
    if b"/ASCII85Decode" in head:
        data = base64.a85decode(data.strip().removesuffix(b"~>"))
    if b"/FlateDecode" in head:
        data = zlib.decompress(data)
    return data


def _cmap(data: bytes) -> dict[int, str]:
    mapping = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for source, target in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            text = bytes.fromhex(target.decode()).decode("utf-16-be")
            if text != "\x00":
                mapping[int(source, 16)] = text
    return mapping


def read_pdf(content: bytes) -> PdfDocument:
    assert content.startswith(b"%PDF-"), "keine PDF-Datei"
    assert content.rstrip().endswith(b"%%EOF"), "PDF unvollständig"
    objects = {int(number): body for number, body in _OBJECT.findall(content)}

    # Schriftname im Inhalt (/F1, /F2+0) → Zuordnung Code → Zeichen (None: Latin-1).
    fonts: dict[str, dict[int, str] | None] = {}
    base_fonts = []
    for body in objects.values():
        if b"/Type /Font" not in body:
            continue
        name = re.search(rb"/Name /(\S+)", body)
        base = re.search(rb"/BaseFont /(\S+)", body)
        if base:
            base_fonts.append(base.group(1).decode())
        if name is None:
            continue
        unicode_ref = re.search(rb"/ToUnicode (\d+) 0 R", body)
        mapping = None
        if unicode_ref:
            data = _stream(objects[int(unicode_ref.group(1))])
            mapping = _cmap(data or b"")
        fonts[name.group(1).decode()] = mapping

    # Seiten in Reihenfolge des Seitenbaums: /Kids der Wurzel.
    pages_root = next(body for body in objects.values() if b"/Type /Pages" in body)
    kids = [
        int(n)
        for n in re.findall(
            rb"(\d+) 0 R", re.search(rb"/Kids \[(.*?)\]", pages_root, re.S).group(1)
        )
    ]  # type: ignore[union-attr]
    texts = []
    for kid in kids:
        page = objects[kid]
        refs = re.search(rb"/Contents (\d+) 0 R", page)
        data = _stream(objects[int(refs.group(1))]) if refs else b""
        texts.append(_page_text(data or b"", fonts))
    embedded = sum(1 for body in objects.values() if b"/FontFile2" in body)
    return PdfDocument(pages=texts, fonts=base_fonts, embedded_fonts=embedded)


def _decode(raw: bytes, mapping: dict[int, str] | None) -> str:
    if mapping is None:
        return raw.decode("latin-1")
    return "".join(mapping.get(byte, "�") for byte in raw)


def _page_text(data: bytes, fonts: dict[str, dict[int, str] | None]) -> str:
    out: list[str] = []
    stack: list[bytes] = []
    mapping: dict[int, str] | None = None
    for token in _TOKEN.findall(data):
        if token in (b"Td", b"TD", b"Tm", b"T*", b"ET"):
            out.append("\n")
            stack.clear()
        elif token == b"Tf":
            name = stack[-2].decode()[1:] if len(stack) >= 2 else ""
            mapping = fonts.get(name)
            stack.clear()
        elif token == b"Tj" or token == b"'":
            if stack and stack[-1].startswith(b"("):
                out.append(_decode(_literal(stack[-1]), mapping))
            stack.clear()
        elif token == b"TJ":
            for item in stack:
                if item.startswith(b"("):
                    out.append(_decode(_literal(item), mapping))
            stack.clear()
        elif token == b"[":
            stack.clear()
        elif token == b"]":
            pass
        else:
            stack.append(token)
    lines = "".join(out).split("\n")
    return "\n".join(line.strip() for line in lines if line.strip())
