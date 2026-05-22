#!/bin/bash
set -e

MODEL_DIR="/app/model"
SAFETENSORS="${MODEL_DIR}/model.safetensors"
FP16_ONNX="${MODEL_DIR}/pronunciation_scorer_fp16.onnx"

# ── Export ONNX models if FP16 doesn't exist yet ──────────────
if [ ! -f "$FP16_ONNX" ]; then
    echo "🔧 FP16 ONNX model not found — running export..."
    echo "   Source : $SAFETENSORS"
    echo "   Target : $FP16_ONNX"

    if [ ! -f "$SAFETENSORS" ]; then
        echo "❌ model.safetensors not found at $SAFETENSORS"
        exit 1
    fi

    python export_onnx.py \
        --weights "$SAFETENSORS" \
        --output-dir "$MODEL_DIR"

    echo "✅ ONNX models export complete."
else
    echo "✅ FP16 ONNX model already exists — skipping export."
    ls -lh "$FP16_ONNX"
fi

# ── Start the FastAPI server ──────────────────────────────────
exec uvicorn main:app --host 0.0.0.0 --port 8000
