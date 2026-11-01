"""Reading names out of what a person typed, free of Telegram."""

import re

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def parse_names(text: str) -> list[str]:
    """Split "a, b,,c" into ["a", "b", "c"]: comma separated, trimmed, without empty names."""
    return [name.strip() for name in text.split(",") if name.strip()]


def parse_swap(text: str) -> tuple[str, str] | None:
    """Split "scambia a con b" into ("a", "b"), or None when it is not exactly "scambia <a> con <b>"."""
    names = text.split(None, 1)[1:]
    parts = [part.strip() for part in f" {names[0]} ".split(" con ")] if names else []
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def is_command_name(name: str) -> bool:
    """A name that looks like a /command is not a name."""
    return name.startswith("/")


_ESCAPED = re.compile(r"\\([*_`\[])")
_BOLD = re.compile(r"\*((?=\S)[^*\n]*?(?<=\S))?\*")
_ITALIC = re.compile(r"(?<![\w_])_(?=\S)([^_\n]*?)(?<=\S)_(?![\w_])")
_SENTINEL = 0xE000  # private use area: stands for an escaped marker while the others are stripped


def plain_text(markdown: str | None) -> str | None:
    """Telegram markdown without its markers: `[text](url)` becomes `text`, paired `*bold*`
    and `_italic_` lose their markers, backticks go, an escaped marker (`\\*`) becomes the
    literal character, single markers and underscores inside words stay, trailing whitespace
    goes. None when there is nothing to show (nothing stored, empty, or the literal "None")."""
    if markdown is None or markdown.strip() in ("", "None"):
        return None
    text = _ESCAPED.sub(lambda m: chr(_SENTINEL + ord(m.group(1))), markdown)
    text = _LINK.sub(r"\1", text).replace("`", "")
    text = _ITALIC.sub(r"\1", _BOLD.sub(lambda m: m.group(1) or "", text)).rstrip()
    text = re.sub(r"[\ue000-\ue0ff]", lambda m: chr(ord(m.group()) - _SENTINEL), text)
    return text or None
