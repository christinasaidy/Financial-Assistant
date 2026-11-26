#!/usr/bin/env bash
# Serve the fine-tuned model on a fresh RunPod "PyTorch" pod from its saved adapter, for an evaluation (2026-11-14).
#
#   cd /workspace/bundle
#   setsid nohup bash merge_and_serve.sh > /root/serve.out 2>&1 &     # keeps going if the browser disconnects
#   tail -f /root/serve.out                                            # then: tail -f /root/vllm.log
#
# The bundle holds the adapter (ADAPTER, default ft-4b-batch4-adapter.tgz), merge.py, serve.sh and key.txt, the API key made on the
# laptop, so nothing has to be typed or pasted. The merged model is rebuilt only if /root/ft-4b is not there yet.
# Same environment as finetune.sh and serve.sh (/root/venv, vLLM 0.33.0), so the model is served as it was trained.
set -euo pipefail
cd "$(dirname "$0")"
VLLM_VERSION="0.33.0"
ADAPTER="${ADAPTER:-ft-4b-batch4-adapter.tgz}"

if [ ! -x /root/venv/bin/vllm ]; then
  python3 -m venv /root/venv || { apt-get update && apt-get install -y python3.12-venv && python3 -m venv /root/venv; }
  /root/venv/bin/pip install "vllm==${VLLM_VERSION}"
fi
/root/venv/bin/pip install -q peft accelerate
export PATH="/root/venv/bin:${PATH}"
unset HF_HOME  # the pod's own disk, as in serve.sh

if [ ! -f /root/ft-4b/config.json ]; then
  mkdir -p /root/adapter
  tar xzf "${ADAPTER}" -C /root/adapter
  python merge.py --adapter /root/adapter/adapter --out /root/ft-4b
fi

VLLM_KEY="$(tr -d '\r\n' < key.txt)"
export VLLM_KEY
bash serve.sh /root/ft-4b --language-model-only --served-model-name ft-4b
echo "Follow the server with: tail -f /root/vllm.log   (ready at 'Application startup complete')"
