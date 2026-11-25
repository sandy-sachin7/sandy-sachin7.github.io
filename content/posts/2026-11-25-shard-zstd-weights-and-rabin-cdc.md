---
title: "Why Zstd barely compresses model weights, and where Rabin CDC actually wins"
slug: "shard-zstd-weights-and-rabin-cdc"
date: "2026-11-25"
tags: "Rust, Storage, Benchmarks"
summary: "Estimated benchmark tables hurt credibility. Measuring Shard on 256 MiB of high-entropy weights and JSONL datasets shows honest 1.00x weight compression alongside 98.5% Rabin CDC deduplication on offset shifts."
read_time: "5 min"
metric: "98.5% dedup"
metric_note: "Rabin CDC stores 3.74 MiB after a 1 MiB header prepend on 256 MiB high-entropy weights, while fixed 4 MiB chunking re-stores 257.01 MiB."
repo_url: "https://github.com/sandy-sachin7/shard"
featured: "false"
poster: "/assets/shard-poster.png"
poster_alt: "Shard Rabin CDC vs fixed 4 MiB chunking diagram: a 1 MiB prepend over 256 MiB high-entropy weights re-stores 257.01 MiB with fixed chunks vs 3.74 MiB (98.5% dedup) with Rabin CDC."
---

Earlier versions of the [Shard](https://github.com/sandy-sachin7/shard) README included an estimated LAN transfer table that assumed 3x to 5x Zstd compression on 10 GB ML checkpoints.

Any ML engineer reading that table spots the problem in two seconds. Trained FP16, BF16, and FP32 neural network weights are high-entropy floating-point mantissas. General-purpose compressors like Zstd barely move them (typically 1.00x to 1.15x). Publishing estimated transfer speeds built on an unrealistic compression assumption damages trust in the rest of the codebase.

I deleted the estimated table and wrote [benchmarks/bench_real.py](https://github.com/sandy-sachin7/shard/blob/main/benchmarks/bench_real.py) to measure two distinct 256 MiB workloads locally with `shard-cli 2.4.1`:

1. **High-entropy binary weights**: 256 MiB of independent `os.urandom` bytes (`1.00x` Zstd compressibility, matching worst-case trained weights).
2. **Structured JSONL dataset**: 256 MiB of unique training records with prompts and token arrays.

## Measured results (256 MiB artifacts)

Measured on Linux x86_64 (AMD Ryzen 5 5600H, 12 logical CPUs) comparing `--chunker fixed` (4 MiB blocks) against `--chunker rabin` (rolling content-defined boundaries):

| Workload (256 MiB artifact) | Chunker | v1 Store Size (Compression) | v2 Incremental Delta | Dedup Savings | shard verify |
| :--- | :--- | :--- | :--- | :--- | :--- |
| High-entropy weights + 5% append (12.8 MiB) | fixed | 256.01 MiB (1.00x) | **12.81 MiB** | **95.0%** | 238 MB/s |
| High-entropy weights + 5% append (12.8 MiB) | rabin | 256.01 MiB (1.00x) | 16.90 MiB | 93.4% | 358 MB/s |
| High-entropy weights + 1 MiB prepend (offset shift) | fixed | 256.01 MiB (1.00x) | 257.01 MiB | 0.0% | 479 MB/s |
| High-entropy weights + 1 MiB prepend (offset shift) | rabin | 256.01 MiB (1.00x) | **3.74 MiB** | **98.5%** | **982 MB/s** |
| JSONL dataset + 1 MiB prepend (offset shift) | fixed | 25.00 MiB (10.25x) | 24.96 MiB | 0.1% | 1,249 MB/s |
| JSONL dataset + 1 MiB prepend (offset shift) | rabin | 25.05 MiB (10.23x) | **0.51 MiB** | **98.0%** | **1,204 MB/s** |

## What the numbers actually say

- **Appends favor fixed chunks.** If you only append new bytes to the tail of a file, fixed 4 MiB blocks keep every prior boundary aligned and store almost zero overhead (12.81 MiB for a 12.8 MiB append).
- **Offset shifts destroy fixed chunking.** Inserting 1 MiB at the front of a file (a metadata header update, a prepended tensor, or new rows in a dataset) shifts every byte offset downstream. Fixed chunking misses every single block and re-stores the full 257 MiB.
- **Rabin CDC recovers alignment within one chunk.** On the exact same 1 MiB prepend over incompressible weights, `--chunker rabin` stores only **3.74 MiB** (98.5% deduplication). On the 256 MiB JSONL dataset, Zstd compresses v1 by **10.23x** (25.05 MiB) and Rabin CDC stores only **0.51 MiB** for the 1 MiB prepend (98.0% deduplication).
- **Integrity checks stay fast.** Full Blake3 content hashing, Merkle root validation, and Ed25519 signature verification (`shard verify`) runs at 982 to 1,249 MB/s on the offset-shifted workloads.

Run the script on your own disk:

```bash
git clone https://github.com/sandy-sachin7/shard.git
cd shard
cargo build --release
python3 benchmarks/bench_real.py --size-mb 256
```
