FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libsndfile1 && rm -rf /var/lib/apt/lists/*

# Step 1: Install torch + torchaudio from PyTorch CPU index
# Using --extra-index-url so transitive deps (typing-extensions, etc.) resolve from PyPI
RUN pip install --no-cache-dir \
    torch==2.6.0+cpu \
    torchaudio==2.6.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Step 2: Install remaining dependencies (torch is NOT in requirements.txt to avoid overwrite)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
