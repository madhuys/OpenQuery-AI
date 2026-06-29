"""
Content Drawer Component
Collapsible drawer for displaying full content with formatting
"""
import streamlit as st
import re


def _convert_text_to_markdown_html(text: str) -> str:
    """
    Convert plain text to formatted HTML with markdown-style headings.

    Args:
        text: Plain text content

    Returns:
        HTML-formatted content with proper heading tags
    """
    if not text:
        return ""

    # Step 1: Clean up excessive newlines (3+ becomes 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Step 2: Remove single chars/numbers between newlines (e.g., "\n2\n" -> "\n\n")
    text = re.sub(r'\n([0-9a-zA-Z])\n', '\n\n', text)

    # Step 3: Join broken sentences (lines that don't end with sentence-ending punctuation)
    lines = text.split('\n')
    joined_lines = []
    buffer = ""

    for line in lines:
        stripped = line.strip()

        # Empty line - flush buffer and add blank line
        if not stripped:
            if buffer:
                joined_lines.append(buffer)
                buffer = ""
            joined_lines.append("")  # Preserve blank line
            continue

        # Add to buffer
        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped

        # Check if line ends with sentence-ending punctuation or is likely a heading
        is_sentence_end = stripped and stripped[-1] in '.!?;:'
        is_heading = (len(stripped) < 80 and
                     stripped.isupper() and
                     any(c.isalpha() for c in stripped) and
                     len([c for c in stripped if c.isalpha()]) > 3)

        # Flush buffer if sentence ends or is heading
        if is_sentence_end or is_heading:
            joined_lines.append(buffer)
            buffer = ""

    # Flush any remaining buffer
    if buffer:
        joined_lines.append(buffer)

    # Step 4: Format lines as HTML
    formatted_lines = []

    for line in joined_lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            formatted_lines.append('<br>')
            continue

        # Detect headings (all caps, relatively short, not just numbers/symbols)
        if (len(stripped) < 80 and
            stripped.isupper() and
            any(c.isalpha() for c in stripped) and
            len([c for c in stripped if c.isalpha()]) > 3):
            # This is likely a heading
            formatted_lines.append(f'<h2 style="color: #1f77b4; margin-top: 20px; margin-bottom: 10px; font-weight: bold;">{stripped}</h2>')
        else:
            # Regular paragraph
            formatted_lines.append(f'<p style="margin-bottom: 10px; line-height: 1.6;">{stripped}</p>')

    return '\n'.join(formatted_lines)


def render_content_drawer(content: str, drawer_key: str, title: str = "Full Content"):
    """
    Render a collapsible content drawer with formatted text display.

    Args:
        content: Text content to display
        drawer_key: Unique key for this drawer's session state
        title: Title to show in the drawer header
    """
    if not content:
        st.info("No content available")
        return

    # Initialize session state for this drawer
    toggle_key = f"drawer_open_{drawer_key}"
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = False

    # Toggle button
    button_label = f"▼ {title}" if not st.session_state[toggle_key] else f"▲ Hide {title}"
    if st.button(f"{button_label} ({len(content):,} chars)", key=f"toggle_{drawer_key}"):
        st.session_state[toggle_key] = not st.session_state[toggle_key]

    # Show content if toggled on
    if st.session_state[toggle_key]:
        st.markdown("---")

        # Convert plain text to formatted HTML
        formatted_html = _convert_text_to_markdown_html(content)

        # Display in scrollable container with proper formatting
        st.markdown(
            f"""
            <div style="
                max-height: 600px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 20px;
                background-color: #f9f9f9;
                font-family: 'Georgia', serif;
                font-size: 16px;
            ">
                {formatted_html}
            </div>
            """,
            unsafe_allow_html=True
        )
