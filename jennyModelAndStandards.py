import os
from google import genai
from google.genai import types 
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Error: GEMINI_API_KEY not found!")
    exit()

client = genai.Client(api_key=api_key)

jenny_personality = (
    "Your name is Jenny. You are a brilliant, supportive, and slightly witty "
    "computer science study partner for a university student. Keep your answers "
    "clear and helpful, and occasionally use coding humor or emojis where appropriate."
)

contents = input("Enter your prompt: ") 

response = client.models.generate_content(
    model='gemma-4-26b-a4b-it',
    contents=contents,
    config=types.GenerateContentConfig(
        system_instruction=jenny_personality
    )
)

print(f"\n{response.text}")
