"""
Changer Club AI Content Factory — Telegram bot (aiogram 3.x).

Entry point: ``python bot.py``

Scenarios
---------
1. User uploads photos -> bot asks for topic -> generates carousel.
2. ``/gallery`` -> user picks photos from local library -> topic -> carousel.

Commands
--------
/start  — welcome + instructions
/gallery — choose photos from the on-disk library
/reset  — clear current session
/help   — short reference
"""

import asyncio
import glob
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InputMediaPhoto,
    Message,
)

from config import BOT_TOKEN, MAX_SLIDES, OUTPUT_DIR, PHOTOS_DIR
from generator import generate_slide_texts
from image_maker import create_slide
from photo_selector import select_photos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
dp = Dispatcher()
dp.include_router(router)

# ------------------------------------------------------------------
# Session state (in-memory, per chat_id)
# ------------------------------------------------------------------

_sessions: dict[int, dict[str, Any]] = {}


def _get_session(chat_id: int) -> dict[str, Any]:
    if chat_id not in _sessions:
        _sessions[chat_id] = {
            "photos": [],
            "source": None,
            "waiting_topic": False,
            "gallery_files": [],
            "auto_mode": False,
        }
    return _sessions[chat_id]


def _reset_session(chat_id: int) -> None:
    sess = _sessions.pop(chat_id, None)
    if sess:
        for p in sess.get("photos", []):
            try:
                if p.startswith(tempfile.gettempdir()):
                    os.remove(p)
            except OSError:
                pass


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "<b>Changer Club — AI Content Factory</b>\n\n"
        "Send me photos from an event and I'll create Instagram carousel slides.\n\n"
        "<b>How to use:</b>\n"
        "1. Send 1-10 photos (as images or files)\n"
        "2. Type the topic / theme for the post\n"
        "3. Get ready-to-post carousel slides\n\n"
        "<b>Commands:</b>\n"
        "/auto — write a topic, AI picks the best photos from the library\n"
        "/gallery — pick photos from the library manually\n"
        "/reset — clear current session\n"
        "/help — quick reference"
    )


# ------------------------------------------------------------------
# /help
# ------------------------------------------------------------------

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Quick reference</b>\n\n"
        "• Send photos (up to 10) then type a topic\n"
        "• /auto — write a topic, AI picks the best photos\n"
        "• /gallery — browse on-disk photo library\n"
        "• /reset — discard photos & start over\n"
        "• Supported formats: JPG, PNG, WEBP"
    )


# ------------------------------------------------------------------
# /reset
# ------------------------------------------------------------------

@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    _reset_session(message.chat.id)
    await message.answer("Session cleared. Send new photos or use /gallery.")


# ------------------------------------------------------------------
# /auto
# ------------------------------------------------------------------

@router.message(Command("auto"))
async def cmd_auto(message: Message) -> None:
    sess = _get_session(message.chat.id)
    sess["photos"] = []
    sess["source"] = None
    sess["waiting_topic"] = False
    sess["auto_mode"] = True
    await message.answer(
        "Auto mode enabled.\n\n"
        "Type the carousel topic — I'll pick the best photos from the library.\n\n"
        "Example: <i>Reverse mentorship Monaco</i> or <i>Dubai founders session</i>"
    )


# ------------------------------------------------------------------
# /gallery
# ------------------------------------------------------------------

@router.message(Command("gallery"))
async def cmd_gallery(message: Message) -> None:
    photos_dir = Path(PHOTOS_DIR)
    if not photos_dir.exists():
        await message.answer("Photo library is empty.")
        return

    files = sorted(
        [f for f in photos_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")],
        key=lambda p: p.name,
    )
    if not files:
        await message.answer("No photos found in the library.")
        return

    sess = _get_session(message.chat.id)
    sess["gallery_files"] = files
    sess["source"] = "gallery"
    sess["photos"] = []
    sess["waiting_topic"] = False

    lines = ["<b>Photo library</b>\n"]
    for i, f in enumerate(files, 1):
        lines.append(f"  {i}. {f.name}")
    lines.append(f"\nSend numbers separated by commas (e.g. <code>1, 3, 5</code>) to select photos (max {MAX_SLIDES}).")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = "\n".join(lines[:50]) + f"\n\n... and {len(files) - 48} more. Send numbers to select."

    await message.answer(text)


# ------------------------------------------------------------------
# Photo handler (compressed Telegram photos)
# ------------------------------------------------------------------

@router.message(F.photo)
async def on_photo(message: Message) -> None:
    sess = _get_session(message.chat.id)

    if len(sess["photos"]) >= MAX_SLIDES:
        await message.answer(f"Maximum {MAX_SLIDES} photos reached. Now type the topic for your post.")
        return

    photo = message.photo[-1]  # highest resolution
    file = await bot.get_file(photo.file_id)
    tmp_path = os.path.join(tempfile.gettempdir(), f"changer_{photo.file_id}.jpg")

    await bot.download_file(file.file_path, tmp_path)
    sess["photos"].append(tmp_path)
    sess["source"] = "upload"
    sess["waiting_topic"] = True

    count = len(sess["photos"])
    await message.answer(
        f"Photo {count} received.\n"
        f"Send more photos or type the <b>topic/theme</b> for the post."
    )


# ------------------------------------------------------------------
# Document handler (original-quality image files)
# ------------------------------------------------------------------

@router.message(F.document)
async def on_document(message: Message) -> None:
    doc = message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await message.answer("Please send an image file (JPG, PNG, WEBP).")
        return

    sess = _get_session(message.chat.id)
    if len(sess["photos"]) >= MAX_SLIDES:
        await message.answer(f"Maximum {MAX_SLIDES} photos reached. Now type the topic for your post.")
        return

    ext = Path(doc.file_name or "photo.jpg").suffix or ".jpg"
    file = await bot.get_file(doc.file_id)
    tmp_path = os.path.join(tempfile.gettempdir(), f"changer_{doc.file_id}{ext}")

    await bot.download_file(file.file_path, tmp_path)
    sess["photos"].append(tmp_path)
    sess["source"] = "upload"
    sess["waiting_topic"] = True

    count = len(sess["photos"])
    await message.answer(
        f"Photo {count} received.\n"
        f"Send more photos or type the <b>topic/theme</b> for the post."
    )


# ------------------------------------------------------------------
# Text handler (topic input or gallery selection)
# ------------------------------------------------------------------

@router.message(F.text)
async def on_text(message: Message) -> None:
    text = message.text.strip()
    if text.startswith("/"):
        return

    sess = _get_session(message.chat.id)

    # Auto mode: no photos yet — select from library by topic
    if sess.get("auto_mode") and not sess["photos"]:
        await _handle_auto_topic(message, sess, text)
        return

    # Gallery number selection
    if sess["source"] == "gallery" and sess["gallery_files"] and not sess["waiting_topic"]:
        await _handle_gallery_selection(message, sess, text)
        return

    # Topic input
    if sess["photos"] and sess["waiting_topic"]:
        await _handle_topic(message, sess, text)
        return

    # No context
    await message.answer(
        "Send me photos first, use /gallery to pick manually, or /auto for AI selection."
    )


async def _handle_auto_topic(
    message: Message, sess: dict[str, Any], topic: str
) -> None:
    """Auto-select photos from library, then generate carousel."""
    chat_id = message.chat.id

    # Step 1: AI photo selection
    status_msg = await message.answer("Searching for the best photos in the library...")
    try:
        selected_paths, reasoning = await asyncio.to_thread(select_photos, topic)
    except ValueError as exc:
        await status_msg.edit_text(f"Error: {exc}")
        return
    except Exception as exc:
        logger.exception("Photo selection failed")
        await status_msg.edit_text(f"Photo selection error: {exc}")
        return

    n = len(selected_paths)
    await status_msg.edit_text(
        f"Selected {n} photos\n"
        f"<i>{reasoning}</i>\n\n"
        "Generating texts..."
    )

    # Step 2: generate texts with the selected photos
    try:
        slides_data = await generate_slide_texts(selected_paths, topic)
    except Exception as exc:
        logger.exception("Text generation failed")
        await status_msg.edit_text(f"Text generation error: {exc}")
        _reset_session(chat_id)
        return

    if len(slides_data) < len(selected_paths):
        slides_data.extend(
            [{"headline": "CHANGER CLUB", "subtitle": "", "caption": "", "hashtags": ""}]
            * (len(selected_paths) - len(slides_data))
        )

    # Step 3: render slides
    await status_msg.edit_text("Assembling slides...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_paths: list[str] = []
    for i, (photo_path, slide) in enumerate(zip(selected_paths, slides_data)):
        out_path = os.path.join(OUTPUT_DIR, f"slide_{chat_id}_{i + 1}.jpg")
        try:
            create_slide(
                input_path=photo_path,
                headline=slide.get("headline", "CHANGER CLUB"),
                subtitle=slide.get("subtitle", ""),
                output_path=out_path,
            )
            output_paths.append(out_path)
        except Exception as exc:
            logger.warning("Failed to render slide %d: %s", i + 1, exc)
            await message.answer(f"Skipped slide {i + 1}: {exc}")

    if not output_paths:
        await status_msg.edit_text("Could not render any slides.")
        _reset_session(chat_id)
        return

    # Step 4: send carousel
    await status_msg.edit_text("Sending carousel...")
    media_group: list[InputMediaPhoto] = []
    for i, path in enumerate(output_paths):
        photo_file = FSInputFile(path)
        if i == 0:
            short_caption = slides_data[0].get("caption", "")[:1024]
            media_group.append(InputMediaPhoto(media=photo_file, caption=short_caption))
        else:
            media_group.append(InputMediaPhoto(media=photo_file))

    try:
        await bot.send_media_group(chat_id=chat_id, media=media_group)
    except Exception as exc:
        logger.exception("Failed to send media group")
        await message.answer(f"Error sending carousel: {exc}")

    # Step 5: full caption + hashtags
    caption = slides_data[0].get("caption", "")
    hashtags = slides_data[0].get("hashtags", "")
    if caption or hashtags:
        full_text = ""
        if caption:
            full_text += f"<b>Caption:</b>\n{caption}\n\n"
        if hashtags:
            full_text += f"<b>Hashtags:</b>\n{hashtags}"
        if full_text:
            if len(full_text) > 4096:
                full_text = full_text[:4093] + "..."
            await message.answer(full_text)

    # Cleanup
    await status_msg.delete()
    for p in output_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    _reset_session(chat_id)
    await message.answer("Done! Send new photos, /gallery, or /auto for another post.")


async def _handle_gallery_selection(
    message: Message, sess: dict[str, Any], text: str
) -> None:
    """Parse comma-separated numbers and add corresponding gallery files."""
    try:
        indices = [int(x.strip()) for x in text.replace(" ", ",").split(",") if x.strip().isdigit()]
    except ValueError:
        await message.answer("Send numbers separated by commas, e.g. <code>1, 3, 5</code>")
        return

    if not indices:
        await message.answer("Send numbers separated by commas, e.g. <code>1, 3, 5</code>")
        return

    gallery = sess["gallery_files"]
    selected: list[str] = []
    for idx in indices:
        if 1 <= idx <= len(gallery):
            selected.append(str(gallery[idx - 1]))
        if len(selected) >= MAX_SLIDES:
            break

    if not selected:
        await message.answer("Invalid selection. Numbers must be between 1 and %d." % len(gallery))
        return

    sess["photos"] = selected
    sess["waiting_topic"] = True

    names = ", ".join(Path(p).name for p in selected)
    await message.answer(
        f"Selected {len(selected)} photo(s): <code>{names}</code>\n\n"
        "Now type the <b>topic/theme</b> for the post."
    )


async def _handle_topic(message: Message, sess: dict[str, Any], topic: str) -> None:
    """Generate slide texts with Claude, render images, and send the carousel."""
    photos = sess["photos"][: MAX_SLIDES]
    chat_id = message.chat.id

    # --- Step 1: Generate texts ---
    status_msg = await message.answer("Generating texts...")
    try:
        slides_data = await generate_slide_texts(photos, topic)
    except Exception as exc:
        logger.exception("Text generation failed")
        await status_msg.edit_text(f"Text generation error: {exc}")
        return

    if len(slides_data) < len(photos):
        slides_data.extend(
            [{"headline": "CHANGER CLUB", "subtitle": "", "caption": "", "hashtags": ""}]
            * (len(photos) - len(slides_data))
        )

    # --- Step 2: Render slides ---
    await status_msg.edit_text("Assembling slides...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_paths: list[str] = []
    for i, (photo_path, slide) in enumerate(zip(photos, slides_data)):
        out_path = os.path.join(OUTPUT_DIR, f"slide_{chat_id}_{i + 1}.jpg")
        try:
            create_slide(
                input_path=photo_path,
                headline=slide.get("headline", "CHANGER CLUB"),
                subtitle=slide.get("subtitle", ""),
                output_path=out_path,
            )
            output_paths.append(out_path)
        except Exception as exc:
            logger.warning("Failed to render slide %d: %s", i + 1, exc)
            await message.answer(f"Skipped slide {i + 1}: {exc}")

    if not output_paths:
        await status_msg.edit_text("Could not render any slides.")
        _reset_session(chat_id)
        return

    # --- Step 3: Send carousel ---
    await status_msg.edit_text("Sending carousel...")
    media_group: list[InputMediaPhoto] = []
    for i, path in enumerate(output_paths):
        photo_file = FSInputFile(path)
        if i == 0:
            short_caption = slides_data[0].get("caption", "")[:1024]
            media_group.append(InputMediaPhoto(media=photo_file, caption=short_caption))
        else:
            media_group.append(InputMediaPhoto(media=photo_file))

    try:
        await bot.send_media_group(chat_id=chat_id, media=media_group)
    except Exception as exc:
        logger.exception("Failed to send media group")
        await message.answer(f"Error sending carousel: {exc}")

    # --- Step 4: Full caption + hashtags ---
    caption = slides_data[0].get("caption", "")
    hashtags = slides_data[0].get("hashtags", "")
    if caption or hashtags:
        full_text = ""
        if caption:
            full_text += f"<b>Caption:</b>\n{caption}\n\n"
        if hashtags:
            full_text += f"<b>Hashtags:</b>\n{hashtags}"
        if full_text:
            if len(full_text) > 4096:
                full_text = full_text[:4093] + "..."
            await message.answer(full_text)

    # --- Cleanup ---
    await status_msg.delete()
    for p in output_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    _reset_session(chat_id)
    await message.answer("Done! Send new photos or /gallery for another post.")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

async def main() -> None:
    logger.info("Starting Changer Club bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
