import asyncio
import hashlib
import logging
import os

import uvicorn
from telegram.ext import Application, ContextTypes

from conf.conf import (
    token,
    hosting_url,
    env,
    webhook_secret,
    jobs_secret,
    miniapp_short_name,
    miniapp_max_age,
)
from handlers import register_handlers
from web.app import WEBHOOK_PATH, create_app
from web.miniapp import miniapp_routes

logger = logging.getLogger(__name__)


def compute_webhook_secret(bot_token, configured_secret=None):
    """Secret Telegram sends back in X-Telegram-Bot-Api-Secret-Token (allowed: [A-Za-z0-9_-], 1-256 chars).

    `PB_WEBHOOK_SECRET` when set, otherwise derived deterministically from the bot token, so no extra
    configuration is needed and the secret is stable across restarts and deploys.
    """
    if configured_secret:
        return configured_secret
    return hashlib.sha256(bot_token.encode()).hexdigest()


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log every unhandled handler/job exception. Users see nothing, as it has always been."""
    logger.error("Exception while handling an update:", exc_info=context.error)


def build_application(bot_token=token, webhook=False):
    builder = Application.builder().token(bot_token)
    if webhook:
        # updates arrive through the web app (web/app.py), so there is no built-in updater
        builder = builder.updater(None)
    application = builder.build()
    register_handlers(application)
    application.add_error_handler(log_error)
    return application


def configure_logging():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # httpx logs every request URL at INFO, and Bot API URLs contain the bot token (/bot<token>/...).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # python-telegram-bot logs the parameters of every Bot API call at DEBUG (user ids, names, texts).
    logging.getLogger("telegram").setLevel(logging.INFO)


async def run_web(application, secret):
    """Serve the web app (webhook + health) and run the application next to it."""
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(
                application,
                secret,
                jobs_secret=jobs_secret,
                extra_routes=(
                    miniapp_routes(application, token, max_age=miniapp_max_age)
                    if miniapp_short_name
                    else ()
                ),
            ),
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 5000)),
        )
    )
    async with application:  # initialize / shutdown
        await application.bot.set_webhook(
            url=f"{hosting_url}/{WEBHOOK_PATH}", secret_token=secret
        )
        await application.start()  # update processing and the job queue
        try:
            await server.serve()  # returns on SIGTERM / SIGINT
        finally:
            await application.stop()


def main():
    configure_logging()

    if env == "local":
        build_application().run_polling()
    else:
        secret = compute_webhook_secret(token, webhook_secret)
        asyncio.run(run_web(build_application(webhook=True), secret))


if __name__ == "__main__":
    main()
