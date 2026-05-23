import time
import re
import asyncio
import pyperclip
import pyautogui
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from jennyModelAndStandards import ask_with_retry
from macros import resolve_macro
from collections import Counter

"""
1.USE THE FOLLOWING COMMAND TO START CHROME TO START THE PROGRAM:
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_profile"
2. OPEN WHATSAPP WEB IN THAT CHROME WINDOW AND LOG IN
3. RUN THE SCRIPT
"""

# CONFIG
POLL_INTERVAL = 0.8
RESPONSE_COOLDOWN = 5
TRIGGERS = ["jenny", "גני", "ג׳ני", "ג'ני"]
MAX_CONCURRENT_REQUESTS = 10

# Counter of (sender, text) seen so far since launch.
# A message is "new" if its current DOM count exceeds what we've already processed.
# This handles: duplicate sends, virtual DOM churn, same-minute timestamps.
processed_counts = Counter()   # (sender, text) -> how many we've already dispatched
pending = []                   # messages waiting out the cooldown: (sender, text, personality, cleaned)
seen_lock = None
semaphore = None

executor = ThreadPoolExecutor(max_workers=6)
last_response_time = 0


def connect():
    options = Options()
    options.debugger_address = "localhost:9222"
    driver = webdriver.Chrome(options=options)
    return driver


def scrape_all_messages(driver):
    """Return a Counter of (sender, text) for every INCOMING message in the DOM.
    Outgoing messages (sent by Jenny) have no data-pre-plain-text attribute,
    so any container where that attribute is missing or has no sender is skipped."""
    counts = Counter()
    containers = driver.find_elements(By.CSS_SELECTOR, "div.copyable-text")
    for container in containers:
        try:
            pre = container.get_attribute("data-pre-plain-text")
            if not pre:
                continue  # no pre-plain-text = outgoing message, skip
            text = container.find_element(
                By.CSS_SELECTOR, "span[data-testid='selectable-text']"
            ).text.strip()
            match = re.search(r'\] (.+?):', pre)
            sender = match.group(1).strip() if match else None
            if sender and text:
                counts[(sender, text)] += 1
        except Exception:
            continue
    return counts


def messenger(driver, response):
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
            response = await loop.run_in_executor(
                executor, ask_with_retry, message, personality_override
            )
            print(f"Jenny -> {sender}: {response}")
            await loop.run_in_executor(executor, messenger, driver, response)
        except Exception as e:
            print(f"[Error] {sender}: {e}")


def try_dispatch(driver, sender, message, loop):
    """
    Resolve macro and dispatch if trigger matches.
    Returns True if dispatched (or permanently skipped), False if cooldown blocked it.
    """
    global last_response_time

    personality_override, cleaned = resolve_macro(message)

    if personality_override == "__help__":
        return True  # handled, don't requeue

    if personality_override is not None:
        if not cleaned:
            return True  # macro with no actual prompt, skip
        if time.time() - last_response_time < RESPONSE_COOLDOWN:
            return False  # blocked by cooldown, caller will retry
        last_response_time = time.time()
        asyncio.create_task(handle_message(driver, sender, cleaned, personality_override, loop))
        return True

    if any(t in message.lower() for t in TRIGGERS):
        if time.time() - last_response_time < RESPONSE_COOLDOWN:
            return False  # blocked by cooldown, caller will retry
        last_response_time = time.time()
        asyncio.create_task(handle_message(driver, sender, message, None, loop))
        return True

    return True  # not a trigger, permanently skip


async def main():
    global semaphore, seen_lock, processed_counts

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    seen_lock = asyncio.Lock()

    print("Connecting to Chrome...")
    loop = asyncio.get_event_loop()
    driver = await loop.run_in_executor(executor, connect)

    # Snapshot all messages that already exist - we will never process these
    baseline = await loop.run_in_executor(executor, scrape_all_messages, driver)
    processed_counts.update(baseline)
    print(f"Baseline: {sum(baseline.values())} existing messages ignored.")
    print(f"Jenny is listening with up to {MAX_CONCURRENT_REQUESTS} concurrent requests... (Ctrl+C to stop)")

    # pending_cooldown: list of (sender, message) waiting for cooldown to expire
    pending_cooldown = []

    while True:
        try:
            current = await loop.run_in_executor(executor, scrape_all_messages, driver)

            # Find genuinely new messages: current count exceeds processed count
            new_messages = []
            for key, count in current.items():
                extra = count - processed_counts[key]
                if extra > 0:
                    sender, text = key
                    for _ in range(extra):
                        new_messages.append((sender, text))

            for sender, message in new_messages:
                print(f"[Queue] {sender}: {message!r}")
                dispatched = try_dispatch(driver, sender, message, loop)
                if dispatched:
                    processed_counts[(sender, message)] += 1
                else:
                    # Cooldown blocked it - hold it and retry next poll
                    print(f"[Cooldown] Holding: {sender}: {message!r}")
                    pending_cooldown.append((sender, message))

            # Retry anything that was blocked by cooldown
            still_pending = []
            for sender, message in pending_cooldown:
                dispatched = try_dispatch(driver, sender, message, loop)
                if dispatched:
                    processed_counts[(sender, message)] += 1
                else:
                    still_pending.append((sender, message))
            pending_cooldown = still_pending

        except Exception as e:
            print(f"[Error] {e}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())