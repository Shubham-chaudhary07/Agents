# step1.py
from dotenv import load_dotenv
load_dotenv()
# Import the Gemini library
from google import genai

# Create a client. It reads GEMINI_API_KEY from your environment automatically.
client = genai.Client()
for m in client.models.list():
    print(m.name)

# Send one prompt to the model and get a response
response = client.models.generate_content(
    model="gemini-3.6-flash",   # if you get "model not found", copy the current Flash model name from AI Studio
    contents="Write a LinkedIn post about getting into the top 10 at the VisionX hackathon. Keep it humble and under 120 words.",
)

# Print the whole response object first to see its structure
print(response)

print("-----")

# Print only the generated text
print(response.text)
