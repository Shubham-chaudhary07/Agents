# step7.py  (step 6 + remembers chat after restart + /achievements and /clear commands)
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
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
MODEL = "gemini-2.5-flash"  # use the model name that worked for you

client = genai.Client(http_options=types.HttpOptions(api_version="v1beta"))
FILE = "achievements.json"
HISTORY_FILE = "chat_history.json"
MAX_TURNS = 10  # remember the last 10 exchanges
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
    # Still a stub: saves to a file. Real LinkedIn posting can be added later.
    with open("published_posts.txt", "a", encoding="utf-8") as f:
        f.write(f"--- {date.today()} ---\n{post['text']}\nImage: {post['image_path'] or 'none'}\n\n")


FUNCTIONS = {
    "save_achievement": save_achievement,
    "list_achievements": list_achievements,
    "publish_post": publish_post,
}

SYSTEM =SYSTEM = """You are Shubham's LinkedIn assistant, chatting on Telegram.

ABOUT HIM
- B.Tech CSE student, Python/Java/web developer, active in hackathons and open source.
- Audience: recruiters, other students, developers.

STYLE
- First line must grab attention with a specific fact, not "I'm excited to share".
- Short paragraphs, simple English, first person, honest, no hype.
- Mention what we built, what I learned, and one thank-you. Max 120 words.
- 3-5 hashtags at the end. At most 1-2 emojis.
- Avoid: "thrilled", "humbled", "game-changer", "journey", "synergy".

EXAMPLE OF A POST I LIKE (copy the tone, not the words):
[paste one real LinkedIn post that you or someone else wrote and liked]

RULES
- When he tells you about a new achievement, save it with save_achievement, then offer to draft a post.
- If an image is attached, use only what is clearly visible or what he told you.
- Show the full draft first. Never invent facts (team size, rank, numbers). If details are missing, ask.
- When he says to post, publish, or go ahead with a draft, you MUST call publish_post with the exact draft text
(and the image path if one was attached). The app shows him Yes/No buttons, so do not ask again in text."""

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
        return []  # damaged file: start fresh


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


log = load_log()  # list of {"user": ..., "model": ...}
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

    # Remember this exchange (only after it succeeded)
    log.append({"user": log_text, "model": reply})
    del log[:-MAX_TURNS]
    save_log()

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
app.add_handler(CommandHandler("achievements", achievements_cmd))
app.add_handler(CommandHandler("clear", clear_cmd))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle))

print(f"Bot running with {len(log)} remembered exchanges. Press Ctrl+C to stop.")
app.run_polling()