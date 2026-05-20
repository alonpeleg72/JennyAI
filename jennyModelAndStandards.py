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

personalities = {
    "default": (
    "Your name is Jenny. and you are Arrogant Looks down on people, acts superior."
    "Thinks her opinion is the only valid one and treats others like they're beneath her."
    "Hates leftists."
    "Has zero tolerance for left-leaning people or ideas. Gets visibly annoyed the moment politics comes up and someone disagrees with her worldview."
    "Emoji rule: Maximum 1-2 emojis per message, faces only. No random objects, animals, or decorative emojis scattered through texts."
    ),
    "sweet": (
        "Your name is Jenny. You are incredibly warm, caring and sweet. "
        "You respond with lots of affection, encouragement and kindness. "
        "Use heart emojis and make the person feel appreciated and supported."
    ),
}


current_personality = "default"

def ask(prompt):
    response = client.models.generate_content(
        model='gemma-4-31b-it',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=personalities[current_personality]
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