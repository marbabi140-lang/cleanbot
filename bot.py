import os
import re
import telebot
import yt_dlp
import time

TOKEN = os.getenv("8581157031:AAGXor8zitheavNkz0i9AWFw6pKFKm2Vodw")
bot = telebot.TeleBot(TOKEN)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URL_REGEX = r"https?://\S+"

def get_url(text):
    match = re.search(URL_REGEX, text or "")
    return match.group(0) if match else None


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Send me a video link (YouTube / TikTok / Instagram)")


def download(url):
    filename = f"{DOWNLOAD_DIR}/{int(time.time())}.mp4"

    ydl_opts = {
        "outtmpl": filename,
        "format": "best",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    return filename


@bot.message_handler(func=lambda m: True)
def handle(message):
    url = get_url(message.text)

    if not url:
        bot.reply_to(message, "❌ لینک معتبر نیست")
        return

    msg = bot.reply_to(message, "⏳ در حال دانلود...")

    try:
        file_path = download(url)

        with open(file_path, "rb") as f:
            bot.send_video(message.chat.id, f)

        os.remove(file_path)

        bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(
            f"❌ خطا:\n{str(e)}",
            message.chat.id,
            msg.message_id
        )


print("Bot running...")
bot.infinity_polling()
