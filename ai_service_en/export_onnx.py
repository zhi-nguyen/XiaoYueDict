"""
Export PronunciationScorer (Wav2Vec2 + Regression Head) to ONNX INT8.

This script:
  1. Rebuilds the exact PronunciationScorer architecture from the training notebook
  2. Loads the trained weights (model.safetensors)
  3. Exports to standard ONNX (FP32)
  4. Quantizes the ONNX model to INT8 (Dynamic Quantization)

The resulting pronunciation_scorer_int8.onnx file can be used with ONNX Runtime
for ~4x smaller model size and ~2-3x faster CPU inference.

Usage:
    python export_onnx.py --weights ./models_weights/model.safetensors
"""

import os
import sys
import argparse
import torch
import torch.nn as nn
from typing import Optional
from dataclasses import dataclass
from transformers import Wav2Vec2Model
from safetensors.torch import load_file as load_safetensors


# =============================================================================
# Model Architecture (exact copy from training notebook)
# =============================================================================

@dataclass
class ScorerOutput:
    """Custom output class for PronunciationScorer."""
    loss: Optional[torch.Tensor] = None
    logits: Optional[torch.Tensor] = None


class PronunciationScorer(nn.Module):
    """Wav2Vec2-based pronunciation quality scorer.

    Architecture:
        Raw Audio (16kHz) -> Wav2Vec2Model -> Mean Pool ->
        Linear(768->256) -> ReLU -> Dropout(0.1) -> Linear(256->1) -> Sigmoid
    """

    def __init__(self, model_name: str = "facebook/wav2vec2-base"):
        super().__init__()
        # IMPORTANT: attn_implementation="eager" is required for ONNX export.
        # Transformers 5.8+ defaults to SDPA attention, which uses dynamic mask
        # creation (create_bidirectional_mask) that is incompatible with torch.jit.trace.
        self.wav2vec2 = Wav2Vec2Model.from_pretrained(
            model_name, use_safetensors=True, attn_implementation="eager"
        )
        self.wav2vec2.feature_extractor._freeze_parameters()

        self.scoring_head = nn.Sequential(
            nn.Linear(768, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 1),
            nn.Sigmoid(),
        )
        self.loss_fn = nn.MSELoss()

    def forward(
        self,
        input_values: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
    ) -> ScorerOutput:
        outputs = self.wav2vec2(input_values)
        hidden_states = outputs.last_hidden_state  # (B, T, 768)
        pooled = hidden_states.mean(dim=1)          # (B, 768)
        logits = self.scoring_head(pooled)           # (B, 1)

        loss = None
        if labels is not None:
            if labels.dim() == 1:
                labels = labels.unsqueeze(1)
            loss = self.loss_fn(logits, labels)

        return ScorerOutput(loss=loss, logits=logits)


# =============================================================================
# ONNX-compatible forward wrapper
# =============================================================================

class PronunciationScorerONNX(nn.Module):
    """Wrapper that returns only the logits tensor for clean ONNX export."""

    def __init__(self, scorer: PronunciationScorer):
        super().__init__()
        self.scorer = scorer

    def forward(self, input_values: torch.Tensor) -> torch.Tensor:
        outputs = self.scorer.wav2vec2(input_values)
        hidden_states = outputs.last_hidden_state
        pooled = hidden_states.mean(dim=1)
        logits = self.scorer.scoring_head(pooled)
        return logits


def main():
    parser = argparse.ArgumentParser(description="Export PronunciationScorer to ONNX INT8")
    parser.add_argument(
        "--weights",
        type=str,
        default="./models_weights/model.safetensors",
        help="Path to trained model.safetensors weights file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./models_weights",
        help="Directory to save ONNX model files",
    )
    args = parser.parse_args()

    # Validate weights path
    if not os.path.exists(args.weights):
        print(f"❌ Weights file not found: {args.weights}")
        print("   Please ensure training is complete and the file exists.")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    onnx_path = os.path.join(args.output_dir, "pronunciation_scorer.onnx")
    quantized_onnx_path = os.path.join(args.output_dir, "pronunciation_scorer_int8.onnx")

    # =========================================================================
    # Step 1: Load PyTorch model with trained weights (safetensors format)
    # =========================================================================
    print("1. Loading PyTorch PronunciationScorer model...")
    model = PronunciationScorer()

    # Load safetensors weights
    state_dict = load_safetensors(args.weights)
    model.load_state_dict(state_dict)
    model.eval()
    print(f"   ✅ Loaded weights from: {args.weights}")
    print(f"   📦 Weights size: {os.path.getsize(args.weights) / (1024**2):.1f} MB")

    # Wrap for clean ONNX export (single tensor output)
    onnx_model = PronunciationScorerONNX(model)
    onnx_model.eval()

    # =========================================================================
    # Step 2: Export to ONNX format
    # =========================================================================
    print("2. Exporting to ONNX format...")

    # Monkey-patch: transformers 5.8+ create_bidirectional_mask → sdpa_mask
    # crashes during torch.jit.trace. We must patch the reference in the module
    # where it's actually CALLED (modeling_wav2vec2), not just masking_utils.
    import transformers.models.wav2vec2.modeling_wav2vec2 as _wav2vec2_mod
    _original_mask_fn = _wav2vec2_mod.create_bidirectional_mask
    _wav2vec2_mod.create_bidirectional_mask = lambda *a, **kw: None
    print("   ⚡ Patched transformers masking for JIT-trace compatibility")

    # Dummy input: 1 batch, 1 second of audio at 16kHz
    dummy_input = torch.randn(1, 16000)

    torch.onnx.export(
        onnx_model,
        (dummy_input,),
        onnx_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["input_values"],
        output_names=["logits"],
        dynamic_axes={
            "input_values": {0: "batch_size", 1: "sequence_length"},
            "logits": {0: "batch_size"},
        },
    )

    # Restore original
    _wav2vec2_mod.create_bidirectional_mask = _original_mask_fn

    onnx_size_mb = os.path.getsize(onnx_path) / (1024 ** 2)
    print(f"   ✅ Saved ONNX model: {onnx_path} ({onnx_size_mb:.1f} MB)")

    # =========================================================================
    # Step 3: Validate ONNX model
    # =========================================================================
    print("3. Validating ONNX model structure...")
    import onnx
    onnx_model_check = onnx.load(onnx_path)
    onnx.checker.check_model(onnx_model_check)
    print("   ✅ ONNX model validation passed")

    # =========================================================================
    # Step 4: Quantize to INT8
    # =========================================================================
    print("4. Quantizing ONNX model to INT8...")
    from onnxruntime.quantization import quantize_dynamic, QuantType

    quantize_dynamic(
        model_input=onnx_path,
        model_output=quantized_onnx_path,
        weight_type=QuantType.QUInt8,    # QUInt8 for CPU optimization
    )

    quantized_size_mb = os.path.getsize(quantized_onnx_path) / (1024 ** 2)
    reduction = (1 - quantized_size_mb / onnx_size_mb) * 100
    print(f"   ✅ Saved quantized model: {quantized_onnx_path} ({quantized_size_mb:.1f} MB)")
    print(f"   📉 Size reduction: {reduction:.1f}%")

    # =========================================================================
    # Step 5: Verify ONNX Runtime inference
    # =========================================================================
    print("5. Verifying ONNX Runtime inference...")
    import onnxruntime as ort
    import numpy as np

    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = 2

    session = ort.InferenceSession(
        quantized_onnx_path,
        sess_options=sess_options,
        providers=["CPUExecutionProvider"],
    )

    # Test with dummy audio
    test_input = np.random.randn(1, 16000).astype(np.float32)
    inputs = {session.get_inputs()[0].name: test_input}
    result = session.run(None, inputs)

    predicted_score = float(result[0][0][0])
    print(f"   ✅ ONNX Runtime inference OK. Dummy prediction: {predicted_score:.4f}")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("  EXPORT COMPLETE")
    print("=" * 60)
    print(f"  Original   : {args.weights} ({os.path.getsize(args.weights) / (1024**2):.1f} MB)")
    print(f"  FP32 ONNX  : {onnx_path} ({onnx_size_mb:.1f} MB)")
    print(f"  INT8 ONNX  : {quantized_onnx_path} ({quantized_size_mb:.1f} MB)")
    print(f"  Compression: {reduction:.1f}% smaller than FP32 ONNX")
    print("=" * 60)
    print("\nTo use in production:")
    print("  import onnxruntime as ort")
    print(f'  session = ort.InferenceSession("{quantized_onnx_path}")')
    print('  result = session.run(None, {"input_values": audio_array})')


if __name__ == "__main__":
    main()
