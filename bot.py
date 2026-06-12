import os
import re
import uuid
import time
import asyncio
import yt_dlp
import requests


from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = "8581157031:AAEi_-ZtNAm5zIxmUwxOA-SF6CkKxNASpzo"
CHANNELS = ["@hexchanell", "@neodlgroup",]

download_queue = asyncio.Queue()
user_last_time = {}

COOLDOWN = 2

# 🔥 concurrency + cache
MAX_WORKERS = 12
DOWNLOAD_LIMIT = asyncio.Semaphore(8)
download_cache = {}

LOADING_STICKER = "CAACAgQAAxkBAAERXcNqKQ2u3Ry7LBKXjrDsNHxt3tzcugACKSAAAtfxSFFgJWZLGKOHWDsE"

CAPTION = '🀄️ download by <a href="https://t.me/DLNeoBot">NEODL</a>'


# ───── URL CHECK ─────
def is_valid_url(text: str):
    return bool(re.match(r"https?://\S+", text))


# ───── CLEAN URL FOR CACHE ─────
def get_cache_key(url):
    return url.strip().split("?")[0]


# ───── RESOLVE ─────
def resolve_url(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=10)
        return r.url
    except:
        return url


# ───── MEMBERSHIP ─────
async def is_member(user_id, bot):
    try:
        for ch in CHANNELS:
            m = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if m.status not in ["member", "administrator", "creator"]:
                return False
        return True
    except:
        return False


# ───── START ─────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_member(user.id, context.bot):
        keyboard = [
            [InlineKeyboardButton("📢 کانال اول", url="https://t.me/hexchanell")],
            [InlineKeyboardButton("📢 کانال دوم", url="https://t.me/neodlgroup")],
            [InlineKeyboardButton("📢 کانال سوم", url="https://t.me/neodlchanel")],
            [InlineKeyboardButton("✅ بررسی عضویت", callback_data="check")]
        ]

        await update.message.reply_text(
            "⚠️ لطفا لینک خود را ارسال کنید",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await update.message.reply_text("👋 خوش آمدید\n📥 لینک خود را ارسال کنید")


# ───── CHECK ─────
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if await is_member(q.from_user.id, context.bot):
        await q.message.edit_text("✅ عضویت تایید شد\n📥 لینک خود را بفرستید")
    else:
        await q.answer("❌ هنوز عضو کانال‌ها نیستی", show_alert=True)


# ───── MODE ─────
def detect_mode(url):
    if "soundcloud.com" in url.lower():
        return "audio"
    return "video"


# ───── YT-DLP OPT ─────
def build_ydl_options(file_path, mode):
    base = {
        "outtmpl": file_path.replace(".mp4", "").replace(".mp3", "") + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "continuedl": True,
        "nopart": True,

        "concurrent_fragment_downloads": 10,

        "http_headers": {
            "User-Agent": "Mozilla/5.0 Chrome/122"
        }
    }

    if mode == "audio":
        return {
            **base,
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }

    return {
        **base,
        "format": "bestvideo*+bestaudio/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }


# ───── WORKER ─────
async def download_worker(app):
    while True:
        update, user, url = await download_queue.get()

        msg = await update.message.reply_sticker(LOADING_STICKER)

        try:
            os.makedirs("downloads", exist_ok=True)
            file_id = str(uuid.uuid4())

            mode = detect_mode(url)
            file_path = f"downloads/{file_id}.mp4" if mode == "video" else f"downloads/{file_id}.mp3"

            cache_key = get_cache_key(url)

            # 🔥 CACHE CHECK (NO DUPLICATE DOWNLOAD)
            if cache_key in download_cache:
                cached_file = download_cache[cache_key]

                if os.path.exists(cached_file):
                    if cached_file.endswith(".mp3"):
                        with open(cached_file, "rb") as f:
                            await update.message.reply_audio(audio=f, caption=CAPTION, parse_mode="HTML")
                    else:
                        with open(cached_file, "rb") as f:
                            await update.message.reply_video(video=f, caption=CAPTION, parse_mode="HTML")

                    await msg.delete()
                    download_queue.task_done()
                    continue
                else:
                    download_cache.pop(cache_key, None)

            ydl_opts = build_ydl_options(file_path, mode)

            async with DOWNLOAD_LIMIT:
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(
                    None,
                    lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True)
                )
                downloaded = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info)

            if mode == "audio":
                final_path = os.path.splitext(downloaded)[0] + ".mp3"
                with open(final_path, "rb") as f:
                    await update.message.reply_audio(audio=f, caption=CAPTION, parse_mode="HTML")
            else:
                final_path = downloaded
                with open(final_path, "rb") as f:
                    await update.message.reply_video(video=f, caption=CAPTION, parse_mode="HTML")

            download_cache[cache_key] = final_path

            os.remove(final_path)

            try:
                await msg.delete()
            except:
                pass

        except Exception as e:
            await msg.edit_text(f"❌ خطا:\n{str(e)[:200]}")

        download_queue.task_done()


# ───── ANTI SPAM ─────
def anti_spam(user_id):
    now = time.time()
    last = user_last_time.get(user_id, 0)

    if now - last < COOLDOWN:
        return True

    user_last_time[user_id] = now
    return False


# ───── HANDLER ─────
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if not await is_member(user.id, context.bot):
        await update.message.reply_text("⚠️ لطفا لینک خود را ارسال کنید")
        return

    if not is_valid_url(text):
        await update.message.reply_text("❌ لینک اشتباهه")
        return

    if anti_spam(user.id):
        await update.message.reply_text("⛔ کمی صبر کن")
        return

    await download_queue.put((update, user, resolve_url(text)))


# ───── MAIN ─────
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_membership, pattern="check"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))

    async def post_init(app):
        for _ in range(12):
            asyncio.create_task(download_worker(app))

    app.post_init = post_init

    print("🚀 BOT READY (CACHE + HIGH SPEED + VPS MODE)")
    app.run_polling()


if __name__ == "__main__":
    main()
