"""
English Pronunciation Scoring Pipeline using Faster-Whisper.

Replaces the previous Wav2Vec2 + ONNX pipeline with a unified
Faster-Whisper Large-v3 (CTranslate2 INT8) approach.

Provides:
- Read-Aloud scoring (word-level confidence against target text)
- Free Decoding (ASR with fluency estimation)

Optimized for CPU-only execution (INT8 quantization via CTranslate2).
"""
import os
import sys
import json
import time
import logging
import numpy as np
import math

# CPU thread optimization
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('CT2_INTER_THREADS', '1')
os.environ.setdefault('CT2_INTRA_THREADS', '2')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Default model to use
DEFAULT_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "distil-large-v3")


class PronunciationScorer:
    """
    English pronunciation scorer using Faster-Whisper (CTranslate2).

    Modes:
        - score_audio(path, target_text): Read-Aloud — word-level confidence scoring
        - decode_and_score(path): Free Decoding — transcription + fluency score

    All inference runs on CPU with INT8 quantization.
    """

    def __init__(self, model_size=None, models_cache_dir=None):
        """Initialize Faster-Whisper model with INT8 quantization for CPU."""
        from faster_whisper import WhisperModel

        if model_size is None:
            model_size = DEFAULT_MODEL_SIZE

        if models_cache_dir is None:
            models_cache_dir = os.path.join(os.path.dirname(__file__), "models_cache")

        self.floor_score = 15.0

        logger.info(f"Loading Faster-Whisper model: {model_size}")
        logger.info(f"  device=cpu, compute_type=int8")

        start_time = time.time()

        # Detect model location — check multiple possible paths
        # 1) models_cache/model.bin (root — download_models.py places files here)
        # 2) models_cache/<model_size>/model.bin (subfolder)
        # 3) Fallback: auto-download from HuggingFace
        root_model = os.path.join(models_cache_dir, "model.bin")
        subfolder_model = os.path.join(models_cache_dir, model_size, "model.bin")

        if os.path.isfile(root_model):
            model_path = models_cache_dir
            logger.info(f"  📦 Loading from local cache (root): {model_path}")
        elif os.path.isfile(subfolder_model):
            model_path = os.path.join(models_cache_dir, model_size)
            logger.info(f"  📦 Loading from local cache (subfolder): {model_path}")
        else:
            logger.info(f"  ⬇️ Model not found locally. Will download from HuggingFace.")
            model_path = model_size

        self.model = WhisperModel(
            model_path,
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            download_root=models_cache_dir,
        )

        load_time = time.time() - start_time
        logger.info(f"✅ Model loaded in {load_time:.1f}s")

    def score_audio(self, audio_path: str, target_text: str) -> dict:
        """
        Read-Aloud mode: Transcribe audio and score each word against the target text.

        Uses Whisper's word-level timestamps and probability scores to provide
        per-word confidence, then aligns against the target text for pedagogical feedback.

        Returns:
            {
                "overall_score": float,
                "word_scores": [{"word": str, "start_time": float, "end_time": float, "score": float}, ...],
                "transcript": str,
                "target_text": str
            }
        """
        if not target_text or not target_text.strip():
            return {"error": "Target text cannot be empty."}

        # Transcribe with word-level timestamps
        transcription_result = self._transcribe(audio_path)
        if "error" in transcription_result:
            return transcription_result

        words = transcription_result["words"]
        transcript = transcription_result["text"]

        if not words:
            return {"error": "No words recognized in audio."}

        # Normalize target text for comparison
        target_clean = self._normalize(target_text)
        target_words = target_clean.split()

        # Build word scores from Whisper confidence probabilities
        whisper_scores = []
        for w in words:
            confidence = w.get("probability", 0.0)
            score = self._confidence_to_pedagogical_score(confidence)
            whisper_scores.append({
                "word": w["word"],
                "start_time": round(w["start"], 3),
                "end_time": round(w["end"], 3),
                "score": round(score, 2),
            })

        # If target text provided, align and score against it
        if target_words:
            aligned_scores = self._align_with_target(
                whisper_scores, target_words, target_text, transcript
            )
        else:
            aligned_scores = whisper_scores

        # Compute overall score using Harmonic Mean (penalizes low scores heavily)
        if aligned_scores:
            scores = [w["score"] for w in aligned_scores]
            
            # alpha càng lớn, từ điểm thấp càng kéo điểm tổng xuống sâu (thử 0.05 - 0.1)
            alpha = 0.05
            weights = [math.exp(alpha * (100.0 - s)) for s in scores]
            
            weighted_sum = sum(w * s for w, s in zip(weights, scores))
            overall_score = max(self.floor_score, min(100.0, round(weighted_sum / sum(weights), 2)))
        else:
            overall_score = self.floor_score

        return {
            "overall_score": overall_score,
            "word_scores": aligned_scores,
            "transcript": transcript,
            "target_text": target_text,
        }

    def decode_and_score(self, audio_path: str) -> dict:
        """
        Free Decoding mode: Transcribe speech and estimate fluency.

        Returns:
            {
                "recognized_text": str,
                "fluency_score": float,
                "details": [{"word": str, "start": float, "end": float, "confidence_score": float}, ...]
            }
        """
        transcription_result = self._transcribe(audio_path)
        if "error" in transcription_result:
            return transcription_result

        text = transcription_result["text"]
        words = transcription_result["words"]

        if not text or not words:
            return {
                "recognized_text": "No speech detected",
                "fluency_score": self.floor_score,
                "details": [],
            }

        # Build word-level details with raw confidence
        details = []
        confidence_values = []
        for w in words:
            prob = w.get("probability", 0.0)
            confidence_values.append(prob)
            details.append({
                "word": w["word"],
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "confidence_score": round(prob, 4),
            })

        # Fluency score: blend of average confidence + speech rate
        avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0

        # Speech rate analysis
        if words:
            total_duration = words[-1]["end"] - words[0]["start"]
            words_per_second = len(words) / max(total_duration, 0.1)
            # Normal English: 2-3 words/sec. Too fast or too slow reduces score
            if 1.5 <= words_per_second <= 4.0:
                rate_factor = 1.0
            elif words_per_second > 4.0:
                rate_factor = max(0.6, 1.0 - (words_per_second - 4.0) * 0.1)
            else:
                rate_factor = max(0.5, words_per_second / 1.5)
        else:
            rate_factor = 0.5

        # Final fluency: 70% confidence + 30% speech rate
        fluency_raw = (0.7 * avg_confidence + 0.3 * rate_factor) * 100.0
        fluency_score = max(self.floor_score, min(100.0, round(fluency_raw, 2)))

        return {
            "recognized_text": text,
            "fluency_score": fluency_score,
            "details": details,
        }

    def _transcribe(self, audio_path: str) -> dict:
        """
        Core transcription using Faster-Whisper.
        Returns {"text": str, "words": list[dict]} or {"error": str}.
        """
        if not os.path.exists(audio_path):
            return {"error": f"Audio file not found: {audio_path}"}

        start_time = time.time()

        try:
            segments, info = self.model.transcribe(
                audio_path,
                language="en",
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=300,
                    speech_pad_ms=200,
                ),
                beam_size=5,
            )

            # Consume the generator to extract all segments and words
            full_text = ""
            all_words = []

            for segment in segments:
                full_text += segment.text
                if segment.words:
                    for w in segment.words:
                        all_words.append({
                            "word": w.word.strip(),
                            "start": w.start,
                            "end": w.end,
                            "probability": w.probability,
                        })

            full_text = full_text.strip()
            elapsed = time.time() - start_time
            logger.info(f"⏱️ Transcription completed in {elapsed:.2f}s — {len(all_words)} words")

            if not full_text:
                return {"error": "No speech detected in audio."}

            return {"text": full_text, "words": all_words}

        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            return {"error": f"Transcription failed: {str(e)}"}

    def _confidence_to_pedagogical_score(self, confidence: float) -> float:
        """
        Map Whisper's raw word probability [0.0, 1.0] to a pedagogical score [15.0, 100.0].

        Scoring tiers:
            - confidence >= 0.80 → 85-100 (Excellent)
            - confidence >= 0.60 → 65-85  (Good)
            - confidence >= 0.40 → 40-65  (Needs Improvement)
            - confidence <  0.40 → 15-40  (Poor)
        """
        if confidence >= 0.90:   # Trước đây là 0.80
            score = 85.0 + (confidence - 0.90) / 0.10 * 15.0
        elif confidence >= 0.70: # Trước đây là 0.60
            score = 65.0 + (confidence - 0.70) / 0.20 * 20.0
        elif confidence >= 0.40:
            score = 40.0 + (confidence - 0.40) / 0.30 * 25.0
        else:
            score = self.floor_score + (confidence / 0.40) * (40.0 - self.floor_score)

        return max(self.floor_score, min(100.0, score))

    def _align_with_target(
        self, whisper_scores: list, target_words: list,
        original_target: str = "", raw_transcript: str = "",
    ) -> list:
        """
        Align Whisper-recognized words with target text words.
        Unmatched target words get floor_score to penalize missed words.

        Numeric tokens (e.g. "1%") are handled specially:
        - Whisper often skips them in word timestamps
        - We check the raw transcript instead
        """
        import re

        def clean_word(w):
            """Strip punctuation and lowercase for comparison."""
            return re.sub(r"[^a-zA-Z']", "", w).lower().strip()

        # Find numeric/symbol tokens from original target to handle separately
        numeric_tokens = set(re.findall(r'[\d$%€£]+[\d.,/$%€£]*', original_target))

        recognized_clean = [clean_word(w["word"]) for w in whisper_scores]
        aligned = []
        r_idx = 0
        transcript_lower = raw_transcript.lower()

        for target_word in target_words:
            target_clean = clean_word(target_word)

            if not target_clean:
                continue

            # Direct match
            if r_idx < len(recognized_clean) and recognized_clean[r_idx] == target_clean:
                ws = whisper_scores[r_idx].copy()
                ws["word"] = target_word.upper()
                aligned.append(ws)
                r_idx += 1
                continue

            # Look-ahead (within window of 5 to handle inserted/extra words)
            found = False
            for look in range(1, min(6, len(recognized_clean) - r_idx)):
                if recognized_clean[r_idx + look] == target_clean:
                    ws = whisper_scores[r_idx + look].copy()
                    ws["word"] = target_word.upper()
                    # Penalize slightly for misalignment
                    ws["score"] = max(self.floor_score, ws["score"] * 0.9)
                    aligned.append(ws)
                    r_idx = r_idx + look + 1
                    found = True
                    break

            if not found:
                # Check if this word was expanded from a numeric token
                # e.g. "ONE" and "PERCENT" came from "1%"
                is_from_number = any(
                    target_clean in self._expand_numbers(tok).lower().split()
                    for tok in numeric_tokens
                )

                if is_from_number:
                    # Check if the original numeric token exists in Whisper's transcript
                    token_found_in_transcript = any(
                        tok in raw_transcript for tok in numeric_tokens
                    )
                    if token_found_in_transcript:
                        # Student read it — Whisper confirmed in transcript.
                        # Give auto-pass score (don't penalize for Whisper's
                        # inability to produce word timestamps for numbers).
                        aligned.append({
                            "word": target_word.upper(),
                            "start_time": 0.0,
                            "end_time": 0.0,
                            "score": 95.0,  # auto-pass
                        })
                    else:
                        # Student did NOT read the number correctly
                        aligned.append({
                            "word": target_word.upper(),
                            "start_time": 0.0,
                            "end_time": 0.0,
                            "score": self.floor_score,
                        })
                else:
                    # Regular word not found — floor score
                    aligned.append({
                        "word": target_word.upper(),
                        "start_time": 0.0,
                        "end_time": 0.0,
                        "score": self.floor_score,
                    })

        return aligned

    def _normalize(self, text: str) -> str:
        """
        Normalize text for comparison:
        1. Expand numbers/symbols to English words (e.g. "1%" → "one percent")
        2. Strip remaining non-alphabetic characters
        3. Uppercase
        """
        import re
        text = self._expand_numbers(text)
        text = re.sub(r"[^a-zA-Z\s']", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text.upper()

    @staticmethod
    def _expand_numbers(text: str) -> str:
        """
        Expand numbers and symbols to English words.
        Handles: percentages, dollars, ordinals, decimals, plain numbers.
        """
        import re

        ones = ["", "one", "two", "three", "four", "five", "six", "seven",
                "eight", "nine", "ten", "eleven", "twelve", "thirteen",
                "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
        tens = ["", "", "twenty", "thirty", "forty", "fifty",
                "sixty", "seventy", "eighty", "ninety"]

        def num_to_words(n):
            """Convert integer 0-9999 to English words."""
            if n < 0:
                return "minus " + num_to_words(-n)
            if n == 0:
                return "zero"
            if n < 20:
                return ones[n]
            if n < 100:
                return tens[n // 10] + ("" if n % 10 == 0 else " " + ones[n % 10])
            if n < 1000:
                remainder = n % 100
                r_str = " " + num_to_words(remainder) if remainder else ""
                return ones[n // 100] + " hundred" + r_str
            if n < 10000:
                remainder = n % 1000
                r_str = " " + num_to_words(remainder) if remainder else ""
                return num_to_words(n // 1000) + " thousand" + r_str
            return str(n)

        ordinals = {
            "1st": "first", "2nd": "second", "3rd": "third",
            "4th": "fourth", "5th": "fifth", "6th": "sixth",
            "7th": "seventh", "8th": "eighth", "9th": "ninth",
            "10th": "tenth", "11th": "eleventh", "12th": "twelfth",
            "13th": "thirteenth", "20th": "twentieth", "21st": "twenty first",
            "30th": "thirtieth", "100th": "hundredth",
        }

        # Ordinals (1st, 2nd, 3rd, etc.)
        for k, v in ordinals.items():
            text = re.sub(r'\b' + re.escape(k) + r'\b', v, text, flags=re.IGNORECASE)

        # Percentages: "1%" → "one percent"
        def replace_percent(m):
            n = float(m.group(1))
            if n == int(n):
                return num_to_words(int(n)) + " percent"
            # Handle decimals like 2.5%
            parts = m.group(1).split(".")
            whole = num_to_words(int(parts[0]))
            decimal = " point " + " ".join(num_to_words(int(d)) for d in parts[1])
            return whole + decimal + " percent"
        text = re.sub(r'(\d+\.?\d*)%', replace_percent, text)

        # Dollar amounts: "$500" → "five hundred dollars"
        def replace_dollar(m):
            n = int(m.group(1))
            return num_to_words(n) + " dollars"
        text = re.sub(r'\$(\d+)', replace_dollar, text)

        # Standalone numbers
        def replace_number(m):
            return num_to_words(int(m.group(0)))
        text = re.sub(r'\b\d+\b', replace_number, text)

        return text


if __name__ == "__main__":
    logger.info("=== English Pronunciation Scoring Pipeline (Faster-Whisper) ===")

    try:
        scorer = PronunciationScorer()
    except Exception as e:
        logger.error(f"Failed to initialize pipeline: {e}")
        sys.exit(1)

    if len(sys.argv) > 2:
        audio_file = sys.argv[1]
        transcript_text = sys.argv[2]

        if os.path.exists(audio_file):
            result = scorer.score_audio(audio_file, transcript_text)
            print("\n--- Read-Aloud Score ---")
            print(json.dumps(result, indent=2))
        else:
            print(f"Error: Audio file {audio_file} does not exist.")
    elif len(sys.argv) > 1:
        audio_file = sys.argv[1]
        if os.path.exists(audio_file):
            result = scorer.decode_and_score(audio_file)
            print("\n--- Free Decoding Result ---")
            print(json.dumps(result, indent=2))
        else:
            print(f"Error: Audio file {audio_file} does not exist.")
    else:
        print("\nUsage:")
        print('  Read-Aloud:   python inference_pipeline.py <audio.wav> "TARGET TEXT"')
        print("  Free Decode:  python inference_pipeline.py <audio.wav>")
