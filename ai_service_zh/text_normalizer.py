"""
Chinese text normalization for pronunciation scoring.
Handles punctuation removal and basic text cleanup for alignment.
"""
import re
import unicodedata


def normalize_chinese_text(text: str) -> str:
    """
    Normalize Chinese text for pronunciation alignment:
    1. Remove all punctuation (Chinese and English)
    2. Normalize unicode characters
    3. Collapse whitespace
    4. Return cleaned text suitable for ASR comparison
    """
    if not text or not text.strip():
        return ""

    # Unicode normalize (NFC form for Chinese characters)
    text = unicodedata.normalize('NFC', text)

    # Remove all punctuation (both Chinese and English)
    # Chinese punctuation: ，。！？、；：""''（）《》【】…—
    chinese_punct = r'[，。！？、；：""''（）《》【】…—·「」『』〈〉〔〕\u3000]'
    text = re.sub(chinese_punct, ' ', text)

    # Remove English punctuation
    english_punct = r'[!"#$%&\'()*+,\-./:;<=>?@\[\\\]^_`{|}~]'
    text = re.sub(english_punct, ' ', text)

    # Remove digits
    text = re.sub(r'\d+', '', text)

    # Collapse whitespace and strip
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def clean_text_for_scoring(text: str, lang: str = 'zh') -> str:
    """
    The "Vacuum Cleaner" — strips EVERYTHING except scorable characters.

    By the time text reaches this function, the Next.js frontend has already
    validated that input contains only letters/Chinese characters and punctuation
    (no numbers, no math symbols). This function does the final cleanup:
    removes all punctuation so only pronunciation-relevant characters remain.

    Args:
        text: Input text (already validated by frontend).
        lang: Language code — 'zh' for Chinese, 'en' for English.

    Returns:
        Clean text with only scorable characters:
        - Chinese: only Chinese characters (U+4E00–U+9FA5)
        - English: only letters and single quotes (for contractions like "don't")
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


def get_pinyin_for_text(text: str) -> list:
    """
    Get pinyin for Chinese text. Returns list of (char, pinyin) tuples.
    Requires pypinyin to be installed.
    """
    try:
        from pypinyin import pinyin, Style
        chars = normalize_chinese_text(text).replace(' ', '')
        py_list = pinyin(chars, style=Style.TONE3, errors='ignore')
        result = []
        for char, py in zip(chars, py_list):
            result.append({
                'character': char,
                'pinyin': py[0] if py else '',
            })
        return result
    except ImportError:
        # Fallback if pypinyin not available
        return [{'character': c, 'pinyin': ''} for c in text if c.strip()]
