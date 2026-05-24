"""
English text normalization for pronunciation scoring.
Handles punctuation removal and basic text cleanup for alignment.
"""
import re


def clean_text_for_scoring(text: str, lang: str = 'en') -> str:
    """
    The "Vacuum Cleaner" — strips EVERYTHING except scorable characters.

    By the time text reaches this function, the Next.js frontend has already
    validated that input contains only letters/Chinese characters and punctuation
    (no numbers, no math symbols). This function does the final cleanup:
    removes all punctuation so only pronunciation-relevant characters remain.

    Args:
        text: Input text (already validated by frontend).
        lang: Language code — 'en' for English, 'zh' for Chinese.

    Returns:
        Clean text with only scorable characters:
        - English: only letters and single quotes (for contractions like "don't")
        - Chinese: only Chinese characters (U+4E00–U+9FA5)
    """
    if not text or not text.strip():
        return ""

    if lang == 'zh':
        # Remove EVERYTHING that IS NOT a Chinese character
        return re.sub(r'[^\u4e00-\u9fa5]', '', text)
    else:
        # Remove EVERYTHING that IS NOT an English letter or a single quote
        # Keep the single quote (') because "don't" counts as a single pronounced word
        return re.sub(r"[^a-zA-Z']", '', text)


def normalize_english_text(text: str) -> str:
    """
    Normalize English text for pronunciation alignment:
    1. Lowercase
    2. Remove all non-letter, non-space, non-apostrophe characters
    3. Collapse whitespace

    Preserves word boundaries (spaces) unlike clean_text_for_scoring.
    """
    if not text or not text.strip():
        return ""

    text = text.lower()
    # Keep letters, spaces, and apostrophes (for contractions)
    text = re.sub(r"[^a-z\s']", '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text
