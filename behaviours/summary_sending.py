from telegram.error import BadRequest


def is_parse_error(error: BadRequest) -> bool:
    return "can't parse entities" in error.message.lower()
