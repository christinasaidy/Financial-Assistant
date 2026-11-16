#!/usr/bin/env bash
# Fine-tune the small model with LoRA on a RunPod "PyTorch" pod, from the uploaded bundle (decided 2026-11-08).
#
#   cd /workspace/bundle
#   bash finetune.sh check     # 5 steps and a merge, to see it all works (a few minutes)
#   setsid nohup bash finetune.sh > /root/run.out 2>&1 &    # the real run, detached from the browser terminal
#   tail -c 400 /root/train.log
#
# The real run saves a checkpoint every 100 steps; if it stops part way, the same command carries on from the last
# one (2026-11-15: a dropped browser terminal once killed a run that saved nothing, at step 405).
#
# On a big card (80 GB, e.g. an H100) use more examples at a time and fewer steps per update, the same 16 per update:
#   BATCH=8 ACCUMULATE=2 bash finetune.sh check      (then the real run with the same two values)
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
# Qwen3.5's fast linear-attention kernels: 33 s per step without them, 16 s with (measured 2026-11-09).
# --no-deps so they cannot change the torch or transformers that vLLM pinned.
/root/venv/bin/pip install -q --no-deps fla-core==0.6.0 flash-linear-attention==0.6.0
export PATH="/root/venv/bin:${PATH}"
unset HF_HOME  # the pod's own disk, as in serve.sh
pkill -f "vllm serve" || true  # the GPU is needed for training

SIZE=(--batch "${BATCH:-2}" --accumulate "${ACCUMULATE:-8}")  # 2 x 8 = 16 examples per update by default
if [ "${1:-}" = "check" ]; then
  python train.py --data data --out /root/ft-check --max-steps 5 "${SIZE[@]}" 2>&1 | tee /root/train.log
else
  python train.py --data data --out /root/ft-4b "${SIZE[@]}" 2>&1 | tee /root/train.log
fi
