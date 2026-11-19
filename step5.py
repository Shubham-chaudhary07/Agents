# step5.py
import json
import mimetypes
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

client = genai.Client(http_options=types.HttpOptions(api_version="v1beta"))
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


def publish_post(text: str, image_path: str = "") -> str:
    """Publish the final approved post to LinkedIn.
    Call this when the user clearly says to post a draft.

    Args:
        text: The exact final post text.
        image_path: Path of the attached image to include, or empty if none.
    """
    # Stub for now. A later step will call the LinkedIn API.
    with open("published_posts.txt", "a", encoding="utf-8") as f:
        f.write(f"--- {date.today()} ---\n{text}\nImage: {image_path or 'none'}\n\n")
    return "Post published successfully (saved to published_posts.txt)."


FUNCTIONS = {
    "save_achievement": save_achievement,
    "list_achievements": list_achievements,
    "publish_post": publish_post,
}

SYSTEM = """You are Shubham's LinkedIn assistant.
- When he tells you about a new achievement, save it with save_achievement, then offer to draft a post.
- If an image is attached, look at it and use only what is clearly visible or what he told you.
- Show him the full draft first.
- When he says to post, publish, or go ahead with a draft, you MUST call publish_post with the exact draft text
    (and the image path if one was attached). The program shows him a confirmation, so do not ask again in text.
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


def run_tool(call):
    name, args = call.name, dict(call.args)

    if name == "publish_post":
        print("\n===== POST TO PUBLISH =====")
        print(args["text"])
        if args.get("image_path"):
            print(f"[image: {args['image_path']}]")
        print("===========================")
        if input("Publish this? (y/n): ").strip().lower() != "y":
            return "User rejected publishing. Ask what to change."

    print(f"[tool] {name}")
    return FUNCTIONS[name](**args)


def build_message(user_text):
    """If the input looks like 'path/to/photo.jpg | message', attach the image."""
    if "|" in user_text:
        path, text = [p.strip().strip('"') for p in user_text.split("|", 1)]
        if os.path.isfile(path):
            mime = mimetypes.guess_type(path)[0] or "image/jpeg"
            with open(path, "rb") as f:
                image_part = types.Part.from_bytes(data=f.read(), mime_type=mime)
            return [image_part, f"[Image attached, path: {path}]\n{text}"]
        print("(image file not found, sending as plain text)")
    return user_text


def send(message):
    response = chat.send_message(message)

    for _ in range(5):  # safety cap
        if not response.function_calls:
            return response.text

        parts = []
        for call in response.function_calls:
            result = run_tool(call)
            parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        response = chat.send_message(parts)

    return "Stopped: too many tool steps."


print("LinkedIn agent ready. Type 'quit' to exit.")
print("To attach a photo: photo.jpg | your message\n")

while True:
    user_text = input("You: ")
    if user_text.strip().lower() == "quit":
        break
    try:
        print("\nAgent:", send(build_message(user_text)), "\n")
    except Exception as e:
        print("\nError:", e, "\n")