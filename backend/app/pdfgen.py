"""Tiny dependency-free PDF table writer (A4 landscape, Helvetica)."""


def _lat(s) -> str:
    return str(s).encode("latin-1", "replace").decode("latin-1")


def _esc(s) -> str:
    return _lat(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\r", " ").replace("\n", " ")


def _clip(text: str, width: float, size: float = 8) -> str:
    maxc = max(1, int(width / (size * 0.52)))
    return text if len(text) <= maxc else text[:max(1, maxc - 3)] + "..."


def table_pdf(title, headers, rows, subtitle="") -> bytes:
    W, H, M, SIZE, LEAD = 842, 595, 36, 8, 13
    headers = [str(h) for h in headers]
    rows = [["" if c is None else str(c) for c in r] for r in rows]
    n = len(headers)
    lens = [min(40, max(6, max([len(headers[i])] + [len(r[i]) for r in rows]))) for i in range(n)]
    widths = [(W - 2 * M) * l / sum(lens) for l in lens]
    per_page = int((H - 2 * M - 60) / LEAD)
    chunks = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{5 + 2 * i} 0 R" for i in range(len(chunks))), len(chunks))).encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    for pi, chunk in enumerate(chunks):
        out = []

        def text(x, y, s, font="F1", size=SIZE):
            out.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({_esc(s)}) Tj ET")

        y = H - M
        text(M, y, title, "F2", 14)
        y -= 16
        if subtitle:
            text(M, y, subtitle)
            y -= 12
        y -= 8
        x = M
        for i, h in enumerate(headers):
            text(x, y, _clip(h, widths[i] - 6), "F2")
            x += widths[i]
        out.append(f"{M} {y - 4:.1f} m {W - M} {y - 4:.1f} l S")
        y -= LEAD
        for r in chunk:
            x = M
            for i, c in enumerate(r):
                text(x, y, _clip(c, widths[i] - 6))
                x += widths[i]
            y -= LEAD
        text(W - M - 60, M - 14, f"Page {pi + 1} of {len(chunks)}")
        stream = "\n".join(out).encode("latin-1")
        objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>"
                     % (W, H, 6 + 2 * pi)).encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    buf, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(buf)
