"""
PDF Processing Helper
Extracts metadata (title, date) and text content from downloaded PDFs.

Uses:
- pdfplumber for metadata and text extraction
- pypdfium2 as fallback (already used in pdf_extractor.py)
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import pdfplumber


# Text extraction sampling configuration
CHARS_FROM_START = 5000   # First 5K chars
CHARS_FROM_MIDDLE = 3000  # Middle 3K chars
CHARS_FROM_END = 2000     # Last 2K chars


def extract_pdf_title(pdf_path: str) -> Optional[str]:
    """
    Extract title from PDF metadata or first line of text.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Title string or None if extraction fails
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Try metadata first
            if pdf.metadata and pdf.metadata.get('Title'):
                title = pdf.metadata.get('Title').strip()
                if title and title.lower() not in ['untitled', 'document', '']:
                    return title

            # Fallback: Extract from first page
            if len(pdf.pages) > 0:
                text = pdf.pages[0].extract_text()
                if text:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    if lines:
                        # Take first non-empty line, limit to 100 chars
                        return lines[0][:100]
    except Exception as e:
        print(f"[PDF Processor] Title extraction error: {e}")

    return None


def extract_pdf_date(pdf_path: str) -> Dict[str, str]:
    """
    Extract publication date from PDF metadata.
    Tries multiple metadata fields and falls back to file system dates.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dict with publication_date, publication_year, publication_month, publication_day
        Defaults to 'NA' if extraction fails
    """
    result = {
        'publication_date': 'NA',
        'publication_year': 'NA',
        'publication_month': 'NA',
        'publication_day': 'NA'
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.metadata:
                # Try CreationDate first, then ModDate
                date_str = pdf.metadata.get('CreationDate') or pdf.metadata.get('ModDate')

                if date_str:
                    # PDF dates are in format: D:YYYYMMDDHHmmSS+TZ
                    if date_str.startswith('D:'):
                        date_str = date_str[2:]

                    # Extract date parts (YYYYMMDD)
                    if len(date_str) >= 8:
                        year = date_str[0:4]
                        month = date_str[4:6]
                        day = date_str[6:8]

                        # Validate
                        if year.isdigit() and month.isdigit() and day.isdigit():
                            result['publication_date'] = f"{year}-{month}-{day}"
                            result['publication_year'] = year
                            result['publication_month'] = month
                            result['publication_day'] = day
                            return result
    except Exception as e:
        print(f"[PDF Processor] Date extraction error (metadata): {e}")

    # Fallback: Use file modification time
    try:
        mtime = os.path.getmtime(pdf_path)
        dt = datetime.fromtimestamp(mtime)

        result['publication_date'] = dt.strftime('%Y-%m-%d')
        result['publication_year'] = str(dt.year)
        result['publication_month'] = f"{dt.month:02d}"
        result['publication_day'] = f"{dt.day:02d}"
    except Exception as e:
        print(f"[PDF Processor] Date extraction error (file time): {e}")

    return result


def extract_pdf_text(pdf_path: str, max_chars: Optional[int] = None) -> str:
    """
    Extract text from PDF with smart sampling for AI analysis.

    For large PDFs, samples from start, middle, and end to stay within token limits.

    Args:
        pdf_path: Path to PDF file
        max_chars: Maximum characters to extract (None = extract all)

    Returns:
        Extracted text (full or sampled)
    """
    text = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extract all pages
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            # If no max or under limit, return full text
            if not max_chars or len(text) <= max_chars:
                return text

            # Smart sampling: start + middle + end
            start_text = text[:CHARS_FROM_START]

            end_text = text[-CHARS_FROM_END:] if CHARS_FROM_END > 0 else ""

            middle_start = (len(text) - CHARS_FROM_MIDDLE) // 2
            middle_end = middle_start + CHARS_FROM_MIDDLE
            middle_text = text[middle_start:middle_end] if CHARS_FROM_MIDDLE > 0 else ""

            return f"""[DOCUMENT START - First {CHARS_FROM_START:,} characters]
{start_text}

[DOCUMENT MIDDLE - {CHARS_FROM_MIDDLE:,} characters from center]
{middle_text}

[DOCUMENT END - Last {CHARS_FROM_END:,} characters]
{end_text}"""

    except Exception as e:
        print(f"[PDF Processor] Text extraction error: {e}")
        return text  # Return whatever was extracted before error


def process_pdf(pdf_path: str, max_text_chars: Optional[int] = None) -> Dict:
    """
    Complete PDF processing: extract title, date, and text.

    Args:
        pdf_path: Path to PDF file
        max_text_chars: Max characters for text extraction (None = all)

    Returns:
        Dict with:
        - status: 'success' or 'failed'
        - title: Extracted title or None
        - date: Dict with publication_date, year, month, day
        - text: Extracted text
        - num_pages: Page count
        - num_words: Word count estimate
        - file_size_mb: File size in MB
        - error: Error message if failed
    """
    result = {
        'status': 'failed',
        'title': None,
        'date': {
            'publication_date': 'NA',
            'publication_year': 'NA',
            'publication_month': 'NA',
            'publication_day': 'NA'
        },
        'text': '',
        'num_pages': 0,
        'num_words': 0,
        'file_size_mb': 0.0,
        'error': None
    }

    try:
        # Check file exists
        if not os.path.exists(pdf_path):
            result['error'] = f"File not found: {pdf_path}"
            return result

        # Get file size
        file_size = os.path.getsize(pdf_path)
        result['file_size_mb'] = file_size / (1024 * 1024)

        # Extract title
        print(f"[PDF Processor] Extracting title from: {pdf_path}")
        result['title'] = extract_pdf_title(pdf_path)

        # Extract date
        print(f"[PDF Processor] Extracting date from: {pdf_path}")
        result['date'] = extract_pdf_date(pdf_path)

        # Extract text
        print(f"[PDF Processor] Extracting text from: {pdf_path}")
        result['text'] = extract_pdf_text(pdf_path, max_chars=max_text_chars)

        # Get page count and word count
        with pdfplumber.open(pdf_path) as pdf:
            result['num_pages'] = len(pdf.pages)

        # Estimate word count from extracted text
        if result['text']:
            result['num_words'] = len(result['text'].split())

        result['status'] = 'success'
        print(f"[PDF Processor] ✓ Processing complete - {result['num_pages']} pages, {result['num_words']} words")

    except Exception as e:
        result['error'] = str(e)
        print(f"[PDF Processor] ✗ Processing failed: {e}")

    return result


# Quick validation function
def validate_pdf(pdf_path: str) -> bool:
    """
    Quick check if file is a valid PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        True if valid PDF, False otherwise
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Just try to access page count
            _ = len(pdf.pages)
        return True
    except:
        return False


if __name__ == "__main__":
    # Test with a sample PDF
    print("PDF Processor Helper - Test Mode")
    print("=" * 50)

    # Example usage
    test_pdf = "downloaded_pdfs/sample.pdf"

    if os.path.exists(test_pdf):
        result = process_pdf(test_pdf, max_text_chars=10000)

        print(f"\nStatus: {result['status']}")
        print(f"Title: {result['title']}")
        print(f"Date: {result['date']['publication_date']}")
        print(f"Pages: {result['num_pages']}")
        print(f"Words: {result['num_words']}")
        print(f"Size: {result['file_size_mb']:.2f} MB")

        if result['error']:
            print(f"Error: {result['error']}")
        else:
            print(f"\nText preview (first 200 chars):")
            print(result['text'][:200])
    else:
        print(f"Test file not found: {test_pdf}")
        print("Place a PDF file there to test extraction.")
