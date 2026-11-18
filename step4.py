# step4.py
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


def publish_post(text: str) -> str:
    """Publish the final approved post text to LinkedIn.
    Only call this after the user has seen the full draft and clearly said to post it.

    Args:
        text: The exact final post text.
    """
    # Stub for now. In a later step this will call the LinkedIn API.
    with open("published_posts.txt", "a", encoding="utf-8") as f:
        f.write(f"--- {date.today()} ---\n{text}\n\n")
    return "Post published successfully (saved to published_posts.txt)."


# Functions the loop is allowed to run, looked up by name
FUNCTIONS = {
    "save_achievement": save_achievement,
    "list_achievements": list_achievements,
    "publish_post": publish_post,
}

SYSTEM = """You are Shubham's LinkedIn assistant.
- When he tells you about a new achievement, save it with save_achievement, then offer to draft a post.
- Show him the full draft first. Call publish_post only after he clearly asks to post that draft.
- Posts: humble, specific, no buzzwords, under 120 words, 3-5 hashtags.
- Never invent facts. If details are missing, ask first."""

chat = client.chats.create(
    model="gemini-2.5-flash",  # use the model name that worked for you
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=list(FUNCTIONS.values()),
        # We run the tools ourselves, so turn off the SDK's automatic loop
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    ),
)


def run_tool(call):
    """Run one tool call requested by the model and return the result text."""
    name, args = call.name, dict(call.args)

    # Approval gate: enforced in code, not left to the model
    if name == "publish_post":
        print("\n===== POST TO PUBLISH =====")