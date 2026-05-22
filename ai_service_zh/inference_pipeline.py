"""
Chinese Pronunciation Scoring Pipeline using FunASR (Alibaba DAMO Academy).

Replaces the previous Sherpa-ONNX pipeline with FunASR's Paraformer-zh model,
which provides:
- High-accuracy Chinese ASR with character-level timestamps
- Built-in VAD (Voice Activity Detection)
- Optional punctuation restoration

Modes:
- Read-Aloud: Character-level scoring against target text with pinyin/tone
- Free Decoding: Transcription with fluency estimation

Optimized for CPU-only execution.
"""
import os
import sys
import json
import time
import logging
import numpy as np

# CPU thread optimization
os.environ.setdefault('OMP_NUM_THREADS', '2')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Default model — Paraformer-zh is the best open-source Chinese ASR model
DEFAULT_MODEL = os.environ.get("FUNASR_MODEL", "paraformer-zh")
DEFAULT_VAD_MODEL = os.environ.get("FUNASR_VAD_MODEL", "fsmn-vad")


class ChinesePronunciationScorer:
    """
    Chinese pronunciation scorer using FunASR Paraformer-zh.

    Modes:
        - score_audio(path, target_text): Read-Aloud — character-level scoring
        - decode_and_score(path): Free Decoding — transcription + fluency score
    """

    def __init__(self, model_name=None, cache_dir=None):
        """Initialize FunASR Paraformer model."""
        from funasr import AutoModel

        if model_name is None:
            model_name = DEFAULT_MODEL
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(__file__), "models_cache")

        self.floor_score = 15.0
        self._init_error = None

        logger.info(f"Loading FunASR model: {model_name}")
        logger.info(f"  Cache directory: {cache_dir}")

        start_time = time.time()

        try:
            os.makedirs(cache_dir, exist_ok=True)

            # Point ModelScope to local cache (pre-downloaded on host)
            os.environ["MODELSCOPE_CACHE"] = cache_dir
            logger.info(f"  MODELSCOPE_CACHE={cache_dir}")

            import torch
            self._torch = torch
            cuda_available = torch.cuda.is_available()
            self._use_cuda = cuda_available
            
            if cuda_available:
                logger.info("CUDA is available. Initializing FunASR model on GPU (AMP FP16).")
                self.model = AutoModel(
                    model=model_name,
                    vad_model=DEFAULT_VAD_MODEL,
                    device="cuda",
                    fp16=False,
                    hub="ms",
                    disable_update=True,
                )
            else:
                logger.info("CUDA not available. Initializing FunASR model on CPU.")
                self.model = AutoModel(
                    model=model_name,
                    vad_model=DEFAULT_VAD_MODEL,
                    device="cpu",
                    hub="ms",
                    disable_update=True,
                )

            load_time = time.time() - start_time
            logger.info(f"✅ FunASR model loaded in {load_time:.1f}s")

        except Exception as e:
            self._init_error = f"FunASR init failed: {e}"
            self.model = None
            logger.error(f"❌ {self._init_error}")
            import traceback
            traceback.print_exc()

    @property
    def model_loaded(self) -> bool:
        """Check if the ASR model is ready."""
        return self.model is not None

    def score_audio(self, audio_path: str, target_text: str) -> dict:
        """
        Read-Aloud mode: Compare spoken audio against target Chinese text.
        Returns character-level scores with pinyin and tone information.
        """
        if not self.model_loaded:
            return {"error": f"Chinese ASR model not loaded: {self._init_error}"}

        if not target_text or not target_text.strip():
            return {"error": "Target text cannot be empty."}

        if not os.path.exists(audio_path):
            return {"error": f"Audio file not found: {audio_path}"}

        start_time = time.time()

        # Run FunASR transcription
        try:
            results = self.model.generate(
                input=audio_path,
                batch_size_s=60,
            )
        except Exception as e:
            logger.error(f"❌ FunASR generate failed: {e}")
            return {"error": f"ASR transcription failed: {str(e)}"}

        elapsed = time.time() - start_time
        logger.info(f"⏱️ Transcription completed in {elapsed:.2f}s")

        if not results or not results[0].get("text"):
            return {"error": "No speech detected in audio."}

        recognized_text = results[0]["text"]
        timestamp_data = results[0].get("timestamp", [])

        logger.info(f"🔤 Recognized: {recognized_text}")

        # Score against target text
        char_scores, overall_score = self._calculate_character_scores(
            recognized_text, target_text, timestamp_data
        )

        # Add pinyin information
        char_scores = self._add_pinyin_to_scores(char_scores)

        # Build word_scores for API compatibility
        word_scores = []
        for cs in char_scores:
            word_scores.append({
                'word': cs['character'],
                'start_time': cs.get('start_time', 0.0),
                'end_time': cs.get('end_time', 0.0),
                'score': cs['score'],
                'pinyin': cs.get('pinyin', ''),
                'tone': cs.get('tone', 0),
                'matched': cs.get('matched', False),
            })

        return {
            'overall_score': overall_score,
            'word_scores': word_scores,
            'transcript': recognized_text,
            'target_text': target_text,
            'language': 'zh',
        }

    def decode_and_score(self, audio_path: str) -> dict:
        """
        Free Decoding mode: Transcribe Chinese speech without reference text.
        Returns recognized text and fluency estimation.
        """
        if not self.model_loaded:
            return {"error": f"Chinese ASR model not loaded: {self._init_error}"}

        if not os.path.exists(audio_path):
            return {"error": f"Audio file not found: {audio_path}"}

        start_time = time.time()

        try:
            results = self.model.generate(
                input=audio_path,
                batch_size_s=300,
            )
        except Exception as e:
            logger.error(f"❌ FunASR generate failed: {e}")
            return {"error": f"ASR transcription failed: {str(e)}"}

        elapsed = time.time() - start_time
        logger.info(f"⏱️ Free decoding completed in {elapsed:.2f}s")

        if not results or not results[0].get("text"):
            return {
                "recognized_text": "未检测到语音 (No speech detected)",
                "fluency_score": self.floor_score,
                "language": "zh",
            }

        recognized_text = results[0]["text"]
        timestamp_data = results[0].get("timestamp", [])

        logger.info(f"🔤 Free decode: {recognized_text}")

        # Estimate fluency from speech rate
        char_count = len(recognized_text.replace(' ', '').replace('，', '').replace('。', ''))

        # Calculate duration from timestamps or audio length
        if timestamp_data:
            # timestamps are in milliseconds: [[start_ms, end_ms], ...]
            if isinstance(timestamp_data[0], list):
                duration_ms = timestamp_data[-1][1] - timestamp_data[0][0]
            else:
                duration_ms = 5000  # fallback 5s
            duration = duration_ms / 1000.0
        else:
            # Estimate from audio file
            try:
                import librosa
                y, sr = librosa.load(audio_path, sr=16000)
                duration = len(y) / sr
            except Exception:
                duration = 5.0

        chars_per_second = char_count / max(duration, 0.1)

        # Chinese speech typically 3-5 characters per second
        if 2.5 <= chars_per_second <= 6.0:
            fluency_score = 75.0 + min(25.0, (chars_per_second - 2.5) * 7.0)
        elif chars_per_second > 6.0:
            fluency_score = max(50.0, 100.0 - (chars_per_second - 6.0) * 10.0)
        else:
            fluency_score = max(self.floor_score, chars_per_second / 2.5 * 50.0)

        fluency_score = max(self.floor_score, min(100.0, round(fluency_score, 2)))

        return {
            "recognized_text": recognized_text,
            "fluency_score": fluency_score,
            "language": "zh",
        }

    def _calculate_character_scores(self, recognized_text, target_text, timestamp_data):
        """
        Compare recognized text with target text character by character.
        Uses timestamps from FunASR when available.
        """
        from text_normalizer import normalize_chinese_text

        recognized_chars = list(normalize_chinese_text(recognized_text).replace(' ', ''))
        target_chars = list(normalize_chinese_text(target_text).replace(' ', ''))

        if not target_chars:
            return [], 0.0

        # Parse timestamps (FunASR format: list of [start_ms, end_ms])
        char_timestamps = []
        if timestamp_data:
            for i, ts in enumerate(timestamp_data):
                if isinstance(ts, list) and len(ts) >= 2:
                    char_timestamps.append({
                        'start': ts[0] / 1000.0,
                        'end': ts[1] / 1000.0,
                    })

        # Align recognized chars against target chars
        char_scores = []
        r_idx = 0

        for t_idx, target_char in enumerate(target_chars):
            if r_idx < len(recognized_chars) and recognized_chars[r_idx] == target_char:
                # Direct match — high score
                ts = char_timestamps[r_idx] if r_idx < len(char_timestamps) else {}
                char_scores.append({
                    'character': target_char,
                    'score': 95.0,
                    'matched': True,
                    'start_time': round(ts.get('start', t_idx * 0.3), 3),
                    'end_time': round(ts.get('end', (t_idx + 1) * 0.3), 3),
                })
                r_idx += 1
            else:
                # Look-ahead for nearby match
                found = False
                for look_ahead in range(1, min(3, len(recognized_chars) - r_idx)):
                    if r_idx + look_ahead < len(recognized_chars) and \
                       recognized_chars[r_idx + look_ahead] == target_char:
                        ts_idx = r_idx + look_ahead
                        ts = char_timestamps[ts_idx] if ts_idx < len(char_timestamps) else {}
                        char_scores.append({
                            'character': target_char,
                            'score': 60.0,
                            'matched': True,
                            'start_time': round(ts.get('start', t_idx * 0.3), 3),
                            'end_time': round(ts.get('end', (t_idx + 1) * 0.3), 3),
                        })
                        r_idx = r_idx + look_ahead + 1
                        found = True
                        break

                if not found:
                    char_scores.append({
                        'character': target_char,
                        'score': self.floor_score,
                        'matched': False,
                        'start_time': round(t_idx * 0.3, 3),
                        'end_time': round((t_idx + 1) * 0.3, 3),
                    })

        # Overall score using Harmonic Mean
        if char_scores:
            scores = [cs['score'] for cs in char_scores]
            harmonic_sum = sum(1.0 / max(s, 1.0) for s in scores)
            overall = len(scores) / harmonic_sum
            overall = max(self.floor_score, min(100.0, round(overall, 2)))
        else:
            overall = self.floor_score

        return char_scores, overall

    def _add_pinyin_to_scores(self, char_scores):
        """Augment character scores with pinyin and tone information."""
        try:
            from pypinyin import pinyin, Style
            chars = ''.join(cs['character'] for cs in char_scores)
            py_list = pinyin(chars, style=Style.TONE3, errors='ignore')

            for cs, py in zip(char_scores, py_list):
                cs['pinyin'] = py[0] if py else ''
                if py and py[0]:
                    tone = ''.join(c for c in py[0] if c.isdigit())
                    cs['tone'] = int(tone) if tone else 0
                else:
                    cs['tone'] = 0
        except ImportError:
            for cs in char_scores:
                cs['pinyin'] = ''
                cs['tone'] = 0

        return char_scores


if __name__ == "__main__":
    logger.info("=== Chinese Pronunciation Scoring Pipeline (FunASR) ===")

    try:
        scorer = ChinesePronunciationScorer()
    except Exception as e:
        logger.error(f"Failed to initialize pipeline: {e}")
        sys.exit(1)

    if len(sys.argv) > 2:
        audio_file = sys.argv[1]
        transcript_text = sys.argv[2]
        if os.path.exists(audio_file):
            result = scorer.score_audio(audio_file, transcript_text)
            print("\n--- Read-Aloud Score ---")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Error: Audio file {audio_file} does not exist.")
    elif len(sys.argv) > 1:
        audio_file = sys.argv[1]
        if os.path.exists(audio_file):
            result = scorer.decode_and_score(audio_file)
            print("\n--- Free Decoding Result ---")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Error: Audio file {audio_file} does not exist.")
    else:
        print("\nUsage:")
        print('  Read-Aloud:   python inference_pipeline.py <audio.wav> "目标文本"')
        print("  Free Decode:  python inference_pipeline.py <audio.wav>")
