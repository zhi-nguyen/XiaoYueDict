import os
import sys
import json
import torch
import torchaudio
from text_normalizer import normalize_transcript

class PronunciationScorer:
    def __init__(self, model_dir=None):
        """
        Initializes the PronunciationScorer utilizing a CTC-Probability 
        based Goodness of Pronunciation (GOP) approach.
        """
        # Prioritize CUDA explicitly
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            print(f"✅ Running in GPU mode. Device assigned: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            print("✅ Running in CPU (FP32) mode. Docker/CPU-only environment detected.")
            
        # Load ASR Model for Forced Alignment and GOP probabilities
        print("Loading ASR model for forced alignment and GOP scoring...")
        self.bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
        self.alignment_model = self.bundle.get_model().to(self.device)
        self.alignment_model.eval()
        self.labels = self.bundle.get_labels()
        self.dictionary = {c: i for i, c in enumerate(self.labels)}
        
        # Pedagogical Scoring Parameters
        self.floor_score = 15.0
        self.critical_threshold = 0.5
        self.moderate_threshold = 0.75
        
        print("✅ Pipeline completely initialized.")

    def _calculate_pedagogical_score(self, word_probs):
        if not word_probs:
            return self.floor_score
            
        sorted_probs = sorted(word_probs)
        idx_25 = int(len(sorted_probs) * 0.25)
        p25_prob = sorted_probs[idx_25]
        mean_prob = sum(word_probs) / len(word_probs)
        
        # Calculate base probability (blending 25th percentile and mean)
        word_prob = (0.5 * p25_prob) + (0.5 * mean_prob)
        
        if word_prob >= self.moderate_threshold:
            # Tier 1 (Good): [moderate_threshold, 1.0] -> [80.0, 100.0]
            score = 80.0 + ((word_prob - self.moderate_threshold) / (1.0 - self.moderate_threshold)) * 20.0
        elif word_prob >= self.critical_threshold:
            # Tier 1 (Moderate): [critical_threshold, moderate_threshold] -> [50.0, 80.0]
            score = 50.0 + ((word_prob - self.critical_threshold) / (self.moderate_threshold - self.critical_threshold)) * 30.0
        else:
            # Tier 2 & 3 (Critical with Exponential Drop)
            score = self.floor_score + ((word_prob / self.critical_threshold) ** 2.0) * (50.0 - self.floor_score)
            
        return max(self.floor_score, min(100.0, score))

    def _compute_word_timestamps(self, alignment, probs, waveform_length, num_frames, sample_rate=16000):
        inv_dict = {v: k for k, v in self.dictionary.items()}
        samples_per_frame = waveform_length / num_frames
        
        words = []
        current_word = ""
        word_start_frame = None
        prev_token_id = 0
        current_word_probs = []
        
        for frame_idx, token_id in enumerate(alignment.tolist()):
            if token_id == 0:
                prev_token_id = 0
                continue
                
            char = inv_dict.get(token_id, "")
            
            # Handle word boundaries (the pipe character in Wav2Vec2)
            if char == '|':
                if current_word != "":
                    start_time = (word_start_frame * samples_per_frame) / sample_rate
                    end_time = (frame_idx * samples_per_frame) / sample_rate
                    
                    word_score = self._calculate_pedagogical_score(current_word_probs)
                    
                    words.append({
                        "word": current_word, 
                        "start": start_time, 
                        "end": end_time,
                        "score": round(word_score, 2)
                    })
                    current_word = ""
                    word_start_frame = None
                    current_word_probs = []
                prev_token_id = token_id
                continue
                
            # Handle character progression
            if token_id != prev_token_id:
                if current_word == "":
                    word_start_frame = frame_idx
                current_word += char
                prev_token_id = token_id
                
            # Accumulate the predicted probability for the target token at this frame
            if current_word != "":
                prob = probs[frame_idx, token_id].item()
                current_word_probs.append(prob)
                
        # Flush the final word if the audio ends without a trailing space
        if current_word != "":
            start_time = (word_start_frame * samples_per_frame) / sample_rate
            end_time = (num_frames * samples_per_frame) / sample_rate
            
            word_score = self._calculate_pedagogical_score(current_word_probs)
            
            words.append({
                "word": current_word, 
                "start": start_time, 
                "end": end_time,
                "score": round(word_score, 2)
            })
            
        return words

    def _align_audio_and_text(self, waveform, transcript):
        # Ensure waveform is strictly (1, time)
        if waveform.dim() == 1:
            waveform = waveform.unsqueeze(0)
        elif waveform.dim() == 2 and waveform.shape[0] > 1:
            waveform = waveform[0:1, :]  # Convert stereo to mono by taking first channel
            
        with torch.inference_mode():
            emissions, _ = self.alignment_model(waveform.to(self.device))
            emissions = torch.log_softmax(emissions, dim=-1)
            
        # Ensure emissions has batch dimension 1 -> shape: (1, time_steps, num_classes)
        if emissions.dim() == 2:
            emissions = emissions.unsqueeze(0)
            
        formatted_transcript = transcript.replace(" ", "|") + "|"
        
        # Strictly map only known characters and explicitly exclude the CTC blank token (0)
        tokens = []
        for char in formatted_transcript:
            if char in self.dictionary:
                token_id = self.dictionary[char]
                if token_id != 0:  # 0 is the CTC blank index
                    tokens.append(token_id)
                    
        targets = torch.tensor([tokens], dtype=torch.int32).to(self.device)
        
        # Ensure targets has batch dimension 1 -> shape: (1, num_targets)
        if targets.dim() == 1:
            targets = targets.unsqueeze(0)
            
        print(f"DEBUG - Emissions shape: {emissions.shape}")
        print(f"DEBUG - Targets shape: {targets.shape}")
        print(f"DEBUG - Cleaned target tensor for alignment: {targets}")
        
        alignments, _ = torchaudio.functional.forced_align(emissions, targets, blank=0)
        
        # Convert log_softmax emissions back to raw probabilities
        probs = torch.exp(emissions[0]) # shape: (time_steps, num_classes)
        
        num_frames = emissions.size(1)
        waveform_length = waveform.size(1)
        
        return self._compute_word_timestamps(
            alignments[0], 
            probs,
            waveform_length=waveform_length, 
            num_frames=num_frames
        )

    def score_audio(self, audio_path, transcript):
        """
        Main pipeline method to align audio and text, then score each word using GOP.
        Returns a dict suitable for JSON serialization in FastAPI.
        """
        try:
            waveform, sample_rate = torchaudio.load(audio_path)
            if sample_rate != 16000:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
        except Exception as e:
            return {"error": f"Failed to load audio: {str(e)}"}
            
        if not transcript.strip():
            return {"error": "Transcript cannot be empty."}
            
        transcript = normalize_transcript(transcript)
        print(f"DEBUG - Normalized text: {transcript}")
        
        # Get alignments and GOP scores
        try:
            timestamps = self._align_audio_and_text(waveform, transcript)
        except Exception as e:
            return {"error": f"Alignment failed: {str(e)}"}
            
        if not timestamps:
            return {"error": "No words aligned. Check audio and transcript."}
            
        word_scores = []
        total_score = 0.0
        valid_words = 0
        
        for word_data in timestamps:
            word_scores.append({
                "word": word_data['word'],
                "start_time": round(word_data['start'], 3),
                "end_time": round(word_data['end'], 3),
                "score": word_data['score']
            })
            
            total_score += word_data['score']
            valid_words += 1
                
        # Compute overall score using Harmonic Mean to heavily penalize poor words
        overall_score = 0.0
        if valid_words > 0:
            harmonic_sum = sum(1.0 / max(w['score'], 1.0) for w in word_scores)
            overall_score = round(valid_words / harmonic_sum, 2)
            overall_score = max(self.floor_score, min(100.0, overall_score))
            
        return {
            "overall_score": overall_score,
            "word_scores": word_scores,
            "transcript": transcript
        }

if __name__ == "__main__":
    print("=== Pronunciation Scoring Pipeline ===")
    
    try:
        scorer = PronunciationScorer()
    except Exception as e:
        print(f"\nFailed to initialize pipeline: {e}")
        sys.exit(1)
        
    if len(sys.argv) > 2:
        audio_file = sys.argv[1]
        transcript_text = sys.argv[2]
        
        if os.path.exists(audio_file):
            result = scorer.score_audio(audio_file, transcript_text)
            print("\n--- Final Score ---")
            print(json.dumps(result, indent=2))
        else:
            print(f"Error: Audio file {audio_file} does not exist.")
    else:
        print("\nUsage to test an audio file: python inference_pipeline.py <path_to_audio_file> \"TRANSCRIPT TEXT\"")
