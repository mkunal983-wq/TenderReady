"""Bounded PDF parsing in a disposable child process; no OCR or external fetches."""
import json
import logging
from pathlib import Path
import subprocess
import sys


class PDFError(ValueError):
    pass


def parse_pdf(path: Path, max_pages: int, max_chars: int) -> dict:
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise PDFError("Encrypted PDFs are not supported. Upload an unencrypted text-based PDF.")
        if not 1 <= len(reader.pages) <= max_pages:
            raise PDFError(f"PDF must contain 1–{max_pages} pages.")
        pages, warnings, total = [], [], 0
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").replace("\x00", "")
            total += len(text)
            if total > max_chars:
                raise PDFError("Extracted text exceeds the supported document limit.")
            pages.append({"page": number, "text": text})
            if not text.strip():
                warnings.append(f"Page {number} has no extractable text; it needs manual review or OCR.")
        if not any(p["text"].strip() for p in pages):
            raise PDFError("No extractable text found. Scanned PDFs need OCR, which is not supported yet.")
        return {"pages": pages, "warnings": warnings}
    except PDFError:
        raise
    except Exception:
        raise PDFError("The PDF is malformed or cannot be read safely.") from None


def parse_isolated(path: Path, settings) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "tenderready.pdf_parse", str(path),
             str(settings.pdf_max_pages), str(settings.pdf_max_text_chars)],
            capture_output=True, timeout=settings.pdf_parse_timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        raise PDFError("PDF parsing timed out. Try a smaller text-based PDF.") from None
    if result.returncode != 0:
        raise PDFError("PDF parsing exceeded resource limits or failed.")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        raise PDFError("PDF parser returned an invalid response.") from None
    if "error" in payload:
        raise PDFError(payload["error"])
    return payload


if __name__ == "__main__":
    # The parent also enforces a wall-clock deadline and kills timed-out children.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (18, 18))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    except (ImportError, OSError, ValueError):
        pass
    try:
        print(json.dumps(parse_pdf(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))))
    except PDFError as error:
        print(json.dumps({"error": str(error)}))
