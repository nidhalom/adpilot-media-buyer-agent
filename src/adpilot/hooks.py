"""Ad-hook generation: LLM when available, deterministic templates otherwise."""

from __future__ import annotations

from typing import Callable

TEMPLATES: dict[str, list[str]] = {
    "testimonial": [
        "\"I almost didn't try {product}. Here is what changed in 14 days.\"",
        "Real customer, real result: why {n_people} people switched to {product}.",
        "\"I wish I had found {product} before wasting money on the rest.\"",
        "Read this before you buy another {category}: a customer's honest take on {product}.",
    ],
    "problem": [
        "Still struggling with {pain}? Try this 30-second fix with {product}.",
        "The reason your {category} isn't working (and it's not your fault).",
        "Stop doing this if you want results with {category}. Do this instead.",
        "POV: you finally solved {pain}.",
    ],
    "asmr": [
        "Wait for the unboxing... {product} sounds as good as it looks.",
        "Opening {product} so you don't have to guess what's inside.",
        "No talking, just {product}. Watch until the end.",
        "The detail nobody shows you about {product}.",
    ],
    "founder": [
        "I started {product} because every {category} I tried failed me.",
        "Why I quit my job to build {product} (the honest version).",
        "Three mistakes I made building {product} so you don't repeat them.",
        "Our founder explains the one thing competitors won't tell you.",
    ],
    "discount": [
        "48 hours only: {product} at a price we won't repeat.",
        "Before you pay full price for {category}, check this offer.",
        "Last chance: the {product} deal ends tonight.",
        "Is {product} worth it at this price? Here is the math.",
    ],
    "catalog": [
        "Still thinking about {product}? It's waiting for you.",
        "Your cart misses you: {product} is nearly sold out.",
        "Back in stock and going fast: {product}.",
        "You looked, you liked it. Here is a reason to finish the order.",
    ],
    "default": [
        "The {category} secret nobody talks about: {product}.",
        "3 reasons {product} beats what you're using now.",
        "Tested {product} for 30 days. Here is what happened.",
        "If you care about {pain}, watch this.",
    ],
}

KEYWORDS = {
    "testimonial": ["testimonial", "ugc", "review"],
    "problem": ["problem", "solution", "pain"],
    "asmr": ["asmr", "unboxing"],
    "founder": ["founder", "story"],
    "discount": ["discount", "promo", "sale", "banner"],
    "catalog": ["catalog", "dpa", "retarget", "feed"],
}


def infer_angle(text: str) -> str:
    t = text.lower()
    for angle, words in KEYWORDS.items():
        if any(w in t for w in words):
            return angle
    return "default"


def template_hooks(product: str, angle: str = "", n: int = 5, category: str = "", pain: str = "") -> list[str]:
    key = angle if angle in TEMPLATES else infer_angle(angle)
    pool = TEMPLATES[key] + [h for k, v in TEMPLATES.items() if k != key for h in v[:1]]
    fmt = dict(product=product, category=category or "product", pain=pain or "this problem", n_people="1,000+")
    return [h.format(**fmt) for h in pool[: max(1, n)]]


def generate_ad_hooks(
    product: str,
    angle: str = "",
    n: int = 5,
    llm: Callable[[str], str] | None = None,
) -> dict:
    """Return new hooks to test. Uses `llm(prompt)->text` if given, else deterministic templates."""
    n = max(1, min(int(n), 12))
    if llm is not None:
        prompt = (
            f"Write {n} distinct short-form video ad hooks (first 3 seconds / first line, max 15 words each) "
            f"for: {product}. Angle/creative context: {angle or 'general'}. "
            "Vary the psychology (curiosity, social proof, pain point, contrarian, urgency). "
            "Return one hook per line, no numbering, no commentary."
        )
        text = llm(prompt)
        hooks = [ln.strip(" -*\t\"") for ln in text.splitlines() if ln.strip()][:n]
        if hooks:
            return {"source": "llm", "angle": angle, "hooks": hooks}
    return {"source": "template", "angle": angle, "hooks": template_hooks(product, angle, n)}
