#!/usr/bin/env bash
# Fine-tune the small model with LoRA on a RunPod "PyTorch" pod, from the uploaded bundle (decided 2026-11-08).
#
#   cd /workspace/bundle
#   bash finetune.sh check     # 5 steps and a merge, to see it all works (a few minutes)
#   bash finetune.sh           # the real run: 2 epochs, then the merged model in /root/ft-4b
#   tail -f /root/train.log
#
# It uses the same environment as serve.sh (/root/venv with vLLM 0.33.0, whose transformers already knows Qwen3.5),
# plus peft and accelerate, so the model is trained and served by the same library versions.
set -euo pipefail
cd "$(dirname "$0")"
VLLM_VERSION="0.33.0"

if [ ! -x /root/venv/bin/vllm ]; then
  python3 -m venv /root/venv || { apt-get update && apt-get install -y python3.12-venv && python3 -m venv /root/venv; }
  /root/venv/bin/pip install "vllm==${VLLM_VERSION}"
fi
/root/venv/bin/pip install -q peft accelerate
export PATH="/root/venv/bin:${PATH}"
unset HF_HOME  # the pod's own disk, as in serve.sh
pkill -f "vllm serve" || true  # the GPU is needed for training

if [ "${1:-}" = "check" ]; then
  python train.py --data data --out /root/ft-check --max-steps 5 2>&1 | tee /root/train.log
else
  python train.py --data data --out /root/ft-4b 2>&1 | tee /root/train.log
fi
