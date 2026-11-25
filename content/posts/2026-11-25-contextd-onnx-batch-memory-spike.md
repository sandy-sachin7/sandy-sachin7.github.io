---
title: "How one unbounded ONNX batch pushed our local MCP daemon to 2.25 GB RAM"
slug: "contextd-onnx-batch-memory-spike"
date: "2026-11-25"
tags: "Rust, Local AI, Benchmarks"
summary: "Micro-benchmarks on 100 synthetic chunks hid a 2.25 GB RAM spike and a 16.5-second query stall in contextd. Here is how an end-to-end codebase benchmark caught it, and the 12-line micro-batch fix."
read_time: "5 min"
metric: "2.25 GB -> 1.18 GB"
metric_note: "Peak indexing RSS cut nearly in half, with steady-state hybrid queries landing at 6.44 ms p50 and 7.74 ms p95."
repo_url: "https://github.com/sandy-sachin7/contextd"
featured: "false"
poster: "/assets/contextd-poster.png"
poster_alt: "contextd v4.0.2 benchmark plate: ONNX micro-batching at 16 chunks drops peak indexing RSS from 2,246.1 MB to 1,177.6 MB, with warm hybrid queries at 6.44 ms p50 and 7.74 ms p95."
---

Criterion micro-benchmarks lie when they only measure small synthetic inputs.

In [contextd](https://github.com/sandy-sachin7/contextd), our `db_bench.rs` suite benchmarked 100 to 200 synthetic chunks (`fn function_0()`). Every number looked fast. Then I wrote an end-to-end benchmark ([scripts/bench_repo.py](https://github.com/sandy-sachin7/contextd/blob/main/scripts/bench_repo.py)) that boots the real `contextd` daemon, indexes the `contextd` repository itself with local CPU ONNX (`all-minilm-l6-v2`), and fires 15 natural-language hybrid queries against `POST /query`.

The first run exposed two ugly problems immediately:

1. **Peak daemon RSS hit 2,246.1 MB** while indexing a 79-file repository.
2. **The first query stalled for 16,552 ms**, and p50 query latency sat at 801 ms while background indexing ran.

## Root cause: one file, one giant transformer tensor

`Embedder::embed_batch` took every Tree-sitter chunk produced from a single file and packed them into a single `ort::Session::run()` call.

For a small 80-line Rust file, that meant a batch of 4 chunks. For a 1,790-line file like `src/storage/db.rs` or a long `Cargo.lock`, that meant 100+ chunks sent in one `[batch_size, seq_len]` tensor:

- Tokenizer padding (`PaddingStrategy::BatchLongest`) padded every short chunk in the file out to the longest chunk's token length.
- Transformer self-attention memory scaled with `batch_size * heads * seq_len^2`, causing the ONNX Runtime CPU arena to expand past 2.2 GB and hold it.
- Because `Session` sits behind a `Mutex<Session>`, a single 100-chunk `session.run()` held the lock for seconds straight, starving incoming `/query` requests that only needed to embed 8 words.

## The 12-line fix

Capping each `session.run()` call at `MAX_EMBED_BATCH_SIZE = 16` in `src/indexer/embeddings.rs` solved both problems at once:

```rust
const MAX_EMBED_BATCH_SIZE: usize = 16;

pub fn embed_batch(&self, texts: &[&str]) -> Result<Vec<Vec<f32>>> {
    if texts.is_empty() {
        return Ok(Vec::new());
    }
    if texts.len() <= MAX_EMBED_BATCH_SIZE {
        return self.embed_micro_batch(texts);
    }
    let mut all_embeddings = Vec::with_capacity(texts.len());
    for chunk in texts.chunks(MAX_EMBED_BATCH_SIZE) {
        all_embeddings.extend(self.embed_micro_batch(chunk)?);
    }
    Ok(all_embeddings)
}
```

Between micro-batches, the mutex releases, so a live `/query` slips in within milliseconds instead of waiting for an entire file to finish. Padding waste also drops because `BatchLongest` now pads across 16 adjacent chunks instead of 120.

## Measured before and after

Measured on Linux x86_64 (AMD Ryzen 5 5600H, 12 logical CPUs) indexing `contextd` itself (79 files, 1,262 chunks) with `all-minilm-l6-v2` (384 dims):

| Metric | Before (unbounded batch) | After (micro-batch = 16) |
| :--- | :--- | :--- |
| Peak daemon RSS during indexing | 2,246.1 MB | **1,177.6 MB** |
| Warm HTTP hybrid query (`POST /query`) p50 | 801.18 ms (contended) | **6.44 ms** (steady state) |
| Warm HTTP hybrid query p95 | 8,294.36 ms (contended) | **7.74 ms** (steady state) |
| Cold CLI query (`contextd query`) median | 184.7 ms | **190.8 ms** |
| SQLite index size (`contextd.db`) | 5.8 MB | **5.0 MB** (9.8 MB incl. WAL) |

## Bonus bug caught by the same script

Inspecting the actual top-3 retrieval hits in `bench_repo.py` caught a second real bug that unit tests never noticed. Querying `"tree sitter AST splitting for Rust and Python"` returned `Cargo.lock` in positions 1 and 3 ahead of `src/indexer/chunker.rs`, because package lockfiles were not excluded by default. That is now tracked in [contextd#25](https://github.com/sandy-sachin7/contextd/issues/25).

Reproduce on any repository:

```bash
cargo build --release --locked
python3 scripts/bench_repo.py --target .
```
