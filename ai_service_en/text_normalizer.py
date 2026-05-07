import re
from num2words import num2words

def normalize_transcript(text: str) -> str:
    """
    Normalizes a transcript for Wav2Vec2 forced alignment.
    Converts symbols to words, numbers to spoken words, removes punctuation,
    and converts to uppercase.
    """
    if not text:
        return ""
        
    # Map common symbols to words
    symbol_map = {
        '%': 'percent',
        '$': 'dollars',
        '&': 'and',
        '+': 'plus',
        '=': 'equals',
        '@': 'at'
    }
    
    # Replace symbols
    for symbol, word in symbol_map.items():
        text = text.replace(symbol, f" {word} ")
        
    # Find and convert numbers
    # We use regex to find standalone numbers, optionally with commas or decimals
    # e.g., 1, 2024, 1.5, 1,000
    def replace_number(match):
        num_str = match.group(0).replace(',', '')
        try:
            # Handle float vs int
            if '.' in num_str:
                num = float(num_str)
            else:
                num = int(num_str)
            
            # If it looks like a year between 1100 and 2099, read as a year
            if isinstance(num, int) and 1100 <= num <= 2099:
                return f" {num2words(num, to='year')} "
            return f" {num2words(num)} "
        except Exception:
            return match.group(0)

    text = re.sub(r'\b\d+(?:,\d{3})*(?:\.\d+)?\b', replace_number, text)
    
    # Remove all punctuation (keep alphanumeric and spaces)
    # The regex \w matches letters, numbers, and underscores. 
    # We want to keep letters and spaces. We already converted numbers, 
    # but any remaining ones will be stripped if we use strict [^A-Za-z\s].
    # Let's keep spaces, single quotes (for contractions like don't), and letters.
    # Actually, Wav2Vec2 usually expects A-Z and apostrophe.
    text = re.sub(r"[^a-zA-Z\s']", " ", text)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Convert to uppercase
    return text.upper()
