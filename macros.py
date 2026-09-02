MACRO_KEYWORDS = {
    "sweetdonna": "sweet",
    "דונה חמדה": "sweet",
    "hassicdonna": "hasidic",
    "דונה חסידה": "hasidic",
    "defaultdonna": "default",
    "donnasuits": "suits",
    "דונהחליפה": "suits",
}


def resolve_macro(message_text, silent=False):
    """
    Returns (personality_override, cleaned_message) if a macro keyword is found,
    where cleaned_message has the keyword stripped out.
    Returns (None, None) if no macro keyword is present.
    The caller uses the personality for this one message only, then discards it.

    Special case: '\help' / 'עזרה\ ' prints help and returns ("__help__", None)
    so the caller knows to skip the AI call entirely.

    silent=True suppresses console output (used during cooldown retries).
    """
    msg_lower = message_text.lower()

    if "\\help" in msg_lower or "עזרה\\ " in message_text:
        if not silent:
            print(_get_help_text())
        return ("__help__", None)

    for keyword, personality in MACRO_KEYWORDS.items():
        if keyword in msg_lower or keyword in message_text:
            cleaned = message_text.replace(keyword, "").replace(keyword.lower(), "").strip()
            if not silent:
                print(f"[Macro] One-shot personality: {personality} | Prompt: {cleaned!r}")
            return (personality, cleaned)

    return (None, None)


def _get_help_text():
    return (
        "Available macros (prefix your message with the keyword):\n"
        "- sweetdonna or דונה חמדה: Donna answers sweetly for that message only.\n"
        "- hassicdonna or דונה חסידה: Donna answers in hasidic mode for that message only.\n"
        "- donnasuits or דונהחליפה: Donna answers like donna from suits mode for that message only.\n"
        "- defaultdonna: Donna answers in default mode for that message only.\n"
        "- help or עזרה: Show this message.\n"
        "After the macro message Donna always returns to default."
    )