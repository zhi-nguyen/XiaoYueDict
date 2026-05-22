FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

# System dependencies for audio processing
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install remaining dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip uninstall -y onnxruntime onnxruntime-gpu && \
    pip install --no-cache-dir onnxruntime-gpu

# Configure runtime library path to find bundled CUDA and cuDNN libraries
ENV LD_LIBRARY_PATH=/opt/conda/lib/python3.11/site-packages/nvidia/cusparse/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cudnn/lib:/opt/conda/lib/python3.11/site-packages/nvidia/nccl/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cusolver/lib:/opt/conda/lib/python3.11/site-packages/nvidia/curand/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cufft/lib:/opt/conda/lib/python3.11/site-packages/nvidia/nvtx/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cuda_nvrtc/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:/opt/conda/lib/python3.11/site-packages/nvidia/nvjitlink/lib:/opt/conda/lib/python3.11/site-packages/nvidia/cuda_cupti/lib

# Copy application code + entrypoint
COPY *.py ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# NOTE: model/ is NOT copied into the image.
# It is volume-mounted at runtime via docker-compose so the
# exported FP16 ONNX persists on the host filesystem.

EXPOSE 8000

# Entrypoint handles FP16 export (if needed) then starts uvicorn
ENTRYPOINT ["./entrypoint.sh"]
