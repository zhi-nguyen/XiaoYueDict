"""
English spellchecker service for the assessments app.

Uses pyspellchecker to validate English words before they reach the AI service.
This acts as the "Receptionist" — catching misspelled words early so the
pronunciation scoring model doesn't waste GPU cycles on invalid input.
"""
import re
from spellchecker import SpellChecker


# Module-level singleton — initialized once, reused across requests.
_spell = SpellChecker()


def check_english_text(text: str) -> dict:
    """
    Check English text for spelling errors.

    Args:
        text: The input English text to check.

    Returns:
        {
            "is_valid": True/False,
            "misspelled": [
                {"word": "helo", "position": 0, "suggestions": ["hello", "help"]},
            ],
            "clean_text": "original text"
        }
    """
    if not text or not text.strip():
        return {"is_valid": True, "misspelled": [], "clean_text": ""}

    clean_text = text.strip()

    # Tokenize: split into words, preserving their positions in the word list
    # Remove punctuation from each word for checking, but keep original
    words = clean_text.split()

    misspelled_results = []

    for idx, raw_word in enumerate(words):
        # Strip punctuation for spell-checking, but keep contractions
        # e.g. "don't" → "don't", "hello!" → "hello"
        check_word = re.sub(r"[^a-zA-Z']", '', raw_word).strip("'")

        if not check_word:
            continue

        # Skip single letters (a, I) and very short words
        if len(check_word) <= 1:
            continue

        # Check if the word is misspelled
        unknown = _spell.unknown([check_word.lower()])
        if unknown:
            suggestions = list(_spell.candidates(check_word.lower()) or [])
            # Limit suggestions to top 5
            misspelled_results.append({
                "word": raw_word,
                "index": idx,
                "suggestions": suggestions[:5],
            })

    return {
        "is_valid": len(misspelled_results) == 0,
        "misspelled": misspelled_results,
        "clean_text": clean_text,
    }
