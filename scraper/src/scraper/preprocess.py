import hashlib
import re

from bs4 import BeautifulSoup

# Pages built as SPAs (like Microsoft's) dump huge JSON config blobs into the markdown.
# No real prose line is this long, so very long lines are always junk.
MAX_LINE_CHARS = 2000


def html_to_lines(html: str) -> list[str]:
    """HTML description -> plain lines, bullets rendered as '- text'. Shared by any
    adapter whose source gives job descriptions as HTML (Microsoft, Google, ...)."""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert(0, "\n- ")
    for block in soup.find_all(["p", "div", "ul", "ol", "h3", "h4"]):
        block.append("\n")
    text = soup.get_text().replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def clean_markdown(markdown: str) -> str:
    kept: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if len(stripped) > MAX_LINE_CHARS:
            continue
        if stripped.startswith("`{") or stripped.startswith("`http"):
            continue
        kept.append(line.rstrip().replace("\xa0", " "))
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit("\n", 1)[0]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
