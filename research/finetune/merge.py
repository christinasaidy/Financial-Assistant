"""Merge a saved LoRA adapter into the base model, so it can be served without training again (2026-11-14).

    python merge.py --adapter /root/adapter/adapter --out /root/ft-4b

train.py saves the adapter and a merged model; the merged model lives on the pod's own disk and is gone once the
pod stops, while the adapter (120 MB) is kept on the laptop. This rebuilds the same merged model from it, exactly as
train.py does at the end of a run, ready for serve.sh.
"""

import argparse
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor, AutoTokenizer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--adapter", type=Path, required=True, help="the folder with adapter_config.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16, device_map="cuda")
    merged = PeftModel.from_pretrained(model, str(args.adapter)).merge_and_unload()
    merged.config.use_cache = True
    args.out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.out, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base).save_pretrained(args.out)
    AutoProcessor.from_pretrained(args.base).save_pretrained(args.out)
    print(f"Merged model saved in {args.out}; serve it with: bash serve.sh {args.out} --language-model-only", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
