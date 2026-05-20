FROM python:3.10-slim

WORKDIR /app

# System dependencies for audio processing
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only first (saves ~1GB vs full CUDA build)
RUN pip install --no-cache-dir \
    torch==2.6.0+cpu \
    torchaudio==2.6.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code + entrypoint
COPY *.py ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# NOTE: model/ is NOT copied into the image.
# It is volume-mounted at runtime via docker-compose so the
# exported INT8 ONNX persists on the host filesystem.

EXPOSE 8000

# Entrypoint handles INT8 export (if needed) then starts uvicorn
ENTRYPOINT ["./entrypoint.sh"]
