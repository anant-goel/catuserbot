import asyncio
import os
import threading

from flask import Flask

import userbot
from userbot import BOTLOG_CHATID, PM_LOGGER_GROUP_ID
from userbot.helpers.uptime_pinger import start_uptime_pinger
from userbot.web import register_web_routes

from .Config import Config
from .core.logger import logging
from .core.session import catub
from .utils import (
    add_bot_to_logger_group,
    install_externalrepo,
    load_plugins,
    setup_bot,
    startupmessage,
    verifyLoggerGroup,
)

LOGS = logging.getLogger("CatUserbot")

LOGS.info(userbot.__copyright__)
LOGS.info(f"Licensed under the terms of the {userbot.__license__}")

cmdhr = Config.COMMAND_HAND_LER

# Flask app
app = Flask(__name__)


async def startup_process():
    """Handle startup process with error handling"""
    try:
        await verifyLoggerGroup()
        await load_plugins("plugins")
        await load_plugins("assistant")

        LOGS.info("=" * 76)
        LOGS.info("||               Yay your userbot is officially working.!!!")
        LOGS.info(f"||   Congratulation, now type {cmdhr}alive to see message if catub is live")
        LOGS.info("||   If you need assistance, head to https://t.me/catuserbot_support")
        LOGS.info("=" * 76)

        await verifyLoggerGroup()
        await add_bot_to_logger_group(BOTLOG_CHATID)

        if PM_LOGGER_GROUP_ID != -100:
            await add_bot_to_logger_group(PM_LOGGER_GROUP_ID)

        await startupmessage()

    except Exception as e:
        LOGS.error(f"Error in startup process: {e}")
        raise


async def externalrepo():
    """Handle external repository installation"""
    try:
        string = "<b>Your external repo plugins have imported.</b>\n\n"

        if hasattr(Config, "EXTERNAL_REPO") and Config.EXTERNAL_REPO:
            data = await install_externalrepo(Config.EXTERNAL_REPO, Config.EXTERNAL_REPOBRANCH, "xtraplugins")
            string += f"<b>➜ Repo:</b> <a href='{data[0]}'><b>{data[1]}</b></a>\n"
            string += f"<b>     • Imported Plugins:</b> <code>{data[2]}</code>\n"
            string += f"<b>     • Failed to Import:</b> <code>{', '.join(data[3])}</code>\n\n"

        if hasattr(Config, "BADCAT") and Config.BADCAT:
            data = await install_externalrepo(Config.BADCAT_REPO, Config.BADCAT_REPOBRANCH, "badcatext")
            string += f"<b>➜ Repo:</b> <a href='{data[0]}'><b>{data[1]}</b></a>\n"
            string += f"<b>     • Imported Plugins:</b> <code>{data[2]}</code>\n"
            string += f"<b>     • Failed to Import:</b> <code>{', '.join(data[3])}</code>\n\n"

        if hasattr(Config, "VCMODE") and Config.VCMODE:
            data = await install_externalrepo(Config.VC_REPO, Config.VC_REPOBRANCH, "catvc")
            string += f"<b>➜ Repo:</b> <a href='{data[0]}'><b>{data[1]}</b></a>\n"
            string += f"<b>     • Imported Plugins:</b> <code>{data[2]}</code>\n"
            string += f"<b>     • Failed to Import:</b> <code>{', '.join(data[3])}</code>\n\n"

        if "Imported Plugins" in string:
            await catub.tgbot.send_message(BOTLOG_CHATID, string, parse_mode="html")

    except Exception as e:
        LOGS.error(f"Error in external repo installation: {e}")


async def init_all():
    """Initialize all components"""
    try:
        await setup_bot()
        await startup_process()
        await externalrepo()
        register_web_routes(app)
    except Exception as e:
        LOGS.error(f"Error in initialization: {e}")
        raise


def run_flask():
    """Run Flask server"""
    try:
        # Quiet werkzeug's "development server" warning and per-request log spam.
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        port = int(os.environ.get("PORT", "10000"))
        LOGS.info(f"Starting Flask server on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        LOGS.error(f"Flask server error: {e}")


async def main():
    """Main function"""
    scheduler = None
    try:
        LOGS.info("Starting Userbot")
        await init_all()
        LOGS.info("TG Bot Startup Completed")

        # Start uptime pinger
        scheduler = start_uptime_pinger()

        # Start Flask server in background thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        LOGS.info("Flask server started in background")

        # Keep bot running
        await catub.run_until_disconnected()

    except Exception as e:
        LOGS.error(f"Error in main: {e}")
        raise
    finally:
        # Cleanup
        if scheduler:
            scheduler.shutdown()
        LOGS.info("Bot stopped.")


if __name__ == "__main__":
    import sys

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())

    except (KeyboardInterrupt, SystemExit):
        LOGS.info("Bot stopped.")
        sys.exit()
