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


def plain_text(markdown: str | None) -> str | None:
    """Telegram markdown without its markers: `[text](url)` becomes `text`, `*`, `_` and
    backticks go, trailing whitespace goes. None when there is nothing to show (nothing
    stored, empty, or the literal "None")."""
    if markdown is None or markdown.strip() in ("", "None"):
        return None
    text = _LINK.sub(r"\1", markdown)
    text = re.sub(r"[*_`]", "", text).rstrip()
    return text or None
