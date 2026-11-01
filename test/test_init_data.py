import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import pytest

from miniapp_signing import init_data, sign
from web.init_data import InitData, InvalidInitData, validate_init_data

TOKEN = "123456:TEST"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
TS = int(NOW.timestamp())
PARAM = "Abc_-123456789012345"


def validate(raw, token=TOKEN, max_age=3600):
    return validate_init_data(raw, token, now=NOW, max_age=max_age)


def test_valid_data_gives_only_the_needed_fields():
    raw = init_data(
        TOKEN,
        auth_date=TS - 10,
        start_param=PARAM,
        user={
            "id": 7,
            "first_name": "Anna",
            "last_name": "Bianchi",
            "username": "Anna_B",
            "language_code": "it",
            "is_premium": True,
            "photo_url": "https://example.com/x.jpg",
        },
        extra={"chat_instance": "123", "chat_type": "group", "query_id": "AAA"},
    )
    data = validate(raw)
    assert data == InitData(7, "Anna_B", "Anna", "Bianchi", PARAM)
    assert set(vars(data)) == {
        "user_id",
        "username",
        "first_name",
        "last_name",
        "start_param",
    }


def test_optional_user_fields_may_be_missing():
    raw = init_data(TOKEN, auth_date=TS, start_param=PARAM, user={"id": 9})
    assert validate(raw) == InitData(9, None, None, None, PARAM)


def test_signature_field_is_part_of_the_signed_string():
    raw = init_data(TOKEN, auth_date=TS, start_param=PARAM, extra={"signature": "xyz"})
    assert validate(raw).user_id == 7
    tampered = raw.replace("signature=xyz", "signature=xyw")
    with pytest.raises(InvalidInitData):
        validate(tampered)


def test_a_tampered_field_is_refused():
    raw = init_data(TOKEN, auth_date=TS, start_param=PARAM)
    with pytest.raises(InvalidInitData):
        validate(raw.replace("%22id%22%3A+7", "%22id%22%3A+8"))
    assert "%22id%22%3A+7" in raw


def test_the_wrong_bot_token_is_refused():
    raw = init_data("999:OTHER", auth_date=TS, start_param=PARAM)
    with pytest.raises(InvalidInitData):
        validate(raw)


@pytest.mark.parametrize("bad", ["", "abc", "A" * 63, "G" * 64, "A" * 64, "a" * 65])
def test_missing_or_malformed_hash_is_refused(bad):
    raw = init_data(TOKEN, auth_date=TS, start_param=PARAM)
    without = raw.rsplit("&hash=", 1)[0]
    with pytest.raises(InvalidInitData):
        validate(without + (f"&hash={bad}" if bad is not None else ""))
    with pytest.raises(InvalidInitData):
        validate(without)


def test_expired_data_is_refused_and_the_limit_is_inclusive():
    validate(init_data(TOKEN, auth_date=TS - 3600, start_param=PARAM))
    with pytest.raises(InvalidInitData):
        validate(init_data(TOKEN, auth_date=TS - 3601, start_param=PARAM))


def test_future_auth_date_is_refused_beyond_a_minute():
    validate(init_data(TOKEN, auth_date=TS + 60, start_param=PARAM))
    with pytest.raises(InvalidInitData):
        validate(init_data(TOKEN, auth_date=TS + 61, start_param=PARAM))


def test_missing_or_non_numeric_auth_date_is_refused():
    fields = {"user": json.dumps({"id": 7}), "start_param": PARAM}
    with pytest.raises(InvalidInitData):
        validate(sign(fields, TOKEN))
    with pytest.raises(InvalidInitData):
        validate(sign({**fields, "auth_date": "yesterday"}, TOKEN))


def test_duplicate_key_is_refused():
    raw = init_data(TOKEN, auth_date=TS, start_param=PARAM)
    with pytest.raises(InvalidInitData):
        validate(raw + "&start_param=" + PARAM)


def test_not_a_query_string_is_refused():
    with pytest.raises(InvalidInitData):
        validate("no-equals-sign")
    with pytest.raises(InvalidInitData):
        validate("")


def test_missing_user_is_refused():
    fields = {"auth_date": str(TS), "start_param": PARAM}
    with pytest.raises(InvalidInitData):
        validate(sign(fields, TOKEN))


@pytest.mark.parametrize(
    "user",
    ["not json", "[1]", "{}", '{"id": "7"}', '{"id": true}', '{"id": 1.5}', "null"],
)
def test_user_without_an_integer_id_is_refused(user):
    fields = {"auth_date": str(TS), "start_param": PARAM, "user": user}
    with pytest.raises(InvalidInitData):
        validate(sign(fields, TOKEN))


@pytest.mark.parametrize(
    "param", [None, "", "short", "A" * 15, "A" * 65, "has space 123456789", "a/b" * 8]
)
def test_bad_start_param_is_refused(param):
    fields = {"auth_date": str(TS), "user": json.dumps({"id": 7})}
    if param is not None:
        fields["start_param"] = param
    with pytest.raises(InvalidInitData):
        validate(sign(fields, TOKEN))


def test_start_param_boundaries_are_accepted():
    for param in ("A" * 16, "z" * 64):
        raw = init_data(TOKEN, auth_date=TS, start_param=param)
        assert validate(raw).start_param == param


def test_oversize_data_is_refused_before_anything_else():
    raw = urlencode({"x": "a" * 4100})
    with pytest.raises(InvalidInitData, match="too long"):
        validate(raw)
    ok = init_data(TOKEN, auth_date=TS, start_param=PARAM)
    assert len(ok) < 4096
