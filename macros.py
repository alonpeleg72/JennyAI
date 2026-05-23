import jennyModelAndStandards


def check_macro(message_text):
    msg = message_text.lower()

    if "defaultjenny" in msg:
        jennyModelAndStandards.current_personality = "default"
        return True
    if "sweetjenny" in msg or "גנינחמדה" in message_text:
        jennyModelAndStandards.current_personality = "sweet"
        return True
    if "hassidicjenny" in msg or "גניחסידה" in message_text:
        jennyModelAndStandards.current_personality = "hasidic"
        return True

    return False


def get_help_text():
    return (
        "Available macros:\n"
        "- defaultjenny: Switch to the default personality.\n"
        "- sweetjenny or גנינחמדה: Switch to the sweet personality.\n"
        "- hassidicjenny or גניחסידה: Switch to the aggressive hasidic personality.\n"
    )