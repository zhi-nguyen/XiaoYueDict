import os
import torch
import torch.nn as nn
import librosa
import asyncio
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from transformers import Wav2Vec2Model, Wav2Vec2Processor

app = FastAPI(title="English Pronunciation Scoring Service")

# 1. Khai báo lại chính xác Class đã dùng để train
class PronunciationScorer(nn.Module):
    def __init__(self):
        super().__init__()
        self.wav2vec2 = Wav2Vec2Model.from_pretrained("facebook/wav2vec2-base", use_safetensors=True)
        self.scoring_head = nn.Sequential(
            nn.Linear(768, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 1),
            nn.Sigmoid()
        )

    def forward(self, input_values):
        outputs = self.wav2vec2(input_values)
        hidden_states = outputs.last_hidden_state.mean(dim=1) 
        score = self.scoring_head(hidden_states)
        return score

# 2. Khởi tạo toàn cục (Global Initialization)
# Load processor từ Hugging Face
processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base")

# Load model weights khi FastAPI khởi động
model = PronunciationScorer()
MODEL_PATH = "models_weights/pytorch_model.bin"

# Lưu ý: Load lên CPU để tiết kiệm tài nguyên cho web server, 
# trừ khi server của muội có GPU chuyên dụng cho inference.
if os.path.exists(MODEL_PATH):
    model.load_state_dict(torch.load(MODEL_PATH, map_location=torch.device('cpu')))
    model.eval() # Chuyển sang chế độ suy luận (tắt Dropout)
    print("✅ Model weights loaded successfully!")
else:
    print(f"⚠️ Warning: Model weights not found at {MODEL_PATH}")

# 3. Hàm xử lý logic lõi (chạy đồng bộ, sẽ được ném vào thread riêng)
def process_and_score(audio_bytes: bytes) -> float:
    try:
        # Load audio từ bytes trực tiếp trên RAM, chuyển về 16kHz
        speech, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
        
        # Tránh lỗi CNN của Wav2Vec2 khi audio quá ngắn (ví dụ: bấm record và stop liên tục)
        import numpy as np
        if len(speech) < 16000:
            speech = np.pad(speech, (0, 16000 - len(speech)), mode='constant')

        # Chạy qua processor
        inputs = processor(speech, sampling_rate=16000, return_tensors="pt", padding=True)
        
        # Đưa vào model lấy điểm
        with torch.no_grad(): # Tắt tính toán gradient để tối ưu tốc độ và RAM
            logits = model(inputs.input_values)
            
        # Điểm trả về đang ở dạng 0.0 - 1.0, nhân 10 để đưa về thang 10 gốc
        final_score = logits.item() * 10.0
        return round(final_score, 2)
    except Exception as e:
        raise Exception(f"Audio processing error: {str(e)}")

# 4. API Endpoint
@app.post("/api/score/english")
async def score_english_audio(audio_file: UploadFile = File(...)):
    if not audio_file.filename.endswith(('.wav', '.webm', '.mp3')):
        raise HTTPException(status_code=400, detail="Invalid file format. Only wav, webm, mp3 are supported.")
    
    # Đọc file audio thành dạng bytes
    audio_bytes = await audio_file.read()
    
    try:
        # Đưa tác vụ nặng vào ThreadPool để không block event loop của FastAPI
        score = await asyncio.to_thread(process_and_score, audio_bytes)
        
        return {
            "status": "success",
            "filename": audio_file.filename,
            "score": score
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))