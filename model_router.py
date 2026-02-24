"""
CardVault AI — Model Router
Routes tasks to appropriate Claude models based on complexity and cost requirements.

Tiers:
  FAST   → claude-haiku-3-5        (cheap, quick, ~20x cheaper than Sonnet)
  SMART  → claude-sonnet-4-20250514 (default — vision + complex reasoning)
  BEST   → claude-opus-4-5         (edge cases, disputed cards, last resort)
"""

import anthropic
import base64
import json
from pathlib import Path

# Model constants
MODEL_FAST  = "claude-haiku-3-5-20241022"
MODEL_SMART = "claude-sonnet-4-20250514"
MODEL_BEST  = "claude-opus-4-5"

# Confidence threshold below which we escalate to a better model
ESCALATE_THRESHOLD = 0.55


def _encode_image(image_path: str) -> tuple[str, str]:
    """Returns (base64_data, media_type)."""
    path = Path(image_path)
    ext = path.suffix.lower()
    media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    media_type = media_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), media_type


def prescreen_image(client: anthropic.Anthropic, image_path: str) -> dict:
    """
    TIER 1 — Haiku prescreen.
    Fast, cheap check: is this a sports card? Is it usable?
    Returns: { is_card: bool, usable: bool, reason: str, confidence: float }
    """
    b64, media_type = _encode_image(image_path)
    prompt = """Look at this image. Answer ONLY with valid JSON, no other text:
{
  "is_card": true/false,
  "usable": true/false,
  "reason": "one short sentence",
  "confidence": 0.0-1.0
}

is_card = true if this is a sports trading card (or a page of them)
usable = true if the image is clear enough to attempt identification
confidence = how confident you are in this assessment"""

    try:
        resp = client.messages.create(
            model=MODEL_FAST,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        text = resp.content[0].text.strip()
        # Strip markdown if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        result["_input_tok"]  = resp.usage.input_tokens
        result["_output_tok"] = resp.usage.output_tokens
        return result
    except Exception as e:
        # If prescreen fails, assume it's a card and let the main identifier try
        return {"is_card": True, "usable": True, "reason": f"prescreen error: {e}", "confidence": 0.5,
                "_input_tok": 0, "_output_tok": 0}


def route_identify(confidence_score: float, attempt: int = 1) -> str:
    """
    Given confidence from a previous ID attempt, return the model to use next.
    attempt=1 → first try
    attempt=2 → retry (escalate if confidence was low)
    """
    if attempt == 1:
        return MODEL_SMART
    if confidence_score < ESCALATE_THRESHOLD:
        return MODEL_BEST
    return MODEL_SMART


def summarize_card_value(client: anthropic.Anthropic, card_data: dict, value: float) -> str:
    """
    TIER 1 — Haiku generates a short value narrative for the card detail page.
    Cheap task: just formatting + light commentary.
    """
    prompt = f"""Write a 1-2 sentence value summary for this sports card. Be brief and factual.
Card: {card_data.get('player_name')} {card_data.get('year')} {card_data.get('set_name')} {card_data.get('parallel', 'Base')}
Estimated value: ${value:.2f}
RC: {card_data.get('is_rookie', False)}, Auto: {card_data.get('is_auto', False)}, Serial: {card_data.get('numbering', 'N/A')}"""

    try:
        resp = client.messages.create(
            model=MODEL_FAST,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception:
        return f"Estimated value: ${value:.2f}"


def get_grading_advice(client: anthropic.Anthropic, card_data: dict, raw_value: float) -> str:
    """
    TIER 1 — Haiku generates grading recommendation copy.
    Only called for cards over $50.
    """
    prompt = f"""Give a 1-sentence PSA grading recommendation for this card.
{card_data.get('player_name')} {card_data.get('year')} {card_data.get('set_name')}
Raw value: ${raw_value:.2f}. Is RC: {card_data.get('is_rookie', False)}
Be direct: should they grade it, and why (ROI, protection, etc)?"""

    try:
        resp = client.messages.create(
            model=MODEL_FAST,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception:
        return "Consider grading if condition is NM or better."


# ── Usage summary (for logging/monitoring) ──────────────────────────────────

MODEL_COSTS = {
    MODEL_FAST:  {"input": 0.80,  "output": 4.00},   # per million tokens
    MODEL_SMART: {"input": 3.00,  "output": 15.00},
    MODEL_BEST:  {"input": 15.00, "output": 75.00},
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Returns estimated cost in USD."""
    costs = MODEL_COSTS.get(model, MODEL_COSTS[MODEL_SMART])
    return (input_tokens / 1_000_000 * costs["input"]) + (output_tokens / 1_000_000 * costs["output"])
