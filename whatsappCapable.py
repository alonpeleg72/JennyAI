import time
import re
import asyncio
import pyperclip
import pyautogui
import json
import os
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    WebDriverException,
    TimeoutException
)
from jennyModelAndStandards import ask_with_retry, ask
from macros import resolve_macro
from collections import Counter
from memory_system import load_memories, remember, recall, forget, get_memory_context, memory_system

r"""
1.USE THE FOLLOWING COMMAND TO START CHROME TO START THE PROGRAM:
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_profile"
2. OPEN WHATSAPP WEB IN THAT CHROME WINDOW AND LOG IN
3. RUN THE SCRIPT
"""

# CONFIG
POLL_INTERVAL = 0.3  # Reduced for better responsiveness
RESPONSE_COOLDOWN = 0
TRIGGERS = ["jenny", "גני", "ג׳ני", "ג'ni"]
MAX_CONCURRENT_REQUESTS = 10

# Connection management
CONNECTION_RETRY_ATTEMPTS = 3
CONNECTION_RETRY_DELAY = 2  # seconds
MAX_RECONNECT_ATTEMPTS = 5

# Selector configurations for robustness
MESSAGE_CONTAINER_SELECTORS = [
    "div.copyable-text",  # Primary selector
    "div[data-pre-plain-text]",  # More direct attribute-based
    ".message-in",  # Alternative class-based
    "[data-testid='msg-container']",  # Test ID based
]

MESSAGE_TEXT_SELECTOR = "span[data-testid='selectable-text']"

processed_counts = Counter()  # (sender, text) -> how many we've already dispatched
# pending_cooldown: set of (sender, message) waiting for cooldown - set prevents duplicates
pending_cooldown = set()
# Gender mapping: sender -> gender ('male', 'female')
GENDER_FILE = "gender.json"
gender_map = {}

# Load memories on startup
load_memories()


ADMIN_USER = "+972584459936"
ADMIN_USER_NAME = "alon peleg"
ADMIN_USER_NAME_HE = "אלון פלג"
memory_system.set_admin_users({ADMIN_USER, ADMIN_USER_NAME, ADMIN_USER_NAME_HE})

def load_gender_map():
    global gender_map
    if os.path.exists(GENDER_FILE):
        try:
            with open(GENDER_FILE, 'r', encoding='utf-8') as f:
                gender_map.update(json.load(f))
        except Exception as e:
            print(f"[Warning] Failed to load gender map: {e}")

def save_gender_map():
    try:
        with open(GENDER_FILE, 'w', encoding='utf-8') as f:
            json.dump(gender_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save gender map: {e}")

# Cache for gender guesses to avoid repeated API calls for the same name
GENDER_GUESS_CACHE = {}
GENDER_GUESS_FILE = "gender_guess_cache.json"

def load_gender_guess_cache():
    global GENDER_GUESS_CACHE
    if os.path.exists(GENDER_GUESS_FILE):
        try:
            with open(GENDER_GUESS_FILE, 'r', encoding='utf-8') as f:
                GENDER_GUESS_CACHE.update(json.load(f))
        except Exception as e:
            print(f"[Warning] Failed to load gender guess cache: {e}")

def save_gender_guess_cache():
    try:
        with open(GENDER_GUESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(GENDER_GUESS_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save gender guess cache: {e}")

def guess_gender_with_ai(name):
    """
    Use the AI to guess gender from a name.
    Returns 'male', 'female', or None if uncertain/unable to determine.
    Results are cached to avoid repeated API calls.
    """
    if not name:
        return None

    name = name.strip()
    if not name:
        return None

    # Check cache first
    if name in GENDER_GUESS_CACHE:
        return GENDER_GUESS_CACHE[name]

    try:
        # Use a simple, fast prompt for gender detection
        prompt = f"What is the likely gender associated with the name '{name}'? Respond with only 'male', 'female', or 'unknown'."

        # We'll make a direct API call here to avoid rate limiting issues with our main token bucket
        # For now, we'll reuse the existing ask function but we should be careful about frequency

        # Temporarily use a simple approach - we could optimize this later
        response = ask(prompt, gender=None)  # No gender bias for this query
        response_clean = response.strip().lower()

        if 'male' in response_clean and 'female' not in response_clean:
            result = 'male'
        elif 'female' in response_clean and 'male' not in response_clean:
            result = 'female'
        else:
            result = None  # uncertain or unknown

        # Cache the result
        GENDER_GUESS_CACHE[name] = result
        # Save cache periodically (we could do this less frequently to save IO)
        save_gender_guess_cache()

        return result
    except Exception as e:
        print(f"[Error] Gender detection failed for '{name}': {e}")
        return None

semaphore = None
executor = ThreadPoolExecutor(max_workers=12)
last_response_time = 0


def connect():
    options = Options()
    options.debugger_address = "localhost:9222"
    # Add performance and stability options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-default-apps")

    driver = webdriver.Chrome(options=options)
    return driver

def is_connection_healthy(driver):
    """Check if the Chrome connection is still alive"""
    try:
        # Simple test - if this fails, connection is dead
        driver.current_url
        return True
    except:
        return False

def reconnect_to_chrome():
    """Attempt to reconnect to Chrome debugging instance"""
    print("[Reconnect] Attempting to reconnect to Chrome...")
    for attempt in range(MAX_RECONNECT_ATTEMPTS):
        try:
            driver = connect()
            if is_connection_healthy(driver):
                print(f"[Reconnect] Successfully reconnected on attempt {attempt + 1}")
                return driver
        except Exception as e:
            print(f"[Reconnect] Attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                time.sleep(CONNECTION_RETRY_DELAY)

    print("[Reconnect] Failed to reconnect after all attempts")
    return None

def find_elements_with_fallback(driver, selectors):
    """Try multiple selectors and return the first one that finds elements"""
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                return elements
        except:
            continue
    return []  # Return empty if none work

def extract_message_data(container):
    """Extract message data from a container with error handling"""
    try:
        # Get pre-text (contains sender info)
        pre = container.get_attribute("data-pre-plain-text")
        if not pre:
            return None, None  # Outgoing message or no sender info

        # Extract message text
        try:
            text_element = container.find_element(By.CSS_SELECTOR, MESSAGE_TEXT_SELECTOR)
            text = text_element.text.strip()
        except NoSuchElementException:
            # Fallback: try to get text directly
            text = container.text.strip()
            # Clean up if it contains the pre-text
            if pre in text:
                text = text.replace(pre, "").strip()

        # Parse sender from pre-text
        # Format: [HH:MM, DD/MM/YYYY] Sender:
        match = re.search(r'\] (.+?):', pre)
        sender = match.group(1).strip() if match else None

        return sender, text if sender and text else (None, None)
    except StaleElementReferenceException:
        # Element went stale, skip this one
        return None, None
    except Exception:
        # Other unexpected error
        return None, None


def scrape_all_messages(driver):
    """Return a Counter of (sender, text) for incoming messages only.
    Skips any message whose text matches something Jenny already sent."""
    counts = Counter()

    # Check connection health first
    if not is_connection_healthy(driver):
        print("[Scrape] Connection unhealthy, attempting reconnect...")
        # Note: In a real implementation, we might want to reconnect here
        # For now, we'll return empty counts and let the main loop handle it
        return counts

    # Find message containers using fallback selectors
    containers = find_elements_with_fallback(driver, MESSAGE_CONTAINER_SELECTORS)

    for container in containers:
        try:
            sender, text = extract_message_data(container)
            if sender and text:
                counts[(sender, text)] += 1
        except StaleElementReferenceException:
            # Skip stale elements - they'll be picked up in next iteration
            continue
        except Exception as e:
            # Log unexpected errors but continue processing
            # print(f"[Scrape] Error processing container: {e}")
            continue

    return counts


def _normalize(text):
    """Collapse all whitespace/newlines to single spaces for comparison."""
    return re.sub(r'\s+', ' ', text).strip()

# Initialize the set of messages sent by Jenny to avoid processing our own messages
jenny_sent = set()

def messenger(driver, response):
    jenny_sent.add(_normalize(response))  # mark before sending so scraper ignores it
    input_box = driver.find_element(
        By.CSS_SELECTOR, "div[data-testid='conversation-compose-box-input']"
    )
    input_box.click()
    time.sleep(0.1)
    pyperclip.copy(response)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1)
    input_box.send_keys(Keys.ENTER)


async def handle_message(driver, sender, message, personality_override, loop):
    async with semaphore:
        print(f"[Processing] {sender}: {message!r}")
        try:
            # Get explicit gender if set, otherwise guess from name using AI
            gender = gender_map.get(sender)
            if gender is None:
                gender = guess_gender_with_ai(sender)
            response = await loop.run_in_executor(
                executor, ask_with_retry, message, personality_override, gender
            )
            print(f"Jenny -> {sender}: {response}")
            await loop.run_in_executor(executor, messenger, driver, response)
        except Exception as e:
            print(f"[Error] {sender}: {e}")
            # Try to send an apology message
            apology = "Sorry, I encountered an error while processing your message."
            try:
                await loop.run_in_executor(executor, messenger, driver, apology)
            except Exception as e2:
                print(f"[Error] Failed to send apology: {e2}")


def try_dispatch(driver, sender, message, loop, silent=False):
    """
    Dispatch the message if cooldown allows.
    Returns True if dispatched or permanently skipped, False if cooldown blocked it.
    silent=True suppresses macro print (used during cooldown retries).
    """
    global last_response_time

    # Handle gender setting command
    stripped = message.strip()
    if stripped.startswith("/gender "):
        parts = stripped.split()
        if len(parts) >= 2 and parts[1] in ("male", "female"):
            gender_map[sender] = parts[1]
            save_gender_map()
            if not silent:
                print(f"[Gender] Set {sender} gender to {parts[1]}")
            return True  # command handled, no AI response
        else:
            if not silent:
                print(f"[Gender] Usage: /gender male|female")
            return True

    # Handle memory commands
    if stripped.startswith("/remember "):
        parts = stripped.split(maxsplit=2)  # Split into max 3 parts
        if len(parts) >= 3:
            key, value = parts[1], parts[2]
            if remember(key, value, sender):
                if not silent:
                    print(f"[Memory] Stored: {key} = {value}")
                    asyncio.create_task(handle_message(driver, sender, f"Memory stored: {key}", None, loop))
            else:
                if not silent:
                    print(f"[Memory] Failed to store memory (unauthorized or error)")
                if not silent:
                    asyncio.create_task(handle_message(driver, sender, "Sorry, you don't have permission to store memories.", None, loop))
            return True
        else:
            if not silent:
                print(f"[Memory] Usage: /remember key value")
            if not silent:
                asyncio.create_task(handle_message(driver, sender, "Usage: /remember key value", None, loop))
            return True

    if stripped.startswith("/recall "):
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2:
            key = parts[1]
            value = recall(key, sender)
            if value is not None:
                response = f"I remember: {key} = {value}"
            else:
                # Could be either not found or unauthorized - don't reveal which for security
                response = f"I don't have any memory stored for '{key}'."
            if not silent:
                asyncio.create_task(handle_message(driver, sender, response, None, loop))
            return True
        else:
            if not silent:
                print(f"[Memory] Usage: /recall key")
            if not silent:
                asyncio.create_task(handle_message(driver, sender, "Usage: /recall key", None, loop))
            return True

    if stripped.startswith("/forget "):
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2:
            key = parts[1]
            if forget(key, sender):
                if not silent:
                    print(f"[Memory] Forgot: {key}")
                if not silent:
                    asyncio.create_task(handle_message(driver, sender, f"Memory forgotten: {key}", None, loop))
            else:
                if not silent:
                    print(f"[Memory] No memory found for '{key}' or unauthorized")
                if not silent:
                    asyncio.create_task(handle_message(driver, sender, "Sorry, you don't have permission to forget memories or the memory doesn't exist.", None, loop))
            return True
        else:
            if not silent:
                print(f"[Memory] Usage: /forget key")
            if not silent:
                asyncio.create_task(handle_message(driver, sender, "Usage: /forget key", None, loop))
            return True

    if stripped.strip() == "/memories":
        memories = list_memories(sender)
        if memories:
            mem_list = "\n".join([f"  {k}: {v}" for k, v in memories.items()])
            response = f"My memories:\n{mem_list}"
        else:
            # Could be either no memories or unauthorized - don't reveal which for security
            response = "I don't have any memories stored yet."
        if not silent:
            asyncio.create_task(handle_message(driver, sender, response, None, loop))
        return True

    if stripped.strip() == "/memhelp":
        help_text = (
            "Memory Commands (Admin Only):\n"
            "  /remember key value - Store a memory\n"
            "  /recall key - Retrieve a memory\n"
            "  /forget key - Remove a memory\n"
            "  /memories - List all memories\n"
            "  /memhelp - Show this help"
        )
        if not silent:
            asyncio.create_task(handle_message(driver, sender, help_text, None, loop))
        return True

    personality_override, cleaned = resolve_macro(message, silent=silent)

    if personality_override == "__help__":
        return True

    if personality_override is not None:
        if not cleaned:
            return True
        if time.time() - last_response_time < RESPONSE_COOLDOWN:
            return False
        last_response_time = time.time()
        asyncio.create_task(handle_message(driver, sender, cleaned, personality_override, loop))
        return True

    if any(t in message.lower() for t in TRIGGERS):
        if time.time() - last_response_time < RESPONSE_COOLDOWN:
            return False
        last_response_time = time.time()
        asyncio.create_task(handle_message(driver, sender, message, None, loop))
        return True

    return True  # not a trigger, skip permanently


async def main():
    global semaphore, processed_counts, gender_map

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    load_gender_map()
    load_gender_guess_cache()

    print("Connecting to Chrome...")
    loop = asyncio.get_event_loop()
    driver = await loop.run_in_executor(executor, connect)

    # Initial connection check
    if not is_connection_healthy(driver):
        print("[Main] Initial connection unhealthy, attempting reconnect...")
        driver = await loop.run_in_executor(executor, reconnect_to_chrome)
        if driver is None:
            print("[Main] Failed to establish connection. Exiting.")
            return

    baseline = await loop.run_in_executor(executor, scrape_all_messages, driver)
    processed_counts.update(baseline)
    print(f"Baseline: {sum(baseline.values())} existing messages ignored.")
    print(f"Jenny is listening with up to {MAX_CONCURRENT_REQUESTS} concurrent requests... (Ctrl+C to stop)")

    consecutive_failures = 0
    max_consecutive_failures = 5

    while True:
        try:
            # Check connection health periodically
            if consecutive_failures > 0 and consecutive_failures % 3 == 0:
                if not is_connection_healthy(driver):
                    print(f"[Main] Connection unhealthy after {consecutive_failures} failures, attempting reconnect...")
                    driver = await loop.run_in_executor(executor, reconnect_to_chrome)
                    if driver is None:
                        print("[Main] Failed to reconnect. Will continue trying...")
                    else:
                        consecutive_failures = 0  # Reset on successful reconnect

            current = await loop.run_in_executor(executor, scrape_all_messages, driver)

            # If we got no results, it might indicate a connection issue
            if len(current) == 0:
                consecutive_failures += 1
                # print(f"[Main] No messages found (failure #{consecutive_failures})")
            else:
                consecutive_failures = 0  # Reset on successful retrieval

            # Detect genuinely new messages
            new_messages = []
            for key, count in current.items():
                extra = count - processed_counts[key]
                if extra > 0:
                    sender, text = key
                    for _ in range(extra):
                        new_messages.append((sender, text))
                        # Mark as processed immediately so next poll doesn't re-detect it
                        # even if cooldown holds it in pending
                        processed_counts[key] += 1

            for sender, message in new_messages:
                print(f"[Queue] {sender}: {message!r}")
                dispatched = try_dispatch(driver, sender, message, loop)
                if not dispatched:
                    print(f"[Cooldown] Holding: {sender}: {message!r}")
                    pending_cooldown.add((sender, message))

            # Retry cooldown-held messages - use a snapshot to avoid mutation during iteration
            for item in list(pending_cooldown):
                sender, message = item
                dispatched = try_dispatch(driver, sender, message, loop, silent=True)
                if dispatched:
                    pending_cooldown.discard(item)
                    print(f"[Cooldown] Released: {sender}: {message!r}")

        except Exception as e:
            print(f"[Error] {e}")
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                print(f"[Main] Too many consecutive failures ({consecutive_failures}), attempting reconnect...")
                driver = await loop.run_in_executor(executor, reconnect_to_chrome)
                if driver is None:
                    print("[Main] Failed to reconnect. Will continue trying...")
                else:
                    consecutive_failures = 0

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())