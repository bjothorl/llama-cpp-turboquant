#!/usr/bin/env python3
"""Restore tensors that AutoModelForCausalLM dropped during PEFT merge.

Background: Qwen/Qwen3.5-9B is a multimodal checkpoint with three groups of
tensors: the text transformer, the vision tower (`model.visual.*`), and the
MTP draft head (`mtp.*`). The transformers `Qwen3_5ForCausalLM` class only
instantiates the text transformer, so PEFT merge_and_unload + save_pretrained
silently drops both vision and MTP weights. We want vision dropped (text-only
inference) but MTP kept (draft-mtp serving).

This script reads the merged dir, finds tensors present in the source HF cache
but missing from the merged dir, applies an include/exclude prefix filter, and
writes the kept tensors as an additional safetensors shard. It also rewrites
the file layout into a sharded form with `model.safetensors.index.json` so
downstream tools (e.g. convert_hf_to_gguf.py) discover all tensors.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", required=True, help="Merged HF model dir")
    parser.add_argument("--source", required=True,
                        help="HF repo id (uses ~/.cache/huggingface) or a local model dir")
    parser.add_argument("--include", default="mtp.",
                        help="Comma-separated tensor name prefixes to restore (default: mtp.)")
    parser.add_argument("--exclude", default="model.visual.",
                        help="Comma-separated prefixes to never restore")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def find_hf_cache_snapshot(repo_id: str) -> str | None:
    cache = Path(os.environ.get("HF_HOME") or
                 Path.home() / ".cache" / "huggingface").expanduser()
    cache = cache / "hub" if (cache / "hub").is_dir() else cache
    target = cache / ("models--" + repo_id.replace("/", "--")) / "snapshots"
    if not target.is_dir():
        return None
    snaps = sorted(target.iterdir())
    return str(snaps[-1]) if snaps else None


def collect_tensor_files(path: Path) -> dict[str, Path]:
    """Map tensor name -> safetensors file containing it."""
    from safetensors import safe_open

    out: dict[str, Path] = {}
    for f in sorted(path.iterdir()):
        if f.suffix != ".safetensors":
            continue
        real = Path(os.path.realpath(f))
        with safe_open(str(real), framework="pt") as st:
            for k in st.keys():
                out[k] = real
    return out


def main() -> None:
    args = parse_args()

    merged_dir = Path(args.merged).resolve()
    if not merged_dir.is_dir():
        raise SystemExit(f"merged dir not found: {merged_dir}")

    if Path(args.source).is_dir():
        source_dir = Path(args.source).resolve()
    else:
        snap = find_hf_cache_snapshot(args.source)
        if not snap:
            raise SystemExit(f"could not locate HF cache snapshot for {args.source}")
        source_dir = Path(snap)

    print(f"merged: {merged_dir}")
    print(f"source: {source_dir}")

    merged_files = collect_tensor_files(merged_dir)
    source_files = collect_tensor_files(source_dir)

    merged_keys = set(merged_files.keys())
    source_keys = set(source_files.keys())

    include = [p for p in (s.strip() for s in args.include.split(",")) if p]
    exclude = [p for p in (s.strip() for s in args.exclude.split(",")) if p]

    to_restore: list[str] = []
    for k in sorted(source_keys - merged_keys):
        if any(k.startswith(p) for p in exclude):
            continue
        if include and not any(k.startswith(p) for p in include):
            continue
        to_restore.append(k)

    if not to_restore:
        print("nothing to restore — merged dir already has every requested tensor")
        return

    print(f"\n{len(to_restore)} tensors to restore (include={include}, exclude={exclude}):")
    for k in to_restore:
        print(f"  {k}  <- {source_files[k].name}")

    if args.dry_run:
        return

    from safetensors import safe_open
    from safetensors.torch import save_file

    new_tensors = {}
    new_size_bytes = 0
    for k in to_restore:
        src = source_files[k]
        with safe_open(str(src), framework="pt") as st:
            t = st.get_tensor(k)
        new_tensors[k] = t
        new_size_bytes += t.numel() * t.element_size()

    # Compute per-existing-shard sizes for the index by re-opening each shard.
    existing_shards: dict[str, list[str]] = {}
    existing_sizes: dict[str, int] = {}
    for shard_path in {Path(v) for v in merged_files.values()}:
        with safe_open(str(shard_path), framework="pt") as st:
            keys = list(st.keys())
            existing_shards[shard_path.name] = keys
            total = 0
            for k in keys:
                t = st.get_tensor(k)
                total += t.numel() * t.element_size()
            existing_sizes[shard_path.name] = total

    aux_name = "model-aux-restored.safetensors"
    aux_path = merged_dir / aux_name
    save_file(new_tensors, str(aux_path))
    print(f"\nwrote {aux_path} ({new_size_bytes / (1024 ** 3):.2f} GiB)")

    # Build / rewrite sharded index.
    weight_map: dict[str, str] = {}
    for shard_name, keys in existing_shards.items():
        for k in keys:
            weight_map[k] = shard_name
    for k in to_restore:
        weight_map[k] = aux_name

    total_size = sum(existing_sizes.values()) + new_size_bytes
    index = {
        "metadata": {"total_size": total_size},
        "weight_map": weight_map,
    }
    index_path = merged_dir / "model.safetensors.index.json"
    if index_path.exists():
        backup = index_path.with_suffix(".json.bak")
        shutil.copy2(index_path, backup)
        print(f"backed up old index to {backup.name}")
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {index_path}")

    print("\nsummary:")
    print(f"  shards: {len(existing_shards) + 1}")
    print(f"  total tensors: {len(weight_map)}")
    print(f"  total size: {total_size / (1024 ** 3):.2f} GiB")


if __name__ == "__main__":
    main()
