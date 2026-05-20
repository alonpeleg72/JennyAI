import time
import pyperclip
import pyautogui
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from jennyModelAndStandards import ask_with_retry

#CONFIG
POLL_INTERVAL = 2.0
TRIGGERS = ["jenny", "גני", "ג׳ני", "ג'ני"]

last_processed = ""

#CONNECT TO EXISTING CHROME
def connect():
    options = Options()
    options.debugger_address = "localhost:9222"
    driver = webdriver.Chrome(options=options)
    return driver

#GET LATEST MESSAGE
def get_latest_message(driver):
    messages = driver.find_elements(By.CSS_SELECTOR, "span[data-testid='selectable-text']")
    if not messages:
        return None
    return messages[-1].text.strip()

#SEND RESPONSE
def messenger(driver, response):
    input_box = driver.find_element(By.CSS_SELECTOR, "div[data-testid='conversation-compose-box-input']")
    input_box.click()
    pyperclip.copy(response)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.2)
    input_box.send_keys(Keys.ENTER)

#MAIN LOOP
def main():
    global last_processed
    print("Connecting to Chrome...")
    driver = connect()
    print("Jenny is listening... (Ctrl+C to stop)")

    while True:
        try:
            message = get_latest_message(driver)

            if message and message != last_processed:
                if any(t in message.lower() for t in TRIGGERS):
                    last_processed = message
                    print(f"Triggered: {message}")
                    response = ask_with_retry(message)
                    print(f"Jenny: {response}")
                    messenger(driver, response)

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()