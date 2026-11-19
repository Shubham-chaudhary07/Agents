# step8.py  (step 7 + real LinkedIn posting)
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

from linkedin_api import post_to_linkedin

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
MODEL = "gemini-2.5-flash"  # use the model name that worked for you

client = genai.Client(http_options=types.HttpOptions(api_version="v1beta"))
FILE = "achievements.json"
HISTORY_FILE = "chat_history.json"
MAX_TURNS = 10
pending = {}


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
    pending.clear()
    pending.update(text=text, image_path=image_path)
    return "Sent to the user for confirmation with Yes/No buttons. It is NOT published yet."


def do_publish(post):
    """The real LinkedIn post. Runs only after you tap the Publish button."""
    url = post_to_linkedin(post["text"], post["image_path"])
    with open("published_posts.txt", "a", encoding="utf-8") as f:  # local copy as a backup
        f.write(f"--- {date.today()} ---\n{post['text']}\nImage: {post['image_path'] or 'none'}\n{url}\n\n")
    return url


FUNCTIONS = {
    "save_achievement": save_achievement,
    "list_achievements": list_achievements,
    "publish_post": publish_post,
}

# If you edited your SYSTEM prompt earlier, paste your version here instead.
SYSTEM = """You are Shubham's LinkedIn assistant, chatting on Telegram.
- When he tells you about a new achievement, save it with save_achievement, then offer to draft a post.
- If an image is attached, look at it and use only what is clearly visible or what he told you.
- Show him the full draft first.
- When he says to post, publish, or go ahead with a draft, you MUST call publish_post with the exact draft text
  (and the image path if one was attached). The app shows him Yes/No buttons, so do not ask again in text.
- Posts: humble, specific, no buzzwords, under 120 words, 3-5 hashtags.
- Never invent facts. If details are missing, ask first."""

CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM,
    tools=list(FUNCTIONS.values()),
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


# ---------- chat history that survives restarts ----------
def load_log():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_log():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def to_contents(entries):
    contents = []
    for t in entries:
        contents.append(types.Content(role="user", parts=[types.Part(text=t["user"])]))
        contents.append(types.Content(role="model", parts=[types.Part(text=t["model"])]))
    return contents


def make_chat():
    return client.chats.create(model=MODEL, config=CONFIG, history=to_contents(log))


log = load_log()
chat = make_chat()


def send(message):
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
def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram user id is {update.effective_user.id}. "
        "Put it in .env as OWNER_ID=... and restart the bot."
    )


async def achievements_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    await update.message.reply_text(list_achievements())


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat
    if not is_owner(update):
        return
    log.clear()
    save_log()
    pending.clear()
    chat = make_chat()
    await update.message.reply_text("Chat memory cleared. Your saved achievements are untouched.")


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    msg = update.message
    text = msg.text or msg.caption or ""
    log_text = text

    if msg.photo:
        os.makedirs("images", exist_ok=True)
        path = f"images/{msg.message_id}.jpg"
        tg_file = await msg.photo[-1].get_file()
        await tg_file.download_to_drive(path)
        with open(path, "rb") as f:
            image_part = types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")
        content = [image_part, f"[Image attached, path: {path}]\n{text}"]
        log_text = f"[Photo attached, path: {path}]\n{text}"
    else:
        content = text

    try:
        reply = await asyncio.to_thread(send, content)
    except Exception as e:
        await msg.reply_text(f"Error: {e}")
        return

    reply = reply or "(no reply)"
    await msg.reply_text(reply)

    log.append({"user": log_text, "model": reply})
    del log[:-MAX_TURNS]
    save_log()

    if pending:
        visibility = os.environ.get("LINKEDIN_VISIBILITY", "CONNECTIONS")
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Publish", callback_data="yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="no"),
        ]])
        await msg.reply_text(
            f"Publish this to LinkedIn? (visibility: {visibility})\n\n" + pending["text"],
            reply_markup=buttons,
        )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != OWNER_ID:
        return
    await q.answer()

    if q.data == "yes" and pending:
        post = dict(pending)
        pending.clear()
        await q.edit_message_text("Publishing...")
        try:
            url = await asyncio.to_thread(do_publish, post)
            await q.edit_message_text(f"Published ✅\n{url}")
        except Exception as e:
            pending.update(post)  # keep it so you can tap Publish again after fixing the problem
            await q.edit_message_text(f"LinkedIn error: {e}")
    else:
        pending.clear()
        await q.edit_message_text("Cancelled. Tell me what to change.")


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("achievements", achievements_cmd))
app.add_handler(CommandHandler("clear", clear_cmd))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle))

print(f"Bot running with {len(log)} remembered exchanges. Press Ctrl+C to stop.")
app.run_polling()