from behaviours.miniapp_link import miniapp_url


def test_the_url_opens_the_mini_app_with_the_token():
    assert (
        miniapp_url("partitelle_bot", "lista", "abc_DEF-123")
        == "https://t.me/partitelle_bot/lista?startapp=abc_DEF-123"
    )
