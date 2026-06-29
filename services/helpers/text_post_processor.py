"""
Text Post-Processor Service
Centralized text cleaning for both HTML and PDF extracted content

Handles:
- Wikipedia table-like formatting (key-value pairs)
- Orphaned hyphens and bullets
- Line break normalization
- Excessive whitespace removal
"""

import re
from typing import Optional, Dict, List


def clean_wikipedia_tables(text: str) -> str:
    """
    Clean Wikipedia-style table formatting where alternating lines are key-value pairs.

    Example input:
        |Alternative names
        |Idly
        |Course
        |Breakfast, dinner

    Example output:
        Alternative names: Idly
        Course: Breakfast, dinner

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text with table pairs merged
    """
    lines = text.split('\n')
    cleaned_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Check if this is a Wikipedia table key (starts with |)
        if line.startswith('|') and i + 1 < len(lines):
            next_line = lines[i + 1].strip()

            # Check if next line is also a table value (starts with |)
            if next_line.startswith('|'):
                # Merge key-value pair
                key = line[1:].strip()  # Remove leading |
                value = next_line[1:].strip()  # Remove leading |

                # Only merge if both key and value are non-empty
                if key and value:
                    cleaned_lines.append(f"{key}: {value}")
                    i += 2  # Skip both lines
                    continue

        # Not a table pair, keep line as-is
        cleaned_lines.append(line)
        i += 1

    return '\n'.join(cleaned_lines)


def remove_orphaned_hyphens(text: str) -> str:
    """
    Remove lines that contain ONLY a hyphen (orphaned list markers).

    Example input:
        -
        Idli batter
        -
        Idli mold
        - Actual list item

    Example output:
        Idli batter
        Idli mold
        - Actual list item

    Args:
        text: Raw extracted text

    Returns:
        Text with orphaned hyphens removed
    """
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip lines that are ONLY a hyphen (with optional whitespace)
        if stripped == '-':
            continue

        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def normalize_line_breaks(text: str, source: str = 'html') -> str:
    """
    Normalize excessive line breaks while preserving paragraph structure.

    Args:
        text: Raw extracted text
        source: 'html' or 'pdf' (different strategies)

    Returns:
        Text with normalized line breaks
    """
    if source == 'html':
        # HTML often has excessive line breaks from extraction
        # Collapse 3+ consecutive line breaks to 2 (paragraph spacing)
        text = re.sub(r'\n{3,}', '\n\n', text)

    elif source == 'pdf':
        # PDF line breaks are usually already optimized by the extractor
        # Just remove excessive whitespace
        text = re.sub(r'\n{4,}', '\n\n', text)

    return text


def remove_wiki_edit_markers(text: str) -> str:
    """
    Remove Wikipedia [edit] markers that appear after headings.

    Example: "History[edit]" -> "History"

    Args:
        text: Raw extracted text

    Returns:
        Text with [edit] markers removed
    """
    # Remove [edit] markers (case-insensitive)
    text = re.sub(r'\[edit\]', '', text, flags=re.IGNORECASE)

    # Also remove other common Wikipedia markers
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[source\]', '', text, flags=re.IGNORECASE)

    return text


def remove_excessive_whitespace(text: str) -> str:
    """
    Remove excessive whitespace while preserving structure.

    Args:
        text: Raw extracted text

    Returns:
        Text with normalized whitespace
    """
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        # Remove trailing/leading whitespace from each line
        cleaned_line = line.strip()
        cleaned_lines.append(cleaned_line)

    # Join and remove empty lines at start/end
    result = '\n'.join(cleaned_lines)
    result = result.strip()

    return result


def clean_extracted_text(
    text: str,
    source: str = 'html',
    options: Optional[Dict] = None
) -> str:
    """
    Main entry point - orchestrates all text cleaning operations.

    Args:
        text: Raw extracted text
        source: 'html' or 'pdf' (affects cleaning strategy)
        options: Optional configuration dict:
            - remove_wiki_edit_markers: bool (default True for HTML)
            - remove_orphaned_hyphens: bool (default True)
            - clean_wikipedia_tables: bool (default True for HTML)
            - normalize_line_breaks: bool (default True)

    Returns:
        Cleaned text ready for display/embedding
    """
    if not text:
        return ""

    # Default options
    default_options = {
        'remove_wiki_edit_markers': source == 'html',
        'remove_orphaned_hyphens': True,
        'clean_wikipedia_tables': source == 'html',
        'normalize_line_breaks': True
    }

    if options:
        default_options.update(options)

    # Cleaning pipeline
    cleaned = text

    # Step 1: Clean Wikipedia table formatting (HTML only by default)
    if default_options['clean_wikipedia_tables']:
        cleaned = clean_wikipedia_tables(cleaned)

    # Step 2: Remove orphaned hyphens
    if default_options['remove_orphaned_hyphens']:
        cleaned = remove_orphaned_hyphens(cleaned)

    # Step 3: Remove Wikipedia edit markers (HTML only by default)
    if default_options['remove_wiki_edit_markers']:
        cleaned = remove_wiki_edit_markers(cleaned)

    # Step 4: Normalize line breaks
    if default_options['normalize_line_breaks']:
        cleaned = normalize_line_breaks(cleaned, source=source)

    # Step 5: Remove excessive whitespace
    cleaned = remove_excessive_whitespace(cleaned)

    return cleaned


# ============================================================================
# UTILITY FUNCTIONS FOR SPECIFIC USE CASES
# ============================================================================

def clean_for_display(text: str, source: str = 'html', max_length: Optional[int] = None) -> str:
    """
    Clean text specifically for UI display (search results, cards, etc.).

    Args:
        text: Raw extracted text
        source: 'html' or 'pdf'
        max_length: Optional max length for truncation

    Returns:
        Display-ready text
    """
    cleaned = clean_extracted_text(text, source=source)

    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + '...'

    return cleaned


def clean_for_embedding(text: str, source: str = 'html') -> str:
    """
    Clean text specifically for embedding generation.
    Preserves semantic meaning while removing noise.

    Args:
        text: Raw extracted text
        source: 'html' or 'pdf'

    Returns:
        Embedding-ready text
    """
    # Use standard cleaning but preserve more structure
    options = {
        'remove_wiki_edit_markers': True,
        'remove_orphaned_hyphens': True,
        'clean_wikipedia_tables': True,
        'normalize_line_breaks': True
    }

    return clean_extracted_text(text, source=source, options=options)


# ============================================================================
# DEBUGGING UTILITIES
# ============================================================================

def debug_cleaning_pipeline(text: str, source: str = 'html') -> Dict[str, str]:
    """
    Run text through cleaning pipeline and return intermediate results.
    Useful for debugging and understanding what each step does.

    Args:
        text: Raw extracted text
        source: 'html' or 'pdf'

    Returns:
        Dict with results after each cleaning step
    """
    results = {
        'original': text,
        'after_wikipedia_tables': clean_wikipedia_tables(text),
    }

    results['after_orphaned_hyphens'] = remove_orphaned_hyphens(results['after_wikipedia_tables'])
    results['after_wiki_markers'] = remove_wiki_edit_markers(results['after_orphaned_hyphens'])
    results['after_line_breaks'] = normalize_line_breaks(results['after_wiki_markers'], source=source)
    results['final'] = remove_excessive_whitespace(results['after_line_breaks'])

    return results
