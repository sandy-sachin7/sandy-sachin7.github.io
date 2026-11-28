---
title: "Why Zstd barely compresses model weights, and where FastCDC actually wins"
slug: "shard-zstd-weights-and-rabin-cdc"
date: "2026-11-25"
kind: "Engineering"
tags: "Rust, Storage, Benchmarks"
summary: "Measuring Shard on 256 MiB high-entropy payloads, JSONL datasets, and 64 MiB FP32 safetensors-style checkpoints shows 1.00x weight compression, 0.0% dedup on full fine-tuning, 89.0% dedup on frozen backbones, and 98.5% FastCDC dedup on offset shifts."
read_time: "6 min"
metric: "98.5% / 89.0%"
metric_note: "FastCDC deduplicates 98.5% of a 256 MiB high-entropy offset shift and 89.0% of a 64 MiB FP32 checkpoint with a frozen 90% backbone, while full fine-tuning yields 0.0% chunk dedup."
repo_url: "https://github.com/sandy-sachin7/shard"
featured: "false"
poster: "/assets/shard-poster.png"
poster_alt: "Shard FastCDC vs fixed 4 MiB chunking diagram: a 1 MiB prepend over 256 MiB high-entropy weights re-stores 257.01 MiB with fixed chunks vs 3.74 MiB (98.5% dedup) with FastCDC."
---

Earlier versions of the [Shard](https://github.com/sandy-sachin7/shard) README included an estimated LAN transfer table that assumed 3x to 5x Zstd compression on 10 GB ML checkpoints.

Any ML engineer reading that table spots the problem in two seconds. Trained FP16, BF16, and FP32 neural network weights are high-entropy floating-point mantissas. General-purpose compressors like Zstd barely move them (typically 1.00x to 1.15x). Publishing estimated transfer speeds built on an unrealistic compression assumption damages trust in the rest of the codebase.

I deleted the estimated table and wrote [benchmarks/bench_real.py](https://github.com/sandy-sachin7/shard/blob/main/benchmarks/bench_real.py) to measure two distinct 256 MiB workloads locally:

1. **High-entropy binary weights**: 256 MiB of independent `os.urandom` bytes (`1.00x` Zstd compressibility, matching worst-case trained weights).
2. **Structured JSONL dataset**: 256 MiB of unique training records with prompts and token arrays.

One naming fix shipped in `v2.5.0`: Shard's content-defined chunker uses a 64-bit Gear rolling hash with dual normalized masks (**FastCDC**), not Rabin fingerprinting. The CLI flag and Rust API were renamed to `--chunker fastcdc` and `FastCdcChunker`, keeping `--chunker rabin` as a backwards-compatible alias.

## Measured results (256 MiB artifacts)

Measured on Linux x86_64 (AMD Ryzen 5 5600H, 12 logical CPUs) comparing `--chunker fixed` (4 MiB blocks) against `--chunker fastcdc` (Gear-hash content-defined boundaries):

| Workload (256 MiB artifact) | Chunker | v1 Store Size (Compression) | v2 Incremental Delta | Dedup Savings | shard verify |
| :--- | :--- | :--- | :--- | :--- | :--- |
| High-entropy weights + 5% append (12.8 MiB) | fixed | 256.01 MiB (1.00x) | **12.81 MiB** | **95.0%** | 238 MB/s |
| High-entropy weights + 5% append (12.8 MiB) | fastcdc | 256.01 MiB (1.00x) | 16.90 MiB | 93.4% | 358 MB/s |
| High-entropy weights + 1 MiB prepend (offset shift) | fixed | 256.01 MiB (1.00x) | 257.01 MiB | 0.0% | 479 MB/s |
| High-entropy weights + 1 MiB prepend (offset shift) | fastcdc | 256.01 MiB (1.00x) | **3.74 MiB** | **98.5%** | **982 MB/s** |
| JSONL dataset + 1 MiB prepend (offset shift) | fixed | 25.00 MiB (10.25x) | 24.96 MiB | 0.1% | 1,249 MB/s |
| JSONL dataset + 1 MiB prepend (offset shift) | fastcdc | 25.05 MiB (10.23x) | **0.51 MiB** | **98.0%** | **1,204 MB/s** |

## What the 256 MiB numbers show

- **Appends favor fixed chunks.** If you only append new bytes to the tail of a file, fixed 4 MiB blocks keep every prior boundary aligned and store almost zero overhead (12.81 MiB for a 12.8 MiB append).
- **Offset shifts destroy fixed chunking.** Inserting 1 MiB at the front of a file (a metadata header update, a prepended tensor, or new rows in a dataset) shifts every byte offset downstream. Fixed chunking misses every single block and re-stores the full 257 MiB.
- **FastCDC recovers alignment within one chunk.** On the exact same 1 MiB prepend over incompressible weights, `--chunker fastcdc` stores only **3.74 MiB** (98.5% deduplication). On the 256 MiB JSONL dataset, Zstd compresses v1 by **10.23x** (25.05 MiB) and FastCDC stores only **0.51 MiB** for the 1 MiB prepend (98.0% deduplication).
- **Integrity checks stay fast.** Full Blake3 content hashing, Merkle root validation, and Ed25519 signature verification (`shard verify`) runs at 982 to 1,249 MB/s on the offset-shifted workloads.

## Testing the real ML checkpoint premise (v2.5.0)

Synthetic `os.urandom` shifts show how FastCDC handles byte offsets, yet they do not answer what happens across real IEEE-754 floating-point training steps. In `v2.5.0`, [benchmarks/bench_checkpoints.py](https://github.com/sandy-sachin7/shard/blob/main/benchmarks/bench_checkpoints.py) generates 64 MiB safetensors-style FP32 checkpoints (JSON header plus Gaussian-initialized weight tensors) and tests three training update patterns:

| 64 MiB FP32 checkpoint scenario | Chunker | v1 Store Size | v2 Incremental Delta | Dedup Savings |
| :--- | :--- | :--- | :--- | :--- |
| Full fine-tune (100% weights updated by `1e-4` step) | fixed | 59.31 MiB | 59.31 MiB | 0.0% |
| Full fine-tune (100% weights updated by `1e-4` step) | fastcdc | 59.31 MiB | 59.31 MiB | 0.0% |
| Frozen 90% backbone + 10% updated head/adapter | fixed | 59.31 MiB | 7.42 MiB | 87.5% |
| Frozen 90% backbone + 10% updated head/adapter | fastcdc | 59.31 MiB | **6.52 MiB** | **89.0%** |
| 1 MiB adapter prepend + frozen backbone (offset shift) | fixed | 59.31 MiB | 60.24 MiB | 0.0% |
| 1 MiB adapter prepend + frozen backbone (offset shift) | fastcdc | 59.31 MiB | **26.99 MiB** | **54.5%** |

That result sets clear boundaries for where chunk-level deduplication pays off:

- **Full fine-tuning breaks chunk dedup completely.** Even a `1e-4` gradient step flips bits across every weight tensor, so every chunk hash misses (`0.0%` savings).
- **Partial updates and LoRA/adapter workflows deduplicate cleanly.** When 90% of the backbone stays frozen, FastCDC stores `6.52 MiB` (`89.0%` dedup). When a new tensor or metadata block shifts offsets in front of frozen layers, fixed chunking drops to `0.0%` while FastCDC recovers `54.5%`.

## Durable crash-atomic checkout journal (v2.5.1 and v2.5.2)

Release `v2.5.0` added staged multi-file `shard checkout`, yet a closer review showed that staging alone was not crash-atomic. A backup failure on file 2 after file 1 was already replaced, a failure while updating `HEAD`, or a process kill mid-swap could still leave a half-updated working tree, and rollback ignored restore errors.

Release `v2.5.1` replaces that path with a journaled checkout in `core/src/repo.rs` backed by `.shard/checkout_journal.json`:

1. Stage and hash-verify every manifest into same-directory temp files before touching any target.
2. Copy every existing target file to a `.shardbak` backup and `sync_all()` each backup before mutating the working tree.
3. Atomically persist and fsync `.shard/checkout_journal.json` in phase `Swapping`.
4. Swap staged files into place and fsync parent directories.
5. Persist the journal in phase `UpdatingHead`, then update `HEAD` atomically.
6. Remove backup files and delete the journal only after `HEAD` is durable.

If a swap or `HEAD` update fails, rollback restores every replaced file via idempotent copy-and-replace from the durable backups, restores `HEAD`, surfaces any restore error through `ShardError::CheckoutRollbackFailed`, and keeps `.shard/checkout_journal.json` on disk so `shard recover` can retry. Running `shard recover` (or any subsequent `add`, `commit`, or `checkout`) replays an interrupted journal automatically, rolling back `Swapping` journals and rolling forward `UpdatingHead` journals.

Six deterministic boundary fault-injection tests in [tests/resilience.rs](https://github.com/sandy-sachin7/shard/blob/main/tests/resilience.rs) exercise failures during backup creation, mid-swap, `HEAD` update, simulated mid-swap crash, simulated `UpdatingHead` crash, and corrupt-backup rollback error propagation. Release `v2.5.2` opens backup files with write access (`OpenOptions::new().write(true)`) before `sync_all()` so Windows `FlushFileBuffers` succeeds without `os error 5`, verified across Linux, macOS, and Windows CI.

## Descriptor-pinned I/O and hard-kill recovery (v2.6.0)

Path-based filesystem checks leave a TOCTOU window if a directory component is swapped for a symlink between validation and open. A journaled checkout also needs integrity checks on the journal file and its backups so bit rot cannot silently restore corrupted weights.

Release `v2.6.0` closes both gaps:

- `PinnedRepoDir` in [core/src/fs_util.rs](https://github.com/sandy-sachin7/shard/blob/main/core/src/fs_util.rs) pins the repository root with `O_DIRECTORY | O_CLOEXEC` on Unix and performs component-by-component `openat(..., O_NOFOLLOW)`, `mkdirat`, `renameat`, `unlinkat`, and `fstatat(..., AT_SYMLINK_NOFOLLOW)` with parent directory `fsync`. Checkout staging, backup, swap, rollback, and cleanup in [core/src/repo.rs](https://github.com/sandy-sachin7/shard/blob/main/core/src/repo.rs) all route through `PinnedRepoDir`.
- `.shard/checkout_journal.json` now wraps its payload in a versioned CRC32 envelope (`CheckoutJournalEnvelope`) and records `backup_blake3` and `expected_blake3` hashes. Corrupted journals and bit-rotted backups fail loudly instead of silently restoring bad data.
- Five new tests in [tests/resilience.rs](https://github.com/sandy-sachin7/shard/blob/main/tests/resilience.rs) verify CRC32 journal tampering, backup Blake3 bit-rot detection, real OS child-process hard kills (`std::process::exit(137)`, zero `Drop` destructors) for both mid-swap rollback and pre-`HEAD` roll-forward, and Unix `O_NOFOLLOW` rejection of symlinked directories and leaf files.

Run both benchmark scripts on your own disk:

```bash
git clone https://github.com/sandy-sachin7/shard.git
cd shard
cargo build --release
python3 benchmarks/bench_real.py --size-mb 256
python3 benchmarks/bench_checkpoints.py --size-mb 64
```
