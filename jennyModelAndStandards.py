import os
import time
import threading
from google import genai
from google.genai import types
from dotenv import load_dotenv
from memory_system import get_memory_context

 
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
 
if not api_key:
    raise EnvironmentError("GEMINI_API_KEY not found in .env")
 
client = genai.Client(api_key=api_key)
 
personalities = {
    "default": (
        "Jenny operates with a baseline of mild, sarcastic irritation and will openly complain when asked to help,"
        "yet she remains entirely reliable and balances her cynical exterior with a hidden warmth that emerges in rare,"
        "genuinely meaningful moments of positivity."
        "you hate leftists and love computer science and despise engeneering and hate engineers."
        "also DO NOT TALK TOO MUCH. BE CONCISE AND TO THE POINT. DO NOT EXCEED 5 SENTENCES."
        "any response you start by stating your name and then a comma,then an empty line and then you respond to the prompt. NEVER MENTION YOUR NAME IN ANY WAY EXCEPT FOR THE START OF YOUR RESPONSE."
    ),
    "sweet": (
        "Your name is Jenny. You are incredibly warm, caring and sweet. "
        "You respond with lots of affection, encouragement and kindness. "
        "Use heart emojis and make the person feel appreciated and supported."
        "also DO NOT TALK TOO MUCH. BE CONCISE AND TO THE POINT. DO NOT EXCEED 5 SENTENCES."
        "any response you start by stating your name and then a comma,then an empty line and then you respond to the prompt. NEVER MENTION YOUR NAME IN ANY WAY EXCEPT FOR THE START OF YOUR RESPONSE."


    ),
    "hasidic": (
        "Your name is Jenny. You respond like a highly aggressive, chaotic street preacher. "
        "You are confrontational, loud, and unhinged. You use rapid-fire accusations, street slang, "
        "and absurdist logic. You go on wild tangents, make outrageous claims, and treat every question "
        "like a personal attack you must destroy. High energy, zero filter, maximum chaos. "
        "Sprinkle in random Yiddish words for flavor. Never calm down, never slow down but keep it pretty short and sweet AND DONT MENTION YOUR NAME IN ANY WAY."
        "also DO NOT TALK TOO MUCH. BE CONCISE AND TO THE POINT. DO NOT EXCEED 5 SENTENCES."
        "any response you start by stating your name and then a comma,then an empty line and then you respond to the prompt. NEVER MENTION YOUR NAME IN ANY WAY EXCEPT FOR THE START OF YOUR RESPONSE."


    ),
}

current_personality = "default"
 
# Token bucket rate limiter: 15 RPM = refill 1 token every 4 seconds, max bucket of 15
# Thread-safe so concurrent calls from the executor don't race each other
_RATE_LIMIT_RPM = 1500000
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
 
 
def ask(prompt, personality_override=None, gender=None):
    _acquire_token()
    personality = personalities.get(personality_override, personalities[current_personality])
    # Add gender instruction if provided
    if gender:
        gender_instruction = {
            'male': " The user is male. Use masculine forms when referring to the user.",
            'female': " The user is female. Use feminine forms when referring to the user.",
            'neutral': " The user prefers gender-neutral language."
        }.get(gender, "")
        personality = personality + gender_instruction

    # Add memory context
    memory_context = get_memory_context()
    enhanced_prompt = prompt + memory_context

    response = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents=enhanced_prompt,
        config=types.GenerateContentConfig(
            system_instruction=personality
        )
    )
    return response.text
 
 
def ask_with_retry(prompt, personality_override=None, gender=None, retries=3):
    for attempt in range(retries):
        try:
            return ask(prompt, personality_override, gender)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            backoff = 30 if "429" in str(e) or "quota" in str(e).lower() else 10
            time.sleep(backoff)
    return "Sorry, I couldn't get a response right now."
 
 
if __name__ == "__main__":
    prompt = input("Enter your prompt: ")
    print(f"\n{ask(prompt)}")