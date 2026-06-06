#!/usr/bin/env python3
"""Merge a PEFT LoRA adapter into its base model and save full safetensors.

The merged checkpoint is what we feed to convert_hf_to_gguf.py. We load the
base in fp16 (not 4-bit) so the merge is faithful; QLoRA's 4-bit base is only
used during training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base model id or path (e.g. Qwen/Qwen3.5-9B)")
    parser.add_argument("--adapter", required=True, help="Trained adapter directory")
    parser.add_argument("--output", required=True, help="Destination directory for merged model")
    parser.add_argument("--dtype", default="float16", choices=["float16", "bfloat16"],
                        help="Compute dtype for the merge")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}[args.dtype]

    print(f"loading base {args.base} as {args.dtype}")
    base = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )

    print(f"attaching adapter {args.adapter}")
    model = PeftModel.from_pretrained(base, args.adapter)

    print("merge_and_unload")
    model = model.merge_and_unload()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    print(f"saving merged model to {out}")
    model.save_pretrained(out, safe_serialization=True)

    print("saving tokenizer")
    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    tokenizer.save_pretrained(out)

    summary = {
        "base": args.base,
        "adapter": args.adapter,
        "output": str(out),
        "dtype": args.dtype,
    }
    (out / "merge_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
