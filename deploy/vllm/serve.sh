#!/usr/bin/env bash
# Start the model server on a fresh RunPod "PyTorch" pod, for the assistant's evaluation.
#
#   export VLLM_KEY='your-key'          # made up on your laptop; never written into this file
#   bash serve.sh                       # Qwen/Qwen3.8-27B by default, or: bash serve.sh <model name> [vllm flags]
#   bash serve.sh Qwen/Qwen3.5-9B --language-model-only   # extra flags go to `vllm serve` as they are
#   tail -f /root/vllm.log              # ready at "Application startup complete"
#
# Every choice below comes from the two pilot sessions of 2026-11-05:
# - vLLM in its own environment (/root/venv): installing it over the pod's own PyTorch mixed two versions and crashed;
# - that environment first on PATH: vLLM builds a small kernel with `ninja`, which is installed there and was not
#   found otherwise;
# - one fixed vLLM version, the one both sessions ran (0.33.0), so every session runs the same server;
# - the model on the pod's own disk: loading it from the RunPod global volume was very slow and once stalled, while a
#   fresh download took about 3.5 minutes (give the pod a container disk of at least 100 GB);
# - --max-num-seqs 32: the evaluation asks one question at a time, and vLLM's default (1024 at once) does not fit
#   this model's cache;
# - --reasoning-parser qwen3: with thinking on, the model's reasoning is kept out of its reply;
# - --api-key: RunPod gives the server a public address, so every request must carry the key.
set -euo pipefail

MODEL="${1:-Qwen/Qwen3.8-27B}"
shift $(( $# > 0 ? 1 : 0 ))  # whatever follows the model name is passed to vllm serve
VLLM_VERSION="0.33.0"
: "${VLLM_KEY:?Set your key first: export VLLM_KEY='...'   (no spaces around =)}"

if [ ! -x /root/venv/bin/vllm ]; then
  python3 -m venv /root/venv || { apt-get update && apt-get install -y python3.12-venv && python3 -m venv /root/venv; }
  /root/venv/bin/pip install "vllm==${VLLM_VERSION}"
fi
export PATH="/root/venv/bin:${PATH}"
unset HF_HOME  # the pod's own disk, see above

pkill -f "vllm serve" || true  # never two servers at once
nohup vllm serve "$MODEL" \
  --max-model-len 16384 --max-num-seqs 32 --reasoning-parser qwen3 \
  --api-key "$VLLM_KEY" --host 0.0.0.0 --port 8000 "$@" \
  > /root/vllm.log 2>&1 &

echo "vLLM $(pip show vllm | awk '/^Version/ {print $2}') is starting $MODEL."
echo "Follow it with: tail -f /root/vllm.log   (ready at 'Application startup complete')"
