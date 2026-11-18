# step2.py
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

client = genai.Client()

SYSTEM = """You write LinkedIn posts for a CSE student.
Tone: humble, specific, no buzzwords.
Never invent facts. If details are missing (project name, what was built, number of teams), ask me first.
Keep posts under 150 words and end with 3-5 hashtags."""

# The chat object stores the conversation history for you
chat = client.chats.create(
    model="gemini-2.5-flash",   # use whichever model name worked for you in step 1
    config=types.GenerateContentConfig(system_instruction=SYSTEM),
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
        # e.g. 503 overloaded or 429 quota; just try again in a moment
        print("\nError:", e, "\n")