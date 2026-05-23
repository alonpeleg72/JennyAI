MACRO_KEYWORDS = {
    "sweetjenny": "sweet",
    "גנינחמדה": "sweet",
    "hassidicjenny": "hasidic",
    "גניחסידה": "hasidic",
    "defaultjenny": "default",
}

MACRO_STRIP = list(MACRO_KEYWORDS.keys())


def resolve_macro(message_text, silent=False):
    """
    Returns (personality_override, cleaned_message) if a macro keyword is found,
    where cleaned_message has the keyword stripped out.
    Returns (None, None) if no macro keyword is present.
    The caller uses the personality for this one message only, then discards it.

    Special case: 'help' / 'עזרה' prints help and returns ("__help__", None)
    so the caller knows to skip the AI call entirely.

    silent=True suppresses console output (used during cooldown retries).
    """
    msg_lower = message_text.lower()

    if "help" in msg_lower or "עזרה" in message_text:
        if not silent:
            print(_get_help_text())
        return ("__help__", None)

    for keyword, personality in MACRO_KEYWORDS.items():
        if keyword in msg_lower or keyword in message_text:
            cleaned = message_text
            for kw in MACRO_STRIP:
                cleaned = cleaned.replace(kw, "").replace(kw.lower(), "")
            cleaned = cleaned.strip()
            if not silent:
                print(f"[Macro] One-shot personality: {personality} | Prompt: {cleaned!r}")
            return (personality, cleaned)

    return (None, None)


def _get_help_text():
    return (
        "Available macros (prefix your message with the keyword):\n"
        "- sweetjenny or גנינחמדה: Jenny answers sweetly for that message only.\n"
        "- hassidicjenny or גניחסידה: Jenny answers in hasidic mode for that message only.\n"
        "- defaultjenny: Jenny answers in default mode for that message only.\n"
        "- help or עזרה: Show this message.\n"
        "After the macro message Jenny always returns to default."
    )