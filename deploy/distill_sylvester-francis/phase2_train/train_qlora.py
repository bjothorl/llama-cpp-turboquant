#!/usr/bin/env python3
"""QLoRA SFT on Qwen/Qwen3.5-9B with Sylvester-style {"text": ...} JSONL.

Defaults from phase2_train/train.env. CLI args override.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path


DEFAULT_ENV_FILE = Path(__file__).resolve().parent / "train.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--base-model", default=None)
    parser.add_argument("--data", dest="data_path", default=None)
    parser.add_argument("--output", dest="output_dir", default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--grad-accum", type=int, default=None)
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--max-seq-length", type=int, default=None)
    parser.add_argument("--lora-r", type=int, default=None)
    parser.add_argument("--lora-alpha", type=int, default=None)
    parser.add_argument("--lora-dropout", type=float, default=None)
    parser.add_argument("--lora-targets", default=None,
                        help="Comma-separated module names, or 'all-linear'")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print resolved config and exit without loading the model")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise SystemExit(f"{path}:{line_no}: expected KEY=VALUE")
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value is not None else default


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value is not None else default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value is not None else default


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve(args: argparse.Namespace) -> dict:
    load_env_file(Path(args.env_file))
    return {
        "base_model": args.base_model or env_str("BASE_MODEL", "Qwen/Qwen3.5-9B"),
        "data_path": args.data_path or env_str("DATA_PATH", ""),
        "output_dir": args.output_dir or env_str("OUTPUT_DIR", "adapters/qwen35-9b-ts-smoke"),
        "max_samples": args.max_samples if args.max_samples is not None else env_int("MAX_SAMPLES", 100),
        "epochs": args.epochs if args.epochs is not None else env_int("EPOCHS", 1),
        "batch_size": args.batch_size if args.batch_size is not None else env_int("BATCH_SIZE", 1),
        "grad_accum": args.grad_accum if args.grad_accum is not None else env_int("GRAD_ACCUM", 16),
        "learning_rate": args.lr if args.lr is not None else env_float("LEARNING_RATE", 1e-4),
        "warmup_ratio": env_float("WARMUP_RATIO", 0.03),
        "weight_decay": env_float("WEIGHT_DECAY", 0.0),
        "max_seq_length": args.max_seq_length if args.max_seq_length is not None else env_int("MAX_SEQ_LENGTH", 1024),
        "logging_steps": env_int("LOGGING_STEPS", 5),
        "save_steps": env_int("SAVE_STEPS", 100),
        "seed": args.seed if args.seed is not None else env_int("SEED", 42),
        "lora_r": args.lora_r if args.lora_r is not None else env_int("LORA_R", 16),
        "lora_alpha": args.lora_alpha if args.lora_alpha is not None else env_int("LORA_ALPHA", 32),
        "lora_dropout": args.lora_dropout if args.lora_dropout is not None else env_float("LORA_DROPOUT", 0.05),
        "lora_targets": args.lora_targets or env_str("LORA_TARGETS", "all-linear"),
        "use_4bit": env_bool("USE_4BIT", True),
        "bnb_quant_type": env_str("BNB_4BIT_QUANT_TYPE", "nf4"),
        "bnb_double_quant": env_bool("BNB_4BIT_USE_DOUBLE_QUANT", True),
        "bnb_compute_dtype": env_str("BNB_4BIT_COMPUTE_DTYPE", "bfloat16"),
    }


def count_jsonl_rows(path: Path) -> int:
    total = 0
    for line in path.read_text().splitlines():
        if line.strip():
            total += 1
    return total


def main() -> None:
    args = parse_args()
    cfg = resolve(args)

    if not cfg["data_path"]:
        raise SystemExit("--data (or DATA_PATH in train.env) is required")

    data_path = Path(cfg["data_path"])
    if not data_path.is_file():
        raise SystemExit(f"data file not found: {data_path}")

    total_rows = count_jsonl_rows(data_path)
    effective_rows = min(total_rows, cfg["max_samples"]) if cfg["max_samples"] else total_rows

    print(json.dumps({"config": cfg, "data_rows_total": total_rows,
                      "data_rows_used": effective_rows}, indent=2))

    if args.dry_run:
        return

    # Heavy imports kept below the dry-run gate so --dry-run works without CUDA.
    import torch
    from datasets import load_dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for QLoRA training")

    random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])
    torch.cuda.manual_seed_all(cfg["seed"])

    compute_dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[cfg["bnb_compute_dtype"]]

    bnb_config = None
    if cfg["use_4bit"]:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=cfg["bnb_quant_type"],
            bnb_4bit_use_double_quant=cfg["bnb_double_quant"],
            bnb_4bit_compute_dtype=compute_dtype,
        )

    print(f"loading tokenizer: {cfg['base_model']}")
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"], trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    print(f"loading base model (4bit={cfg['use_4bit']}): {cfg['base_model']}")
    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"],
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )
    model.config.use_cache = False

    if cfg["use_4bit"]:
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=True,
        )

    targets_raw = cfg["lora_targets"].strip()
    if targets_raw.lower() == "all-linear":
        target_modules = "all-linear"
    else:
        target_modules = [m.strip() for m in targets_raw.split(",") if m.strip()]

    lora_config = LoraConfig(
        r=cfg["lora_r"],
        lora_alpha=cfg["lora_alpha"],
        lora_dropout=cfg["lora_dropout"],
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_modules,
    )

    print(f"loading dataset: {data_path}")
    dataset = load_dataset("json", data_files=str(data_path), split="train")
    if cfg["max_samples"] and cfg["max_samples"] < len(dataset):
        dataset = dataset.shuffle(seed=cfg["seed"]).select(range(cfg["max_samples"]))

    if "text" not in dataset.column_names:
        raise SystemExit(
            f"dataset {data_path} has no 'text' field "
            f"(columns: {dataset.column_names})"
        )

    output_dir = cfg["output_dir"]
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    sft_config = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=cfg["epochs"],
        per_device_train_batch_size=cfg["batch_size"],
        gradient_accumulation_steps=cfg["grad_accum"],
        learning_rate=cfg["learning_rate"],
        warmup_ratio=cfg["warmup_ratio"],
        weight_decay=cfg["weight_decay"],
        lr_scheduler_type="cosine",
        max_grad_norm=0.3,
        logging_steps=cfg["logging_steps"],
        save_steps=cfg["save_steps"],
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to="none",
        seed=cfg["seed"],
        max_length=cfg["max_seq_length"],
        dataset_text_field="text",
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        peft_config=lora_config,
        processing_class=tokenizer,
    )

    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in trainer.model.parameters())
    print(f"trainable params: {trainable:,} / {total:,} ({100 * trainable / total:.4f}%)")

    print("starting training")
    trainer.train()

    print(f"saving adapter to {output_dir}")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    summary = {
        "base_model": cfg["base_model"],
        "output_dir": output_dir,
        "rows_used": effective_rows,
        "epochs": cfg["epochs"],
        "effective_batch_size": cfg["batch_size"] * cfg["grad_accum"],
        "lora_r": cfg["lora_r"],
        "lora_alpha": cfg["lora_alpha"],
        "trainable_params": trainable,
        "total_params": total,
    }
    Path(output_dir, "train_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
