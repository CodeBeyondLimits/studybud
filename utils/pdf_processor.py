from typing import Dict, Tuple

from pypdf import PdfReader


class PDFExtractionError(Exception):
    pass


def extract_pdf_text(uploaded_file) -> Tuple[str, Dict[str, int]]:
    try:
        reader = PdfReader(uploaded_file)
    except Exception as exc:
        raise PDFExtractionError("This PDF could not be read. Choose a valid PDF file.") from exc

    if getattr(reader, "is_encrypted", False):
        raise PDFExtractionError("This PDF is password-protected. Upload an unlocked copy.")

    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            raise PDFExtractionError(
                f"Text could not be extracted from page {page_number}."
            ) from exc
        if page_text.strip():
            pages.append(page_text)

    text = "\n\n".join(pages).strip()
    if not text:
        raise PDFExtractionError(
            "No readable text was found. Try a text-based PDF or paste the notes."
        )

    return text, {
        "pages": len(reader.pages),
        "characters": len(text),
    }
