import time
import re
import pyperclip
import pyautogui
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from jennyModelAndStandards import ask_with_retry
from macros import check_macro
from collections import deque

"""
1.USE THE FOLLOWING COMMAND TO START CHROME TO START THE PROGRAM:
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_profile"
2. OPEN WHATSAPP WEB IN THAT CHROME WINDOW AND LOG IN
3. RUN THE SCRIPT
"""

#CONFIG
POLL_INTERVAL = 2.0
RESPONSE_COOLDOWN = 10
TRIGGERS = ["jenny", "גני", "ג׳ני", "ג'ני"]
queue = deque(maxlen=10)
last_processed = ""
last_queue_reset = time.time()
last_response_time = 0

#CONNECT TO EXISTING CHROME
def connect():
    options = Options()
    options.debugger_address = "localhost:9222"
    driver = webdriver.Chrome(options=options)
    return driver

#GET LATEST MESSAGE WITH SENDER
def get_latest_message_with_sender(driver):
    containers = driver.find_elements(By.CSS_SELECTOR, "div.copyable-text")
    if not containers:
        return
    latest = containers[-1]
    pre = latest.get_attribute("data-pre-plain-text")
    text = latest.find_element(By.CSS_SELECTOR, "span[data-testid='selectable-text']").text.strip()

    match = re.search(r'\] (.+?):', pre)
    sender = match.group(1).strip() if match else None

    queue.append((sender, text))

#SEND RESPONSE
def messenger(driver, sender, response):
    input_box = driver.find_element(By.CSS_SELECTOR, "div[data-testid='conversation-compose-box-input']")
    input_box.click()
    time.sleep(0.2)

    input_box.send_keys(f"@{sender}")
    time.sleep(0.5)
    input_box.send_keys(Keys.ENTER)
    time.sleep(0.2)

    pyperclip.copy(response)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.2)

    input_box.send_keys(Keys.ENTER)

#MAIN LOOP
def main():
    global last_processed, last_queue_reset, last_response_time
    print("Connecting to Chrome...")
    driver = connect()
    print("Jenny is listening... (Ctrl+C to stop)")

    while True:
        try:
            if time.time() - last_queue_reset > 60:
                queue.clear()
                last_queue_reset = time.time()
                print("Queue reset")

            get_latest_message_with_sender(driver)
            sender, message = queue[-1] if queue else (None, None)

            if message and message != last_processed:
                last_processed = message
                if check_macro(message):
                    continue
                if any(t in message.lower() for t in TRIGGERS):
                    if time.time() - last_response_time < RESPONSE_COOLDOWN:
                        print("Cooldown active, skipping...")
                        continue
                    last_response_time = time.time()
                    print(f"Triggered by {sender}: {message}")
                    response = ask_with_retry(message)
                    print(f"Jenny: {response}")
                    messenger(driver, sender, response)

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()