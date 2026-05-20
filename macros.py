import jennyModelAndStandards

def check_macro(message):
    if "sweetjenny" in message.lower() or "גנינחמדה" in message:
        jennyModelAndStandards.current_personality = "sweet"
        return True
    if "defaultjenny" in message.lower():
        jennyModelAndStandards.current_personality = "default"
        return True
    return False