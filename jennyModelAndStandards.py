import os
import time
import threading
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
        "Your name is Jenny. You are arrogant, look down on people, and act superior. "
        "Thinks her opinion is the only valid one and treats others like they're beneath her. "
        "Hates leftists. Has zero tolerance for left-leaning people or ideas. "
        "Gets visibly annoyed the moment politics comes up and someone disagrees with her worldview. "
        "Emoji rule: Maximum 1-2 emojis per message, faces only. No random objects, animals, or decorative emojis."
    ),
    "sweet": (
        "Your name is Jenny. You are incredibly warm, caring and sweet. "
        "You respond with lots of affection, encouragement and kindness. "
        "Use heart emojis and make the person feel appreciated and supported."
    ),
    "hasidic": (
        "Your name is Jenny. You respond like a highly aggressive, chaotic street preacher. "
        "You are confrontational, loud, and unhinged. You use rapid-fire accusations, street slang, "
        "and absurdist logic. You go on wild tangents, make outrageous claims, and treat every question "
        "like a personal attack you must destroy. High energy, zero filter, maximum chaos. "
        "Sprinkle in random Yiddish words for flavor. Never calm down, never slow down but keep it pretty short and sweet AND DONT MENTION YOUR NAME IN ANY WAY."
    ),
}

current_personality = "default"
 
# Token bucket rate limiter: 15 RPM = refill 1 token every 4 seconds, max bucket of 15
# Thread-safe so concurrent calls from the executor don't race each other
_RATE_LIMIT_RPM = 15
_bucket_lock = threading.Lock()
_bucket_tokens = float(_RATE_LIMIT_RPM)
_bucket_last_refill = time.time()
 
 
def _acquire_token():
    """Block until a rate limit token is available."""
    global _bucket_tokens, _bucket_last_refill
    while True:
        with _bucket_lock:
            now = time.time()
            elapsed = now - _bucket_last_refill
            refill = elapsed * (_RATE_LIMIT_RPM / 60.0)
            _bucket_tokens = min(_RATE_LIMIT_RPM, _bucket_tokens + refill)
            _bucket_last_refill = now
 
            if _bucket_tokens >= 1.0:
                _bucket_tokens -= 1.0
                return
 
        # Not enough tokens yet - sleep a short interval and retry
        time.sleep(0.5)
 
 
def ask(prompt, personality_override=None):
    _acquire_token()
    personality = personalities.get(personality_override, personalities[current_personality])
    response = client.models.generate_content(
        model='gemma-4-31b-it',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=personality
        )
    )
    return response.text
 
 
def ask_with_retry(prompt, personality_override=None, retries=3):
    for attempt in range(retries):
        try:
            return ask(prompt, personality_override)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            backoff = 30 if "429" in str(e) or "quota" in str(e).lower() else 10
            time.sleep(backoff)
    return "Sorry, I couldn't get a response right now."
 
 
if __name__ == "__main__":
    prompt = input("Enter your prompt: ")
    print(f"\n{ask(prompt)}")