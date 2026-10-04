"""
Translation service (Bhashini mocked for Phases 1–7).

Template-first approach:
  - Advisory text uses {variable} slots filled BEFORE translation
  - Numbers, units and dates are substituted BEFORE translation so they
    are never mangled by the MT system
  - Post-translation: RE-VALIDATES that all numbers, units, and dates
    exist intact in the final output string.
  - The Bhashini API is called only for natural-language prose portions

Mock provider:
  - Returns "[LANG: hi] <original_text>" (obvious machine-translated flag)
  - Real Bhashini wired in Phase 8 via BHASHINI_API_KEY env var

SUPPORTED_LANGUAGES maps language codes to display names.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "te": "Telugu",
    "kn": "Kannada",
    "pa": "Punjabi",
}

# Language codes that use Devanagari script (numbers stay ASCII in templates)
DEVANAGARI_LANGS = {"hi", "mr"}

BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "")
BHASHINI_URL     = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"

# Numbers/units/dates that must survive translation unchanged
_PRESERVE_PATTERN = re.compile(
    r"(\d+\.?\d*\s*%|\d+\.?\d*\s*mm|\d+\.?\d*\s*°C"
    r"|\d{4}-\d{2}-\d{2}"         # ISO dates
    r"|\bweek\s+\d+\b"            # "week 2"
    r"|\d+\.?\d*)",               # bare numbers
    re.IGNORECASE,
)


class TranslationIntegrityError(Exception):
    """Raised when MT corrupts preserved numbers/units/dates."""
    pass


def extract_preserved_tokens(text: str) -> list[str]:
    """Find all numbers, units, percentages, and dates in text."""
    return _PRESERVE_PATTERN.findall(text)


def validate_preserved_elements(original_text: str, translated_text: str) -> bool:
    """
    Re-validation step: verify that every number, unit, percentage,
    and date present in the original text is also present in translated text.
    """
    tokens = extract_preserved_tokens(original_text)
    for tok in tokens:
        clean_tok = tok.strip()
        if clean_tok and clean_tok not in translated_text:
            logger.error(
                f"[TranslationValidation] Token {clean_tok!r} missing in translated text: {translated_text!r}"
            )
            return False
    return True


def _extract_preserve(text: str) -> tuple[str, dict]:
    """
    Replace numbers/units with placeholders before translation.
    Returns (masked_text, {placeholder: original}) so they can be restored.
    """
    placeholders = {}
    counter = [0]

    def _replace(m: re.Match) -> str:
        key = f"__NUM{counter[0]}__"
        placeholders[key] = m.group(0)
        counter[0] += 1
        return key

    masked = _PRESERVE_PATTERN.sub(_replace, text)
    return masked, placeholders


def _restore_preserve(text: str, placeholders: dict) -> str:
    """Restore placeholder tokens back to original numbers/units."""
    for key, val in placeholders.items():
        text = text.replace(key, val)
    return text


def translate_text(
    text: str,
    target_lang: str,
    source_lang: str = "en",
) -> tuple[str, bool]:
    """
    Translate text to target_lang.

    Returns (translated_text, is_machine_translated: bool).
    Numbers, units and dates are preserved exactly and re-validated.

    Uses real Bhashini API if BHASHINI_API_KEY is set, otherwise mock.
    """
    if target_lang == source_lang or target_lang == "en":
        return text, False

    # Mask numbers/units before sending to MT
    masked, placeholders = _extract_preserve(text)

    if BHASHINI_API_KEY:
        translated_masked = _call_bhashini(masked, source_lang, target_lang)
        is_machine = True
    else:
        # Mock: prefix with language marker
        translated_masked = f"[{target_lang.upper()}] {masked}"
        is_machine = True

    translated = _restore_preserve(translated_masked, placeholders)

    # Re-validation check
    if not validate_preserved_elements(text, translated):
        raise TranslationIntegrityError(
            f"Translation into {target_lang} failed numerical integrity check. Missing critical numerical tokens."
        )

    return translated, is_machine


def _call_bhashini(text: str, src: str, tgt: str) -> str:
    """
    Call live Bhashini Dhruva API. Only reached when BHASHINI_API_KEY is set.
    """
    try:
        import httpx
        payload = {
            "pipelineTasks": [{
                "taskType": "translation",
                "config": {"language": {"sourceLanguage": src, "targetLanguage": tgt}},
            }],
            "inputData": {"input": [{"source": text}]},
        }
        resp = httpx.post(
            BHASHINI_URL,
            json=payload,
            headers={"Authorization": BHASHINI_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["pipelineResponse"][0]["output"][0]["target"]
    except Exception as e:
        logger.warning(f"[Bhashini] API call failed ({src}→{tgt}): {e}. Using mock.")
        return f"[{tgt.upper()}] {text}"


def translate_advisory(
    headline: str,
    content: str,
    target_lang: str,
    vetted_headline: Optional[str] = None,
    vetted_content: Optional[str] = None,
) -> dict:
    """
    Translate both headline and content of an advisory.
    Distinguishes vetted template translations (vetted_template: True)
    from automated machine translation (machine_translated: True, flagged_for_review: True).
    """
    if target_lang == "en":
        return {
            "language": "en",
            "language_name": "English",
            "headline": headline,
            "content": content,
            "vetted_template": True,
            "machine_translated": False,
            "flagged_for_review": False,
            "provider": "template",
        }

    # Pre-vetted template translation path
    if vetted_headline and vetted_content:
        return {
            "language": target_lang,
            "language_name": SUPPORTED_LANGUAGES.get(target_lang, target_lang),
            "headline": vetted_headline,
            "content": vetted_content,
            "vetted_template": True,
            "machine_translated": False,
            "flagged_for_review": False,
            "review_required": False,
            "review_disclaimer": None,
            "provider": "vetted_template",
        }

    # Free-text Machine Translation path
    translated_headline, is_mt_h = translate_text(headline, target_lang)
    translated_content,  is_mt_c = translate_text(content,  target_lang)
    is_mt = is_mt_h or is_mt_c
    return {
        "language":            target_lang,
        "language_name":       SUPPORTED_LANGUAGES.get(target_lang, target_lang),
        "headline":            translated_headline,
        "content":             translated_content,
        "vetted_template":     False,
        "machine_translated":  is_mt,
        "flagged_for_review":  is_mt,
        "review_required":     is_mt,
        "review_disclaimer":   "Machine-translated content: Extension Officer review required before broadcast." if is_mt else None,
        "provider":            "bhashini" if BHASHINI_API_KEY else "mock",
    }

