import re
import html
from collections import Counter


def remove_repeated_short_lines(
    md: str,
    min_repeat: int = 3,
    max_len: int = 80,
) -> str:
    """
    Remove repeated footer/header-like lines.
    Example: website footer, page label, repeated source name.

    Safety:
    - Keep Markdown headings
    - Keep bullet lines
    - Keep numbered list lines
    """

    if not md:
        return ""

    lines = md.splitlines()
    normalized_lines = [line.strip() for line in lines if line.strip()]
    counts = Counter(normalized_lines)

    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append(line)
            continue

        # Keep useful Markdown structure
        if (
            stripped.startswith("#")
            or stripped.startswith("- ")
            or re.match(r"^\d+\.", stripped)
        ):
            cleaned_lines.append(line)
            continue

        # Remove repeated short footer/header-like line
        if (
            len(stripped) <= max_len
            and counts[stripped] >= min_repeat
        ):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def clean_picture_blocks(
    md: str,
    keep_picture_text: bool = True,
    min_picture_text_chars: int = 80,
    separate_picture_text: bool = True,
) -> str:
    """
    Handle pymupdf4llm picture OCR blocks.

    keep_picture_text=True:
        Keep useful OCR text from picture blocks.

    keep_picture_text=False:
        Remove the whole picture OCR block.

    min_picture_text_chars:
        If OCR text is shorter than this, remove it.
        Short OCR is often noisy, for example:
        Vietnam
        Highlights
        Ha Long Bay.

    separate_picture_text=True:
        Keep useful OCR text under a separate Markdown heading:
        ### Image OCR Text

        This prevents OCR text from polluting the main paragraph chunk.
    """

    if not md:
        return ""

    block_pattern = re.compile(
        r"""
        \s*
        \*{0,2}\s*-{2,}\s*Start\ of\ picture\ text\s*-{2,}\s*\*{0,2}
        \s*
        (.*?)
        \s*
        \*{0,2}\s*-{2,}\s*End\ of\ picture\ text\s*-{2,}\s*\*{0,2}
        \s*
        """,
        flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    def replace_picture_block(match: re.Match) -> str:
        picture_text = match.group(1).strip()

        # Normalize OCR text inside the image block
        picture_text = re.sub(r"\n{3,}", "\n\n", picture_text)
        picture_text = "\n".join(
            line.strip()
            for line in picture_text.splitlines()
            if line.strip()
        )

        flat_text = re.sub(r"\s+", " ", picture_text).strip()

        if not keep_picture_text:
            return "\n"

        # Remove very short OCR text because it often pollutes the nearby paragraph
        if len(flat_text) < min_picture_text_chars:
            return "\n"

        # Remove OCR text with too little alphabetic content
        alpha_count = sum(ch.isalpha() for ch in flat_text)
        alpha_ratio = alpha_count / max(len(flat_text), 1)

        if alpha_ratio < 0.35:
            return "\n"

        if separate_picture_text:
            return f"\n\n### Image OCR Text\n\n{picture_text}\n\n"

        return f"\n\n{picture_text}\n\n"

    md = block_pattern.sub(replace_picture_block, md)

    # Remove leftover wrapper lines if some malformed block was not captured
    md = re.sub(
        r"(?im)^\s*\*{0,2}\s*-{2,}\s*Start of picture text\s*-{2,}\s*\*{0,2}\s*$",
        "",
        md,
    )

    md = re.sub(
        r"(?im)^\s*\*{0,2}\s*-{2,}\s*End of picture text\s*-{2,}\s*\*{0,2}\s*$",
        "",
        md,
    )

    return md


def clean_markdown_general(
    md: str,
    keep_picture_text: bool = True,
    min_picture_text_chars: int = 80,
    separate_picture_text: bool = True,
) -> str:
    """
    General Markdown cleaner for PDF-to-Markdown output.

    Suitable for:
    - pymupdf4llm output
    - tourism PDFs
    - brochures
    - reports
    - RAG preprocessing

    Goal:
    Clean noise but avoid deleting useful content.
    """

    if not md:
        return ""

    # 1. Basic normalization
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    md = html.unescape(md)

    # 2. Convert HTML line breaks to real newlines
    md = re.sub(
        r"<br\s*/?>",
        "\n",
        md,
        flags=re.IGNORECASE,
    )

    # 3. Remove picture placeholder lines only
    # Example:
    # **==> picture [xxx] ... <==**
    md = re.sub(
        r"(?im)^\s*\*{0,2}\s*==>\s*picture\b.*?<==\s*\*{0,2}\s*$",
        "",
        md,
    )

    # 4. Handle picture OCR blocks
    # Short OCR text is removed.
    # Useful long OCR text is kept separately.
    md = clean_picture_blocks(
        md,
        keep_picture_text=keep_picture_text,
        min_picture_text_chars=min_picture_text_chars,
        separate_picture_text=separate_picture_text,
    )

    # 5. Remove Markdown image syntax
    md = re.sub(
        r"!\[[^\]]*\]\([^)]+\)",
        "",
        md,
    )

    # 6. Remove simple/common HTML tags
    # Safer than removing every <...> because some text may contain comparison symbols
    md = re.sub(
        r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*)?>",
        "",
        md,
    )

    # 7. Fix headings without spaces
    # ##**Title** -> ## Title
    md = re.sub(
        r"(?m)^(#{1,6})\s*\*\*(.*?)\*\*\s*$",
        r"\1 \2",
        md,
    )

    # ##Title -> ## Title
    md = re.sub(
        r"(?m)^(#{1,6})([^\s#])",
        r"\1 \2",
        md,
    )

    # 8. Split heading stuck to paragraph
    # ## Welcome to Vietnam**Vietnam is...**
    md = re.sub(
        r"(?m)^(#{1,6}\s+[^\n*]{3,100})\*\*(.+?)\*\*\s*$",
        r"\1\n\n\2",
        md,
    )

    # 9. Split text stuck to bold heading
    # karsts**Da Nang** Breezy beaches
    # ->
    # karsts
    #
    # ## Da Nang
    #
    # Breezy beaches
    md = re.sub(
        r"([a-z0-9.,;:!?])\s*\*\*([A-ZÀ-Ỹ][A-Za-zÀ-ỹ0-9&,'’() /-]{2,80})\*\*\s+",
        r"\1\n\n## \2\n\n",
        md,
    )

    # 10. Convert standalone bold line to heading
    # **Fabulous Food** -> ## Fabulous Food
    md = re.sub(
        r"(?m)^\s*\*\*([A-ZÀ-Ỹ][^*\n]{2,100})\*\*\s*$",
        r"## \1",
        md,
    )

    # 11. Remove bold markers
    md = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        md,
    )

    md = re.sub(
        r"__(.*?)__",
        r"\1",
        md,
    )

    # 12. Remove italic markers safely
    # Safe for normal asterisk italic
    md = re.sub(
        r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)",
        r"\1",
        md,
    )

    # Safe for underscore italic
    # Avoid breaking technical words like input_UC1, amount_cd_para1
    md = re.sub(
        r"(?<!\w)_(?!_)(.*?)(?<!_)_(?!\w)",
        r"\1",
        md,
    )

    # 13. Remove strikethrough artifacts
    md = re.sub(
        r"~~(.*?)~~",
        r"\1",
        md,
    )

    # 14. Fix broken numbered list patterns
    # 1Title - text -> 1. Title - text
    # Limited to 1-2 digits to avoid changing years
    md = re.sub(
        r"(?m)^\s*-?\s*(\d{1,2})\s*([A-ZÀ-Ỹ][^\n]{2,100}?)\s+-\s+",
        r"\1. \2 - ",
        md,
    )

    # 1 Title -> 1. Title
    # Limited to 1-2 digits to avoid changing:
    # 2026 Vietnam guide -> 2026. Vietnam guide
    md = re.sub(
        r"(?m)^\s*(\d{1,2})\s+([A-ZÀ-Ỹ][^\n]+)$",
        r"\1. \2",
        md,
    )

    # 15. Fix spacing before punctuation
    md = re.sub(
        r"\s+([.,;:!?])",
        r"\1",
        md,
    )

    # 16. Fix repeated spaces, but not newlines
    md = re.sub(
        r"[ \t]{2,}",
        " ",
        md,
    )

    # 17. Normalize bullets
    md = re.sub(
        r"(?m)^\s*[-•♦]\s*",
        "- ",
        md,
    )

    # 18. Remove repeated short footer/header lines
    md = remove_repeated_short_lines(md)

    # 19. Remove empty headings
    md = re.sub(
        r"(?m)^#{1,6}\s*$",
        "",
        md,
    )

    # 20. Remove trailing spaces
    md = "\n".join(
        line.rstrip()
        for line in md.splitlines()
    )

    # 21. Collapse too many blank lines
    md = re.sub(
        r"\n{3,}",
        "\n\n",
        md,
    )

    return md.strip()