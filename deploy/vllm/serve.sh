#!/usr/bin/env bash
# Start the model server on a fresh RunPod "PyTorch" pod, for the assistant's evaluation.
#
#   export VLLM_KEY='your-key'          # made up on your laptop; never written into this file
#   bash serve.sh                       # Qwen/Qwen3.8-27B by default, or: bash serve.sh <model name>
#   tail -f /root/vllm.log              # ready at "Application startup complete"
#
# What it does, and why (learned on the first pilot run, 2026-11-05):
# - installs vLLM in its own environment (/root/venv): installing it over the pod's own PyTorch left two versions
#   mixed and vLLM crashed;
# - keeps the model on the global volume when one is mounted at /workspace-global, so it is downloaded only once;
# - --max-num-seqs 32: the evaluation asks one question at a time, and vLLM's default (1024 at once) does not fit
#   this model's cache;
# - --api-key: RunPod gives the server a public address, so every request must carry the key.
set -euo pipefail

MODEL="${1:-Qwen/Qwen3.8-27B}"
: "${VLLM_KEY:?Set your key first: export VLLM_KEY='...'   (no spaces around =)}"

if [ -d /workspace-global ]; then
  export HF_HOME=/workspace-global/hf
fi

if [ ! -x /root/venv/bin/vllm ]; then
  python3 -m venv /root/venv || { apt-get update && apt-get install -y python3.12-venv && python3 -m venv /root/venv; }
  /root/venv/bin/pip install -U vllm
fi

pkill -f "vllm serve" || true  # never two servers at once
nohup /root/venv/bin/vllm serve "$MODEL" \
  --max-model-len 16384 --max-num-seqs 32 \
  --api-key "$VLLM_KEY" --host 0.0.0.0 --port 8000 \
  > /root/vllm.log 2>&1 &

echo "vLLM $(/root/venv/bin/pip show vllm | awk '/^Version/ {print $2}') is starting $MODEL."
echo "Follow it with: tail -f /root/vllm.log   (ready at 'Application startup complete')"
