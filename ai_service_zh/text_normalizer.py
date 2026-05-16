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
