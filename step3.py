# step3.py
import json
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

client = genai.Client()

FILE = "achievements.json"


def _load():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_achievement(title: str, details: str) -> str:
    """Save a new achievement (hackathon result, certificate, project milestone, etc.).

    Args:
        title: Short name of the achievement, e.g. "Top 10 at VisionX Hackathon".
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


SYSTEM = """You are Shubham's LinkedIn assistant.
- When he tells you about a new achievement, save it with save_achievement, then offer to draft a LinkedIn post.
- When he asks what he has done so far, use list_achievements.
- Posts: humble, specific, no buzzwords, under 120 words, 3-5 hashtags.
- Never invent facts. If details are missing, ask first."""

chat = client.chats.create(
    model="gemini-2.5-flash",  # use the model name that worked for you
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[save_achievement, list_achievements],  # just pass the functions
    ),
)

print("LinkedIn agent ready. Type 'quit' to exit.\n")

while True:
    user_text = input("You: ")
    if user_text.strip().lower() == "quit":
        break
    try:
        response = chat.send_message(user_text)
        print("\nAgent:", response.text, "\n")
    except Exception as e:
        print("\nError:", e, "\n")