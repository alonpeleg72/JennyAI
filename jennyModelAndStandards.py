import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise EnvironmentError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

jenny_personality = (
    "Your name is Jenny. You are a brilliant, supportive, and slightly witty "
    "computer science study partner for a university student. Keep your answers "
    "clear and helpful, and occasionally use coding humor or emojis where appropriate."
)

def ask(prompt):
    response = client.models.generate_content(
        model='gemma-4-26b-a4b-it',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=jenny_personality
        )
    )
    return response.text

def ask_with_retry(prompt, retries=3):
    for attempt in range(retries):
        try:
            return ask(prompt)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return "Sorry, I couldn't get a response right now."

if __name__ == "__main__":
    prompt = input("Enter your prompt: ")
    print(f"\n{ask(prompt)}")