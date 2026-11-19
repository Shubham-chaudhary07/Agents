# step6.py
import asyncio
import json
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # only this Telegram user can use the bot

client = genai.Client(http_options=types.HttpOptions(api_version="v1beta"))
FILE = "achievements.json"
pending = {}  # a post waiting for your button press


# ---------- tools ----------
def _load():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_achievement(title: str, details: str) -> str:
    """Save a new achievement (hackathon result, certificate, project milestone, etc.).

    Args:
        title: Short name of the achievement.
        details: What happened, the project, the team, anything specific.
    """
    items = _load()
    items.append({"title": title, "details": details, "date": str(date.today())})
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    return f"Saved: {title}"


def list_achievements() -> str:
    """List all achievements saved so far."""
    items = _load()
    if not items:
        return "No achievements saved yet."
    return "\n".join(f"- {i['date']}: {i['title']} ({i['details']})" for i in items)


def publish_post(text: str, image_path: str = "") -> str:
    """Request publishing of the final post when the user clearly says to post a draft.

    Args:
        text: The exact final post text.
        image_path: Path of the attached image to include, or empty if none.
    """
    # Does NOT publish. It only queues the post; the user approves with a button.
    pending.clear()
    pending.update(text=text, image_path=image_path)
    return "Sent to the user for confirmation with Yes/No buttons. It is NOT published yet."


def do_publish(post):
    # Stub for now. A later step will call the LinkedIn API.
    with open("published_posts.txt", "a", encoding="utf-8") as f:
        f.write(f"--- {date.today()} ---\n{post['text']}\nImage: {post['image_path'] or 'none'}\n\n")


FUNCTIONS = {
    "save_achievement": save_achievement,
    "list_achievements": list_achievements,
    "publish_post": publish_post,
}

SYSTEM = """You are Shubham's LinkedIn assistant, chatting on Telegram.
- When he tells you about a new achievement, save it with save_achievement, then offer to draft a post.
- If an image is attached, look at it and use only what is clearly visible or what he told you.
- Show him the full draft first.
- When he says to post, publish, or go ahead with a draft, you MUST call publish_post with the exact draft text
  (and the image path if one was attached). The app shows him Yes/No buttons, so do not ask again in text.
- Posts: humble, specific, no buzzwords, under 120 words, 3-5 hashtags.
- Never invent facts. If details are missing, ask first."""

chat = client.chats.create(
    model="gemini-2.5-flash",  # use the model name that worked for you
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=list(FUNCTIONS.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    ),
)


def send(message):
    """Same loop as step 5, minus input(): approval now happens via Telegram buttons."""
    response = chat.send_message(message)
    for _ in range(5):
        if not response.function_calls:
            return response.text
        parts = []
        for call in response.function_calls:
            print(f"[tool] {call.name}")
            result = FUNCTIONS[call.name](**dict(call.args))
            parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))
        response = chat.send_message(parts)
    return "Stopped: too many tool steps."


# ---------- Telegram handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram user id is {update.effective_user.id}. "
        "Put it in .env as OWNER_ID=... and restart the bot."
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return  # ignore everyone else
    msg = update.message
    text = msg.text or msg.caption or ""

    if msg.photo:
        os.makedirs("images", exist_ok=True)
        path = f"images/{msg.message_id}.jpg"
        tg_file = await msg.photo[-1].get_file()
        await tg_file.download_to_drive(path)
        with open(path, "rb") as f:
            image_part = types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")
        content = [image_part, f"[Image attached, path: {path}]\n{text}"]
    else:
        content = text

    try:
        reply = await asyncio.to_thread(send, content)  # run the blocking Gemini call off the event loop
    except Exception as e:
        await msg.reply_text(f"Error: {e}")
        return

    await msg.reply_text(reply or "(no reply)")

    if pending:
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Publish", callback_data="yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="no"),
        ]])
        await msg.reply_text("Publish this post?\n\n" + pending["text"], reply_markup=buttons)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != OWNER_ID:
        return
    await q.answer()
    if q.data == "yes" and pending:
        do_publish(dict(pending))
        pending.clear()
        await q.edit_message_text("Published ✅ (saved to published_posts.txt)")
    else:
        pending.clear()
        await q.edit_message_text("Cancelled. Tell me what to change.")


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle))

print("Bot running. Press Ctrl+C to stop.")
app.run_polling()