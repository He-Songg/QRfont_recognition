import argparse
import sys
from pathlib import Path
from datetime import datetime
import re


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Try to extract text directly from the PDF using PyMuPDF.
    Returns a string with original line breaks preserved if text exists; otherwise empty string.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        # PyMuPDF not available
        return ""

    text_pages: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                # 'text' format keeps line breaks reasonably well
                page_text = page.get_text("text")
                # Normalize whitespace but keep '+', since '+' is the paragraph delimiter
                page_text = page_text.replace("\r\n", "\n").replace("\r", "\n")
                page_text = re.sub(r"\s+", "", page_text).strip()
                if page_text:
                    text_pages.append(page_text)
    except Exception:
        return ""

    # Concatenate all pages with a space; then split paragraphs by '+' and remove it from output
    all_text = " ".join(text_pages).strip()
    if not all_text:
        return ""
    parts = re.split(r"\s*\+\s*", all_text)
    parts = [p.strip() for p in parts if p and p.strip()]
    return "\n".join(parts)


def decode_qr_from_pdf(pdf_path: Path, zoom: float = 4.0) -> str:
    """
    Render each PDF page to an image and detect multiple QR codes.
    Each QR encodes a single character. We reconstruct lines by clustering by Y.
    """
    import statistics

    try:
        import fitz  # PyMuPDF
        import numpy as np
        import cv2
    except Exception as e:
        raise RuntimeError(
            "需要安装依赖：PyMuPDF、opencv-python、numpy。请先安装后重试。"
        ) from e

    detector = cv2.QRCodeDetector()
    lines_all_pages: list[list[tuple[float, float, str, float]]] = (
        []
    )  # per page lines after clustering

    with fitz.open(pdf_path) as doc:
        for page in doc:
            # Render page
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            n_channels = pix.n  # 3 for RGB
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.h, pix.w, n_channels
            )
            # Convert to BGR for OpenCV if needed (PyMuPDF returns RGB). OpenCV expects BGR, but for QR it's fine either way.
            img_bgr = img[:, :, ::-1].copy() if n_channels == 3 else img

            # Try multi decode (OpenCV versions differ in return signature)
            decoded_info = []
            points = None
            try:
                result = detector.detectAndDecodeMulti(img_bgr)
                # Handle different return formats across OpenCV versions
                if isinstance(result, tuple):
                    if len(result) == 4:
                        retval, infos, pts, _ = result
                        if retval and infos is not None and pts is not None:
                            decoded_info = list(infos)
                            points = pts
                    elif len(result) == 3:
                        infos, pts, _ = result
                        if infos is not None and pts is not None:
                            decoded_info = list(infos)
                            points = pts
            except Exception:
                decoded_info = []
                points = None

            items: list[tuple[float, float, str, float]] = []  # (cy, cx, text, size)
            if points is not None and len(decoded_info) == len(points):
                for info, pts in zip(decoded_info, points):
                    text = info or ""
                    # pts shape (4,2)
                    try:
                        cy = float(pts[:, 1].mean())
                        cx = float(pts[:, 0].mean())
                        size = float(pts[:, 1].max() - pts[:, 1].min())
                    except Exception:
                        continue
                    if text:
                        items.append((cy, cx, text, size))

            # If multi failed or produced too few items, try a simple grid-based enhancement isn't implemented here
            # We proceed with whatever we decoded.

            if not items:
                lines_all_pages.append([])
                continue

            # Cluster into lines by Y using a running-average threshold based on median QR height
            median_h = (
                statistics.median([s for (_, _, _, s) in items]) if items else 20.0
            )
            y_threshold = max(5.0, 0.6 * median_h)

            items.sort(key=lambda t: (t[0], t[1]))  # sort by y then x
            lines: list[list[tuple[float, float, str, float]]] = []
            current_line: list[tuple[float, float, str, float]] = []
            current_y = None
            for it in items:
                y = it[0]
                if current_y is None:
                    current_line = [it]
                    current_y = y
                elif abs(y - current_y) <= y_threshold:
                    current_line.append(it)
                    # Update running average y
                    current_y = (current_y * 0.7) + (y * 0.3)
                else:
                    # finalize current line
                    current_line.sort(key=lambda t: t[1])
                    lines.append(current_line)
                    current_line = [it]
                    current_y = y

            if current_line:
                current_line.sort(key=lambda t: t[1])
                lines.append(current_line)

            lines_all_pages.append(lines)

    # Compose by scanning characters and using '+' as paragraph delimiter; do not output '+'
    paragraphs: list[str] = []
    current: list[str] = []

    for page_lines in lines_all_pages:
        if not page_lines:
            continue
        for li, line in enumerate(page_lines):
            # characters in reading order for this line
            line_chars = [ch[2] for ch in line]
            for ch in line_chars:
                if ch == "+":
                    # end of paragraph; flush current
                    paragraph = "".join(current).strip()
                    if paragraph:
                        paragraphs.append(paragraph)
                    current = []
                else:
                    current.append(ch)

    # flush any remaining content as the last paragraph
    tail = "".join(current).strip()
    if tail:
        paragraphs.append(tail)

    return "\n".join(paragraphs).strip("\n")


def main():
    parser = argparse.ArgumentParser(
        description="从二维码测试PDF提取文本：优先直接提取文本，失败则渲染后扫描二维码。"
    )
    parser.add_argument(
        "input", nargs="?", default="测试文档.pdf", help="输入 PDF 文件路径"
    )
    parser.add_argument(
        "output", nargs="?", default="result.txt", help="输出 TXT 文件路径（UTF-8）"
    )
    parser.add_argument(
        "--zoom",
        type=float,
        default=4.0,
        help="渲染倍率（用于二维码扫描回退路径），默认 4.0",
    )
    args = parser.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    if not in_path.exists():
        print(f"找不到输入文件: {in_path}", file=sys.stderr)
        sys.exit(1)

    # 1) Try to extract text directly from PDF
    text = extract_text_from_pdf(in_path)

    # 2) Fallback to QR detection if needed
    if not text:
        try:
            text = decode_qr_from_pdf(in_path, zoom=args.zoom)
        except Exception as e:
            print(f"二维码扫描失败：{e}", file=sys.stderr)
            sys.exit(2)

    # Write output with timestamp suffix: _YYMMDD_hhmmss
    ts = datetime.now().strftime("%y%m%d_%H%M%S")
    suffix = out_path.suffix if out_path.suffix else ".txt"
    stamped_out = out_path.with_name(f"{out_path.stem}_{ts}{suffix}")
    stamped_out.write_text(text, encoding="utf-8")
    print(f"已写出结果到: {stamped_out}")


if __name__ == "__main__":
    main()
