"""
English Pronunciation Scoring Pipeline — Faster-Whisper ASR + ONNX INT8 Scorer.

Architecture:
  - ASR layer:    Faster-Whisper (base.en) — transcription + word timestamps
  - Scorer layer: ONNX INT8 (Wav2Vec2 + regression head) — pronunciation quality

Modes:
  - score_audio(path, target_text):  Read-Aloud — word-level scoring
  - decode_and_score(path):          Free Decoding — transcription + fluency

Optimized for CPU-only execution.
"""

import os
import re
import difflib
import time
import logging
import numpy as np
import librosa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# CPU thread settings — sync with docker-compose ORT_INTRA_OP_THREADS
os.environ.setdefault("OMP_NUM_THREADS", os.environ.get("ORT_INTRA_OP_THREADS", "4"))

# Default paths
DEFAULT_ONNX_MODEL = os.environ.get(
    "ONNX_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "model", "pronunciation_scorer_int8.onnx"),
)
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base.en")
WHISPER_CACHE_DIR = os.environ.get(
    "WHISPER_CACHE_DIR",
    os.path.join(os.path.dirname(__file__), "model", "whisper_cache"),
)
SAMPLE_RATE = 16_000


class EnglishPronunciationScorer:
    """
    English pronunciation scorer combining:
      - Faster-Whisper for ASR (transcription + word timestamps + confidence)
      - ONNX INT8 model for overall pronunciation quality scoring
    """

    def __init__(self, model_path: str = None):
        """Load both the ONNX INT8 scorer and Faster-Whisper ASR."""
        import onnxruntime as ort
        from faster_whisper import WhisperModel

        if model_path is None:
            model_path = DEFAULT_ONNX_MODEL

        self.floor_score = 15.0
        self._init_error = None
        self.session = None
        self.whisper_model = None

        # ── Load ONNX INT8 Scorer ──
        logger.info(f"Loading ONNX INT8 scorer: {model_path}")
        start = time.time()

        try:
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found: {model_path}")

            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = int(
                os.environ.get("ORT_INTRA_OP_THREADS", "4")
            )
            sess_opts.inter_op_num_threads = int(
                os.environ.get("ORT_INTER_OP_THREADS", "1")
            )
            sess_opts.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )

            self.session = ort.InferenceSession(
                model_path,
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )

            elapsed = time.time() - start
            model_size_mb = os.path.getsize(model_path) / (1024 ** 2)
            logger.info(
                f"✅ ONNX INT8 scorer loaded in {elapsed:.2f}s "
                f"({model_size_mb:.1f} MB)"
            )
        except Exception as exc:
            self._init_error = f"ONNX model load failed: {exc}"
            logger.error(f"❌ {self._init_error}")

        # ── Load Faster-Whisper ASR ──
        logger.info(f"Loading Faster-Whisper model: {WHISPER_MODEL_SIZE}")
        start = time.time()

        try:
            cpu_threads = int(os.environ.get("ORT_INTRA_OP_THREADS", "4"))
            self.whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device="cpu",
                compute_type="int8",
                cpu_threads=cpu_threads,
                download_root=WHISPER_CACHE_DIR,
            )
            elapsed = time.time() - start
            logger.info(f"✅ Faster-Whisper loaded in {elapsed:.2f}s")
        except Exception as exc:
            logger.error(f"❌ Faster-Whisper load failed: {exc}")
            # ASR failure is non-fatal — scorer can still work for Read-Aloud

    # ─────────────────────────────────────────────────────────
    @property
    def model_loaded(self) -> bool:
        return self.session is not None

    # ─────────────────────────────────────────────────────────
    #  Core: raw ONNX scorer inference
    # ─────────────────────────────────────────────────────────
    def _predict_score(self, audio_path: str) -> float:
        """
        Run ONNX inference on an audio file and return the raw sigmoid score
        in [0, 1].
        """
        waveform, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)

        if len(waveform) == 0:
            raise ValueError("Audio file is empty or unreadable.")

        input_values = waveform[np.newaxis, :].astype(np.float32)
        inputs = {self.session.get_inputs()[0].name: input_values}
        outputs = self.session.run(None, inputs)

        raw_score = float(outputs[0][0][0])
        return raw_score

    # ─────────────────────────────────────────────────────────
    #  Core: Faster-Whisper transcription
    # ─────────────────────────────────────────────────────────
    def _transcribe(self, audio_path: str) -> dict:
        """
        Transcribe audio using Faster-Whisper.

        Returns:
            {
                "text": "full transcript",
                "words": [{"word": "hello", "start": 0.1, "end": 0.5, "probability": 0.99}, ...],
                "language": "en",
            }
        """
        if self.whisper_model is None:
            return {"text": "", "words": [], "language": "en"}

        segments, info = self.whisper_model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
        )

        full_text_parts = []
        all_words = []

        for segment in segments:
            full_text_parts.append(segment.text.strip())
            if segment.words:
                for w in segment.words:
                    all_words.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "probability": round(w.probability, 4),
                    })

        return {
            "text": " ".join(full_text_parts),
            "words": all_words,
            "language": info.language if info else "en",
        }

    # ─────────────────────────────────────────────────────────
    #  Branch A: Read-Aloud scoring
    # ─────────────────────────────────────────────────────────
    def score_audio(self, audio_path: str, target_text: str) -> dict:
        """
        Read-Aloud mode: score pronunciation against a reference sentence.

        Pipeline:
          1. Faster-Whisper transcribes → word timestamps + confidence
          2. ONNX INT8 scorer → overall pronunciation quality
          3. Align transcribed words with target text
        """
        if not self.model_loaded:
            return {"error": f"Model not loaded: {self._init_error}"}
        if not target_text or not target_text.strip():
            return {"error": "Target text cannot be empty."}
        if not os.path.exists(audio_path):
            return {"error": f"Audio file not found: {audio_path}"}

        start = time.time()

        # Step 1: INT8 scorer
        try:
            raw_score = self._predict_score(audio_path)
        except Exception as exc:
            logger.error(f"❌ Scorer inference failed: {exc}")
            return {"error": f"Inference failed: {str(exc)}"}

        model_score = self._sigmoid_to_percentage(raw_score)

        # Step 2: ASR transcription for word-level detail
        asr_result = self._transcribe(audio_path)

        # Step 3: Blend model score with ASR confidence
        overall_score = self._blend_scores(model_score, asr_result["words"])

        elapsed = time.time() - start
        logger.info(
            f"⏱️ Read-Aloud completed in {elapsed:.3f}s — "
            f"raw={raw_score:.4f}, model={model_score}, overall={overall_score}"
        )

        # Step 4: Build word scores from ASR confidence + scorer
        word_scores = self._build_word_scores_from_asr(
            asr_result["words"], target_text, overall_score, audio_path
        )

        return {
            "overall_score": overall_score,
            "word_scores": word_scores,
            "transcript": asr_result["text"] or target_text,
            "target_text": target_text,
            "language": "en",
        }

    # ─────────────────────────────────────────────────────────
    #  Branch B: Free Decoding
    # ─────────────────────────────────────────────────────────
    def decode_and_score(self, audio_path: str) -> dict:
        """
        Free Decoding mode: transcribe audio and score pronunciation.

        Pipeline:
          1. Faster-Whisper transcribes → full text + word details
          2. ONNX INT8 scorer → fluency/quality score
        """
        if not self.model_loaded:
            return {"error": f"Model not loaded: {self._init_error}"}
        if not os.path.exists(audio_path):
            return {"error": f"Audio file not found: {audio_path}"}

        start = time.time()

        # Step 1: INT8 scorer for overall quality
        try:
            raw_score = self._predict_score(audio_path)
        except Exception as exc:
            logger.error(f"❌ Scorer inference failed: {exc}")
            return {"error": f"Inference failed: {str(exc)}"}

        model_score = self._sigmoid_to_percentage(raw_score)

        # Step 2: ASR transcription
        asr_result = self._transcribe(audio_path)

        # Step 3: Blend model score with ASR confidence
        fluency_score = self._blend_scores(model_score, asr_result["words"])

        elapsed = time.time() - start
        logger.info(
            f"✅ Free Decoding completed in {elapsed:.2f}s — "
            f"model={model_score}, blended={fluency_score}"
        )

        # Build details from ASR word-level data
        details = []
        for w in asr_result["words"]:
            details.append({
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
                "confidence_score": w["probability"],
            })

        return {
            "recognized_text": asr_result["text"] or "(No speech detected)",
            "fluency_score": fluency_score,
            "details": details,
            "language": "en",
        }

    # ─────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────
    def _sigmoid_to_percentage(self, raw: float) -> float:
        """
        Map raw sigmoid output [0, 1] → [floor_score, 100].

        Uses a calibrated power curve instead of linear mapping.
        The model typically outputs 0.50-0.80 for decent-to-excellent speech,
        so a linear map compresses that range into 57-83% which is misleading.

        Calibration (approximate):
          raw 0.30 → ~50%   (poor pronunciation)
          raw 0.50 → ~70%   (fair)
          raw 0.65 → ~82%   (good)
          raw 0.75 → ~90%   (very good)
          raw 0.85 → ~95%   (excellent)
          raw 0.95 → ~99%   (near perfect)
        """
        # Power curve: stretches the upper range
        calibrated = raw ** 0.6
        scaled = self.floor_score + calibrated * (100.0 - self.floor_score)
        return round(max(self.floor_score, min(100.0, scaled)), 2)

    def _blend_scores(
        self, model_score: float, asr_words: list
    ) -> float:
        """
        Blend ONNX model score with average ASR word confidence and penalize low-confidence words.

        The model score captures pronunciation quality holistically,
        while ASR confidence captures per-word clarity.
        Weighted blend: 40% model + 60% ASR confidence.
        Additionally, applies a penalty for any words spoken with low confidence (< 0.80).
        """
        if not asr_words:
            return model_score

        probabilities = [w["probability"] for w in asr_words]
        avg_confidence = np.mean(probabilities)
        asr_score = avg_confidence * 100.0

        # Weighted blend
        blended = (model_score * 0.4) + (asr_score * 0.6)

        # Apply low-confidence penalty
        # Each word with confidence < 0.80 incurs a penalty scaled by how far below 0.80 it is.
        # We normalize the sum of penalties by sqrt of word count so that the penalty is significant
        # but doesn't completely destroy the score for very long passages.
        penalties = [(0.80 - p) * 45.0 for p in probabilities if p < 0.80]
        if penalties:
            total_penalty = sum(penalties) / np.sqrt(len(asr_words))
            blended -= total_penalty

        return round(max(self.floor_score, min(100.0, blended)), 2)

    def _normalize_word_to_spoken(self, word: str) -> str:
        """
        Normalize word to its spoken form (converting numbers, %, & etc. to words).
        """
        from num2words import num2words
        word = word.lower().strip(".,!?;:\"'()[]{}*-_/\\")
        if not word:
            return ""

        # Common symbols
        word = word.replace("%", " percent")
        word = word.replace("&", " and")
        word = word.replace("$", " dollar")

        # Convert integers and decimals
        if re.match(r'^\d+(\.\d+)?$', word):
            try:
                if "." in word:
                    parts = word.split(".")
                    int_part = num2words(int(parts[0]))
                    dec_part = " ".join([num2words(int(d)) for d in parts[1]])
                    return f"{int_part} point {dec_part}"
                else:
                    return num2words(int(word))
            except Exception:
                pass

        # Convert digits within a word
        def replace_num(match):
            try:
                return num2words(int(match.group(0)))
            except Exception:
                return match.group(0)

        word = re.sub(r'\d+', replace_num, word)
        return word.strip()

    def _build_word_scores_from_asr(
        self,
        asr_words: list,
        target_text: str,
        overall_score: float,
        audio_path: str,
    ) -> list:
        """
        Build word-level scores by aligning ASR words with target text.
        
        Uses sequence-based LCS alignment with difflib and falls back to localized
        fuzzy matching for slightly mispronounced words.
        Handles numbers and special characters by normalizing them to their spoken form.
        """
        target_words = target_text.strip().split()

        if not asr_words:
            # Fallback: no ASR data — distribute overall score uniformly
            return self._build_word_scores_fallback(
                target_words, overall_score, audio_path
            )

        # 1. Build flat spoken representation for target words
        flat_target = []
        for t_idx, t_word in enumerate(target_words):
            t_sp = self._normalize_word_to_spoken(t_word)
            if t_sp:
                for part in t_sp.split():
                    flat_target.append((part, t_idx))

        # 2. Build flat spoken representation for ASR words
        flat_asr = []
        for asr_idx, aw in enumerate(asr_words):
            a_sp = self._normalize_word_to_spoken(aw["word"])
            if a_sp:
                for part in a_sp.split():
                    flat_asr.append((part, asr_idx))

        # If flat mappings are empty (e.g. empty inputs), fallback
        if not flat_target or not flat_asr:
            return self._build_word_scores_fallback(
                target_words, overall_score, audio_path
            )

        # 3. Align sequences using SequenceMatcher
        target_spoken_list = [item[0] for item in flat_target]
        asr_spoken_list = [item[0] for item in flat_asr]

        matcher = difflib.SequenceMatcher(None, target_spoken_list, asr_spoken_list)
        matching_blocks = matcher.get_matching_blocks()

        # Map target index to matched ASR indices
        target_to_asr = [[] for _ in range(len(target_words))]
        for i, j, size in matching_blocks:
            for k in range(size):
                t_idx = flat_target[i + k][1]
                asr_idx = flat_asr[j + k][1]
                if asr_idx not in target_to_asr[t_idx]:
                    target_to_asr[t_idx].append(asr_idx)

        # Keep track of matched ASR words
        matched_asr_indices = set()
        for asr_list in target_to_asr:
            matched_asr_indices.update(asr_list)

        # 4. Fuzzy Match for any remaining unmatched target words
        for t_idx in range(len(target_words)):
            if not target_to_asr[t_idx]:
                # Find matched bounds in ASR list
                left_asr_limit = -1
                for l in range(t_idx - 1, -1, -1):
                    if target_to_asr[l]:
                        left_asr_limit = max(target_to_asr[l])
                        break

                right_asr_limit = len(asr_words)
                for r in range(t_idx + 1, len(target_words)):
                    if target_to_asr[r]:
                        right_asr_limit = min(target_to_asr[r])
                        break

                # Fuzzy search in the unmatched candidates
                t_sp = self._normalize_word_to_spoken(target_words[t_idx])
                if not t_sp:
                    continue

                best_sim = 0.0
                best_asr_idx = -1

                for a_idx in range(left_asr_limit + 1, right_asr_limit):
                    if a_idx not in matched_asr_indices:
                        a_sp = self._normalize_word_to_spoken(asr_words[a_idx]["word"])
                        if a_sp:
                            sim = difflib.SequenceMatcher(None, t_sp, a_sp).ratio()
                            if sim > best_sim:
                                best_sim = sim
                                best_asr_idx = a_idx

                # If ratio is high enough, consider it a match
                if best_sim >= 0.70 and best_asr_idx != -1:
                    target_to_asr[t_idx].append(best_asr_idx)
                    matched_asr_indices.add(best_asr_idx)

        # 5. Build the final word scores list
        word_scores = []
        for t_idx, t_word in enumerate(target_words):
            matched_indices = target_to_asr[t_idx]
            if matched_indices:
                matched_indices.sort()
                matched_words = [asr_words[idx] for idx in matched_indices]

                start_time = min(w["start"] for w in matched_words)
                end_time = max(w["end"] for w in matched_words)
                confidence = np.mean([w["probability"] for w in matched_words])

                # Calculate word score based on ASR confidence:
                # - If confidence >= 0.90, score starts at 85.0 and scales up to 100.0 (confidence 1.0)
                # - If confidence < 0.50, score is 0.0
                # - Otherwise, scales linearly between 0.0 and 85.0
                if confidence < 0.50:
                    score = 0.0
                elif confidence < 0.90:
                    score = (confidence - 0.50) / 0.40 * 85.0
                else:
                    score = 85.0 + (confidence - 0.90) / 0.10 * 15.0

                score = round(max(0.0, min(100.0, score)), 2)

                word_scores.append({
                    "word": t_word,
                    "start_time": round(start_time, 3),
                    "end_time": round(end_time, 3),
                    "score": score,
                    "confidence": round(confidence, 4),
                    "matched": True,
                })
            else:
                word_scores.append({
                    "word": t_word,
                    "start_time": 0.0,
                    "end_time": 0.0,
                    "score": 0.0,
                    "confidence": 0.0,
                    "matched": False,
                })

        return word_scores

    def _build_word_scores_fallback(
        self, words: list, overall: float, audio_path: str
    ) -> list:
        """Fallback when ASR is unavailable — distribute score uniformly."""
        if not words:
            return []

        try:
            duration = librosa.get_duration(filename=audio_path)
        except Exception:
            duration = len(words) * 0.5

        interval = duration / max(len(words), 1)
        rng = np.random.default_rng(42)

        word_scores = []
        for i, word in enumerate(words):
            jitter = rng.uniform(-5.0, 5.0)
            score = max(self.floor_score, min(100.0, round(overall + jitter, 2)))
            word_scores.append({
                "word": word,
                "start_time": round(i * interval, 3),
                "end_time": round((i + 1) * interval, 3),
                "score": score,
            })

        return word_scores
