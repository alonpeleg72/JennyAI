import pyautogui
import pyperclip
import pytesseract
import time
import re
import locator
from jennyModelAndStandards import ask
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# CONFIG 
CHAT_REGION = (923, 323, 1876 , 1205)  # (x, y, width, height) — adjust to your screen
POLL_INTERVAL = 2.0
DIRECTED_PATTERNS = [r"jenny[,\s]", r"גני[,\s]", r"ג[׳']ני[,\s]"]

last_processed = ""

# OCR 
def get_chat_text():
    screenshot = pyautogui.screenshot(region=CHAT_REGION)
    text = pytesseract.image_to_string(screenshot, lang='heb+eng')
    return text

# PARSE 
def extract_message(chat_text):
    lines = [l.strip() for l in chat_text.split('\n') if l.strip()]
    target = None
    for line in lines:
        if any(re.search(p, line.lower()) for p in DIRECTED_PATTERNS):
            target = line
    return target

# AI 
def ask_jenny(message):
    return ask(message)

# SEND 
def messenger(message):
    location = locator.locateOnScreen(
        r'C:\Users\alonp\documents\degree\year1\CS\WhatsappBot\whatsapp_bot_images\TextLine.png',
        confidence=0.85
    )
    pyautogui.click(location)
    pyperclip.copy(message)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1)
    pyautogui.press('enter')

# MAIN LOOP 
def main():
    global last_processed
    print("Jenny is listening... (Ctrl+C to stop)")
    while True:
        try:
            chat_text = get_chat_text()
            message = extract_message(chat_text)

            if message and message != last_processed:
                last_processed = message
                print(f"Triggered: {message}")
                response = ask_jenny(message)
                print(f"Jenny: {response}")
                messenger(response)

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()