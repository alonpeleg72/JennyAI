import time
import re
import asyncio
import threading
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
from donnaModelAndStandards import ask_with_retry, ask
from macros import resolve_macro
from collections import Counter
from memory_system import load_memories, remember, recall, forget, list_memories, get_memory_context, memory_system
from dotenv import load_dotenv

load_dotenv()

r"""
1.USE THE FOLLOWING COMMAND TO START CHROME TO START THE PROGRAM:
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_profile"
2. OPEN WHATSAPP WEB IN THAT CHROME WINDOW AND LOG IN
3. RUN THE SCRIPT
"""

# CONFIG
POLL_INTERVAL = 0.3  # Reduced for better responsiveness
RESPONSE_COOLDOWN = 0
TRIGGERS = ["donna", "דונה", "clanker"]
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


# Admin management
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_USER_NAME = os.getenv("ADMIN_USER_NAME", "")
ADMIN_USER_NAME_HE = os.getenv("ADMIN_USER_NAME_HE", "")
ADMIN_FILE = "admins.json"

# Blacklist management
BLACKLIST_FILE = "blacklist.json"
blacklisted_users = set()

# Pause functionality
paused_until = 0  # Timestamp when pause ends (0 = not paused)

# Flood control
FLOOD_TRACKER_FILE = "flood_tracker.json"
flood_tracker = {}  # {user_id: [timestamps]}
FLOOD_LIMIT_COUNT = 5  # Max messages
FLOOD_LIMIT_TIME = 10  # Time window in seconds

# Load persistent data
def load_admin_list():
    global ADMIN_USER, ADMIN_USER_NAME, ADMIN_USER_NAME_HE
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                ADMIN_USER = data.get('primary_admin', ADMIN_USER)
                ADMIN_USER_NAME = data.get('primary_admin_name', ADMIN_USER_NAME)
                ADMIN_USER_NAME_HE = data.get('primary_admin_name_he', ADMIN_USER_NAME_HE)
                # Update admin list in memory system
                admin_set = {ADMIN_USER, ADMIN_USER_NAME, ADMIN_USER_NAME_HE}
                # Add any additional admins from file
                for admin in data.get('additional_admins', []):
                    admin_set.add(admin)
                memory_system.set_admin_users(admin_set)
        except Exception as e:
            print(f"[Warning] Failed to load admin list: {e}")

def save_admin_list():
    try:
        with open(ADMIN_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'primary_admin': ADMIN_USER,
                'primary_admin_name': ADMIN_USER_NAME,
                'primary_admin_name_he': ADMIN_USER_NAME_HE,
                'additional_admins': list(memory_system.admin_users - {ADMIN_USER, ADMIN_USER_NAME, ADMIN_USER_NAME_HE})
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save admin list: {e}")

def load_blacklist():
    global blacklisted_users
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                blacklisted_users.update(json.load(f))
        except Exception as e:
            print(f"[Warning] Failed to load blacklist: {e}")

def save_blacklist():
    try:
        with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(blacklisted_users), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save blacklist: {e}")

def is_blacklisted(user):
    """Check if a user is blacklisted"""
    return user in blacklisted_users

def add_to_blacklist(user):
    """Add a user to the blacklist"""
    blacklisted_users.add(user)
    save_blacklist()
    print(f"[Blacklist] Added {user} to blacklist")

def remove_from_blacklist(user):
    """Remove a user from the blacklist"""
    if user in blacklisted_users:
        blacklisted_users.remove(user)
        save_blacklist()
        print(f"[Blacklist] Removed {user} from blacklist")
        return True
    else:
        print(f"[Blacklist] User {user} not found in blacklist")
        return False

def load_flood_tracker():
    global flood_tracker
    if os.path.exists(FLOOD_TRACKER_FILE):
        try:
            with open(FLOOD_TRACKER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert lists back to lists (JSON stores them as lists)
                flood_tracker = {k: v for k, v in data.items()}
        except Exception as e:
            print(f"[Warning] Failed to load flood tracker: {e}")

def save_flood_tracker():
    try:
        with open(FLOOD_TRACKER_FILE, 'w', encoding='utf-8') as f:
            json.dump(flood_tracker, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save flood tracker: {e}")

def clean_old_timestamps(user_id):
    """Remove timestamps older than FLOOD_LIMIT_TIME for a user"""
    if user_id not in flood_tracker:
        return

    now = time.time()
    # Keep only timestamps within the time window
    flood_tracker[user_id] = [ts for ts in flood_tracker[user_id] if now - ts < FLOOD_LIMIT_TIME]

    # Remove user entry if no timestamps left
    if not flood_tracker[user_id]:
        del flood_tracker[user_id]

def is_flooding(user_id):
    """Check if a user is flooding (exceeding message limit)"""
    if user_id not in flood_tracker:
        return False

    clean_old_timestamps(user_id)  # Clean old timestamps first
    return len(flood_tracker[user_id]) >= FLOOD_LIMIT_COUNT

def record_message(user_id):
    """Record a message from a user for flood tracking"""
    if user_id not in flood_tracker:
        flood_tracker[user_id] = []

    flood_tracker[user_id].append(time.time())
    clean_old_timestamps(user_id)  # Clean old timestamps after adding new one
    save_flood_tracker()

# Initialize with defaults
memory_system.set_admin_users({ADMIN_USER, ADMIN_USER_NAME, ADMIN_USER_NAME_HE})
load_admin_list()
load_blacklist()
load_flood_tracker()

# Pause management functions
def is_paused():
    """Check if the bot is currently paused"""
    global paused_until
    return time.time() < paused_until

def pause_bot(seconds):
    """Pause the bot for specified number of seconds"""
    global paused_until
    paused_until = time.time() + seconds
    save_pause_state()
    print(f"[Pause] Bot paused for {seconds} seconds until {time.ctime(paused_until)}")

def unpause_bot():
    """Unpause the bot immediately"""
    global paused_until
    paused_until = 0
    save_pause_state()
    print("[Pause] Bot unpaused")

def save_pause_state():
    """Save pause state to file"""
    try:
        with open("pause.json", 'w', encoding='utf-8') as f:
            json.dump({'paused_until': paused_until}, f)
    except Exception as e:
        print(f"[Error] Failed to save pause state: {e}")

def load_pause_state():
    """Load pause state from file - always start unpaused to prevent startup issues"""
    global paused_until
    try:
        if os.path.exists("pause.json"):
            with open("pause.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Always start unpaused regardless of saved state
                paused_until = 0
                # Save the corrected state
                save_pause_state()
    except Exception as e:
        print(f"[Warning] Failed to load pause state: {e}")
        paused_until = 0

# Load pause state on startup
load_pause_state()

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
send_lock = threading.Lock()
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
    Skips any message whose text matches something Donna already sent."""
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
                normalized_text = _normalize(text)
                if normalized_text in donna_sent:
                    continue  # Skip messages sent by Donna
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


donna_sent = set()

def messenger(driver, response):
    with send_lock:
        donna_sent.add(_normalize(response))  # mark before sending so scraper ignores it
        input_box = driver.find_element(
            By.CSS_SELECTOR, "div[data-testid='conversation-compose-box-input']"
        )
        input_box.click()
        time.sleep(0.1)
        pyperclip.copy(response)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.1)
        input_box.send_keys(Keys.ENTER)


def send_direct(driver, loop, text):
    """Send a fixed string straight to WhatsApp, no AI call involved."""
    asyncio.create_task(loop.run_in_executor(executor, messenger, driver, text))


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
            print(f"Donna -> {sender}: {response}")
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
                    send_direct(driver, loop, f"Memory stored: {key}")
            else:
                if not silent:
                    print(f"[Memory] Failed to store memory (unauthorized or error)")
                    send_direct(driver, loop, "Sorry, you don't have permission to store memories.")
            return True
        else:
            if not silent:
                print(f"[Memory] Usage: /remember key value")
                send_direct(driver, loop, "Usage: /remember key value")
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
                send_direct(driver, loop, response)
            return True
        else:
            if not silent:
                print(f"[Memory] Usage: /recall key")
                send_direct(driver, loop, "Usage: /recall key")
            return True

    if stripped.startswith("/forget "):
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2:
            key = parts[1]
            if forget(key, sender):
                if not silent:
                    print(f"[Memory] Forgot: {key}")
                    send_direct(driver, loop, f"Memory forgotten: {key}")
            else:
                if not silent:
                    print(f"[Memory] No memory found for '{key}' or unauthorized")
                    send_direct(driver, loop, "Sorry, you don't have permission to forget memories or the memory doesn't exist.")
            return True
        else:
            if not silent:
                print(f"[Memory] Usage: /forget key")
                send_direct(driver, loop, "Usage: /forget key")
            return True

    if stripped.strip() == "/memories":
        if sender in memory_system.admin_users:
            memories = list_memories(sender)
            if memories:
                mem_list = "\n".join([f"  {k}: {v}" for k, v in memories.items()])
                response = f"My memories:\n{mem_list}"
            else:
                response = "I don't have any memories stored yet."
        else:
            response = "Sorry, you don't have permission to view memories."

        if not silent:
            send_direct(driver, loop, response)
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
            send_direct(driver, loop, help_text)
        return True

    if stripped.strip() == "/help":
        if sender in memory_system.admin_users:
            help_text = (
                "Available Commands:\n"
                "  /help - Show this help\n"
                "  /gender male|female - Set gender for name recognition\n"
                "  /remember key value - Store a memory (Admin)\n"
                "  /recall key - Retrieve a memory (Admin)\n"
                "  /forget key - Remove a memory (Admin)\n"
                "  /memories - List all memories (Admin)\n"
                "  /memhelp - Show memory help (Admin)\n"
                "  /pause <seconds> - Pause bot for specified time (Admin)\n"
                "  /unpause - Immediately unpause bot (Admin)\n"
                "  /pausestatus - Check pause status (Admin)\n"
                "  /addblacklist <user> - Add user to blacklist (Admin)\n"
                "  /removeblacklist <user> - Remove user from blacklist (Admin)\n"
                "  /listblacklist - List blacklisted users (Admin)\n"
                "  /floodstatus - Show flood tracking statistics (Admin)\n"
                "  (Bot will also respond to triggers: clanker,donna, דונה)"
            )
        else:
            help_text = (
                "Available Commands:\n"
                "  /help - Show this help\n"
                "  /gender male|female - Set gender for name recognition\n"
                "  (Bot will also respond to triggers: donna, דונה)\n"
                "  (Administrative commands are available to admins only)"
            )
        if not silent:
            send_direct(driver, loop, help_text)
        return True

    # Pause management commands
    if stripped.startswith("/pause "):
        if sender in memory_system.admin_users:
            try:
                seconds = int(stripped.split()[1])
                if seconds > 0:
                    pause_bot(seconds)
                    if not silent:
                        send_direct(driver, loop, f"Bot paused for {seconds} seconds.")
                else:
                    if not silent:
                        send_direct(driver, loop, "Please specify a positive number of seconds.")
            except (IndexError, ValueError):
                if not silent:
                    send_direct(driver, loop, "Usage: /pause <seconds>")
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    if stripped.strip() == "/unpause":
        if sender in memory_system.admin_users:
            unpause_bot()
            if not silent:
                send_direct(driver, loop, "Bot unpaused.")
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    if stripped.strip() == "/pausestatus":
        if sender in memory_system.admin_users:
            if is_paused():
                remaining = int(paused_until - time.time())
                if not silent:
                    send_direct(driver, loop, f"Bot is paused for {remaining} more seconds.")
            else:
                if not silent:
                    send_direct(driver, loop, "Bot is not paused.")
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    # Blacklist management commands
    if stripped.startswith("/addblacklist "):
        if sender in memory_system.admin_users:
            try:
                user_to_block = stripped.split()[1]
                add_to_blacklist(user_to_block)
                if not silent:
                    send_direct(driver, loop, f"User {user_to_block} added to blacklist.")
            except IndexError:
                if not silent:
                    send_direct(driver, loop, "Usage: /addblacklist <user>")
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    if stripped.startswith("/removeblacklist "):
        if sender in memory_system.admin_users:
            try:
                user_to_unblock = stripped.split()[1]
                if remove_from_blacklist(user_to_unblock):
                    if not silent:
                        send_direct(driver, loop, f"User {user_to_unblock} removed from blacklist.")
                else:
                    if not silent:
                        send_direct(driver, loop, f"User {user_to_unblock} was not in the blacklist.")
            except IndexError:
                if not silent:
                    send_direct(driver, loop, "Usage: /removeblacklist <user>")
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    if stripped.strip() == "/listblacklist":
        if sender in memory_system.admin_users:
            if blacklisted_users:
                blacklist_list = "\n".join([f"  {user}" for user in sorted(blacklisted_users)])
                response = f"Blacklisted users:\n{blacklist_list}"
            else:
                response = "No users are currently blacklisted."
            if not silent:
                send_direct(driver, loop, response)
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    # Flood control status
    if stripped.strip() == "/floodstatus":
        if sender in memory_system.admin_users:
            # Show stats for users with messages tracked
            if flood_tracker:
                status_lines = []
                for user, timestamps in flood_tracker.items():
                    clean_old_timestamps(user)  # Clean before counting
                    count = len(flood_tracker[user])
                    status_lines.append(f"  {user}: {count} messages in last {FLOOD_LIMIT_TIME} seconds")
                if status_lines:
                    response = f"Flood tracking:\n" + "\n".join(status_lines)
                else:
                    response = "No users currently being tracked for flood control."
            else:
                response = "No users currently being tracked for flood control."
            if not silent:
                send_direct(driver, loop, response)
        else:
            if not silent:
                send_direct(driver, loop, "Sorry, you don't have permission to use this command.")
        return True

    personality_override, cleaned = resolve_macro(message, silent=silent)

    if personality_override == "__help__":
        return True

    if personality_override is not None:
        if not cleaned:
            return True
        # Check for flood control - prevent AI responses when flooding
        if is_flooding(sender):
            if not silent:
                send_direct(driver, loop, "Please slow down your messages to avoid overwhelming the system.")
            return True  # Prevent AI response but acknowledge the message
        if time.time() - last_response_time < RESPONSE_COOLDOWN:
            return False
        last_response_time = time.time()
        asyncio.create_task(handle_message(driver, sender, cleaned, personality_override, loop))
        return True

    if any(t in message.lower() for t in TRIGGERS):
        # Check for flood control - prevent AI responses when flooding
        if is_flooding(sender):
            if not silent:
                send_direct(driver, loop, "Please slow down your messages to avoid overwhelming the system.")
            return True  # Prevent AI response but acknowledge the message
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
    print(f"Donna is listening with up to {MAX_CONCURRENT_REQUESTS} concurrent requests... (Ctrl+C to stop)")

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
                # Record message for flood tracking
                record_message(sender)

                # Check if bot is paused
                if is_paused():
                    # Only allow specific admin commands when paused
                    stripped = message.strip()
                    if not (stripped.startswith("/unpause") or stripped == "/pausestatus"):
                        print(f"[Pause] Bot is paused, ignoring message from {sender}")
                        continue

                # Check if user is blacklisted
                if is_blacklisted(sender):
                    print(f"[Blacklist] Ignoring message from blacklisted user: {sender}")
                    continue

                # Check if user is flooding
                if is_flooding(sender):
                    print(f"[Flood] User {sender} is flooding, rate limiting")
                    # Still process the message but we'll handle rate limiting in try_dispatch
                    # The flood control is actually handled in try_dispatch where we prevent AI responses

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