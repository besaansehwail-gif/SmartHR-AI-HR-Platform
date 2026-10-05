"""Fixed interviewer speech in the supported interview languages."""

PHRASES = {
    "welcome": (
        "Hi, welcome to your SmartHR interview. There are {count} questions - "
        "please answer after each one. Here is the first.",
        "مرحبًا بك في مقابلة SmartHR. لدينا {count} أسئلة؛ يرجى الإجابة بعد كل سؤال. لنبدأ بالسؤال الأول.",
    ),
    "welcome_for_role": (
        "Hi, welcome to your SmartHR interview for the {title} position. "
        "There are {count} questions - please answer after each one. Here is the first.",
        "مرحبًا بك في مقابلة SmartHR لوظيفة {title}. لدينا {count} أسئلة؛ يرجى الإجابة بعد كل سؤال. لنبدأ بالسؤال الأول.",
    ),
    "spoke_during_welcome": (
        "Sorry, I couldn't hear you while I was speaking.",
        "عذرًا، لم أتمكن من سماعك أثناء حديثي.",
    ),
    "silence_nudge": (
        "Take your time. Whenever you're ready, I'm listening.",
        "خذ وقتك. عندما تكون مستعدًا، أنا أستمع.",
    ),
    "closing": (
        "Thank you for your time today. That's the end of this practice interview. Goodbye.",
        "شكرًا لوقتك اليوم. انتهت هذه المقابلة التدريبية. إلى اللقاء.",
    ),
    "plan_unavailable": (
        "I'm sorry - the interview questions could not be loaded right now, so we can't "
        "continue this interview. Please try again a little later. Goodbye.",
        "عذرًا، تعذر تحميل أسئلة المقابلة الآن، لذلك لا يمكننا المتابعة. يرجى المحاولة لاحقًا. إلى اللقاء.",
    ),
    "closing_after_last": (
        "That was my last question. Thank you for your time today - "
        "this is the end of the practice interview. Goodbye.",
        "كان هذا سؤالي الأخير. شكرًا لوقتك اليوم؛ انتهت المقابلة التدريبية. إلى اللقاء.",
    ),
    "repeat_after_cut": (
        "Let me repeat the question.",
        "سأعيد طرح السؤال.",
    ),
    "fixed_repeat": ("Of course.", "بالطبع."),
    "fixed_reask": ("Sorry, I didn't catch that.", "عذرًا، لم أتمكن من فهم إجابتك."),
    "fixed_skip": ("Let's move on to the next question.", "لننتقل إلى السؤال التالي."),
    "side_reply_fallback": ("Let's continue with the interview.", "لنواصل المقابلة."),
    "fallback_ack": ("Thank you.", "شكرًا."),
    "elaboration_fallback": (
        "Could you tell me a little more about that?",
        "هل يمكنك إضافة مزيد من التفاصيل؟",
    ),
}


def spoken_phrase(key: str, language: str | None = "en", **values: str | int) -> str:
    """Return a fixed phrase in Arabic for ar* locales, otherwise English."""
    try:
        english, arabic = PHRASES[key]
    except KeyError:
        raise KeyError(f"Unknown interviewer phrase: {key}") from None
    template = arabic if isinstance(language, str) and language.casefold().startswith("ar") else english
    return template.format(**values)
