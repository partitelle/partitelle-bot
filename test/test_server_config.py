"""The uvicorn config built by main.build_server_config."""

from telegram.ext import Application

from main import build_server_config


def test_the_web_server_has_no_access_log():
    application = Application.builder().token("123456:FAKE-token").updater(None).build()
    config = build_server_config(application, "placeholder-secret")
    assert config.access_log is False
    assert config.host == "0.0.0.0"
