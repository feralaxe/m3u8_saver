from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .access import AccessPolicy, AccessStore
from .config import Settings, load_settings
from .discovery import VideoCandidate, discover_videos
from .ffmpeg import FfmpegError, download_playlist
from .logging_setup import configure_logging


URL_PATTERN = re.compile(r"https?://\S+|(?:[\w-]+\.)+[\w-]{2,}\S*", re.IGNORECASE)
LOGGER = logging.getLogger(__name__)


def _safe_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return url[:200]
    return parsed._replace(query="", fragment="").geturl()[:200]


class BotState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = AccessStore(settings.database_path)
        self.access = AccessPolicy(
            self.store,
            settings.admin_user_ids,
            settings.permanent_allowed_user_ids,
        )
        self.candidates: dict[str, VideoCandidate] = {}


def _state(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return context.application.bot_data["state"]


def _user_id(update: Update) -> int | None:
    return update.effective_user.id if update.effective_user else None


async def _deny(update: Update) -> None:
    message = update.effective_message
    if message:
        await message.reply_text(
            "Access is not active for your Telegram account. Send /id to get your user id."
        )


def _extract_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    return match.group(0).rstrip(".,)") if match else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update)
    state = _state(context)
    allowed = user_id is not None and state.access.can_use(user_id)
    LOGGER.info("start command user_id=%s allowed=%s", user_id, allowed)
    await update.effective_message.reply_text(
        "Send me a page URL or direct .m3u8 URL. "
        f"Your access is {'active' if allowed else 'not active'}."
    )


async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    LOGGER.info("id command user_id=%s", user.id)
    await update.effective_message.reply_text(f"Your Telegram user id: {user.id}")


async def grant_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    sender = _user_id(update)
    if sender is None or not state.access.is_admin(sender):
        LOGGER.warning("grant denied sender=%s", sender)
        await _deny(update)
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("Usage: /grantdays <user_id> <days>")
        return
    target_id = int(context.args[0])
    days = int(context.args[1])
    expires_at = state.store.grant_days(target_id, days, note=f"granted by {sender}")
    LOGGER.info("subscription granted sender=%s target=%s days=%s", sender, target_id, days)
    await update.effective_message.reply_text(
        f"Subscription for {target_id} is active until {expires_at.isoformat()}."
    )


async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    sender = _user_id(update)
    if sender is None or not state.access.is_admin(sender):
        LOGGER.warning("revoke denied sender=%s", sender)
        await _deny(update)
        return
    if len(context.args) < 1:
        await update.effective_message.reply_text("Usage: /revoke <user_id>")
        return
    target_id = int(context.args[0])
    state.store.revoke(target_id)
    LOGGER.info("subscription revoked sender=%s target=%s", sender, target_id)
    await update.effective_message.reply_text(f"Subscription revoked for {target_id}.")


async def allow_forever(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    sender = _user_id(update)
    if sender is None or not state.access.is_admin(sender):
        LOGGER.warning("allow_forever denied sender=%s", sender)
        await _deny(update)
        return
    if len(context.args) < 1:
        await update.effective_message.reply_text("Usage: /allowforever <user_id>")
        return
    target_id = int(context.args[0])
    state.store.allow_forever(target_id, note=f"allowed by {sender}")
    LOGGER.info("permanent access granted sender=%s target=%s", sender, target_id)
    await update.effective_message.reply_text(f"{target_id} can now use the bot permanently.")


async def unallow_forever(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    sender = _user_id(update)
    if sender is None or not state.access.is_admin(sender):
        LOGGER.warning("unallow_forever denied sender=%s", sender)
        await _deny(update)
        return
    if len(context.args) < 1:
        await update.effective_message.reply_text("Usage: /unallowforever <user_id>")
        return
    target_id = int(context.args[0])
    state.store.unallow_forever(target_id)
    LOGGER.info("permanent access removed sender=%s target=%s", sender, target_id)
    await update.effective_message.reply_text(f"Permanent access removed for {target_id}.")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    user_id = _user_id(update)
    if user_id is None or not state.access.can_use(user_id):
        LOGGER.warning("url rejected user_id=%s reason=not_allowed", user_id)
        await _deny(update)
        return

    text = update.effective_message.text or ""
    url = _extract_url(text)
    if not url:
        LOGGER.info("message without url user_id=%s", user_id)
        await update.effective_message.reply_text("Please send a URL.")
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    LOGGER.info("discover start user_id=%s url=%s", user_id, _safe_url_for_log(url))
    try:
        candidates = await discover_videos(
            url,
            timeout=state.settings.http_timeout_seconds,
            user_agent=state.settings.default_user_agent,
        )
    except Exception as exc:
        LOGGER.exception("discover failed user_id=%s url=%s", user_id, _safe_url_for_log(url))
        await update.effective_message.reply_text(f"Could not parse that URL: {exc}")
        return

    if not candidates:
        LOGGER.info("discover none user_id=%s url=%s", user_id, _safe_url_for_log(url))
        await update.effective_message.reply_text("No .m3u8 playlists were found on that page.")
        return

    LOGGER.info(
        "discover complete user_id=%s url=%s candidates=%s",
        user_id,
        _safe_url_for_log(url),
        len(candidates),
    )

    keyboard = []
    for candidate in candidates[:20]:
        key = f"{user_id}:{len(state.candidates)}"
        state.candidates[key] = candidate
        keyboard.append([InlineKeyboardButton(candidate.title[:64], callback_data=f"download:{key}")])

    await update.effective_message.reply_text(
        "Found these videos:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def download_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    user_id = _user_id(update)
    if user_id is None or not state.access.can_use(user_id):
        LOGGER.warning("download rejected user_id=%s reason=not_allowed", user_id)
        await query.edit_message_text("Access is not active for your Telegram account.")
        return

    _, key = query.data.split(":", maxsplit=1)
    owner_id, _ = key.split(":", maxsplit=1)
    if int(owner_id) != user_id:
        LOGGER.warning("download rejected user_id=%s reason=wrong_owner owner=%s", user_id, owner_id)
        await query.edit_message_text("This video choice belongs to another user.")
        return

    candidate = state.candidates.get(key)
    if not candidate:
        LOGGER.info("download rejected user_id=%s reason=expired_choice", user_id)
        await query.edit_message_text("This video choice expired. Please send the URL again.")
        return

    await query.edit_message_text(f"Downloading {candidate.title}. This may take a while.")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    work_dir = Path(tempfile.mkdtemp(prefix="m3u8-", dir=state.settings.temp_dir))
    output_path = work_dir / "video.mp4"
    LOGGER.info(
        "download start user_id=%s playlist=%s work_dir=%s",
        user_id,
        _safe_url_for_log(candidate.playlist_url),
        work_dir,
    )
    try:
        accel_name = await download_playlist(
            playlist_url=candidate.playlist_url,
            output_path=output_path,
            user_agent=state.settings.default_user_agent,
            timeout_seconds=state.settings.ffmpeg_timeout_seconds,
            max_video_bytes=state.settings.max_video_bytes,
            transcode=state.settings.transcode_video,
            preferred_accel=state.settings.preferred_accel,
        )
        output_size = output_path.stat().st_size
        LOGGER.info(
            "download complete user_id=%s mode=%s bytes=%s",
            user_id,
            accel_name,
            output_size,
        )
        state.store.record_download(user_id, candidate.source_url, candidate.playlist_url)
        with output_path.open("rb") as video_file:
            LOGGER.info("upload start user_id=%s bytes=%s", user_id, output_size)
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=video_file,
                filename="video.mp4",
                caption=f"Done. Processing mode: {accel_name}.",
                read_timeout=state.settings.ffmpeg_timeout_seconds,
                write_timeout=state.settings.ffmpeg_timeout_seconds,
            )
        LOGGER.info("upload complete user_id=%s bytes=%s", user_id, output_size)
    except FfmpegError as exc:
        LOGGER.exception("ffmpeg failed user_id=%s playlist=%s", user_id, _safe_url_for_log(candidate.playlist_url))
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"Download failed: {exc}")
    except Exception as exc:
        LOGGER.exception("download/upload failed user_id=%s", user_id)
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"Upload failed: {exc}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        state.candidates.pop(key, None)
        LOGGER.info("cleanup complete user_id=%s work_dir=%s", user_id, work_dir)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Telegram handler error", exc_info=context.error)


def build_application(settings: Settings) -> Application:
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["state"] = BotState(settings)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", user_id))
    application.add_handler(CommandHandler("grantdays", grant_days))
    application.add_handler(CommandHandler("revoke", revoke))
    application.add_handler(CommandHandler("allowforever", allow_forever))
    application.add_handler(CommandHandler("unallowforever", unallow_forever))
    application.add_handler(CallbackQueryHandler(download_choice, pattern=r"^download:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    application = build_application(settings)
    LOGGER.info(
        "starting m3u8 saver bot data_dir=%s temp_dir=%s log_file=%s transcode=%s accel=%s",
        settings.data_dir,
        settings.temp_dir,
        settings.log_file,
        settings.transcode_video,
        settings.preferred_accel,
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)
