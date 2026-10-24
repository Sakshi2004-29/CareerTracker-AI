
from pypdf import PdfReader
from io import BytesIO


def extract_resume_text(pdf_bytes: bytes) -> str:
    """
    Extract readable text from an uploaded PDF resume.
    pdf_bytes contains the PDF file data.
    """

    try:
        pdf_file = BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)

        if reader.is_encrypted:
            raise ValueError("This PDF is password-protected.")

        text_parts = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                text_parts.append(page_text)

        extracted_text = "\n".join(text_parts).strip()

        if not extracted_text:
            raise ValueError(
                "No readable text found. The PDF may contain scanned images."
            )

        return extracted_text

    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Could not read this PDF. Please upload a valid PDF resume."
        ) from error
