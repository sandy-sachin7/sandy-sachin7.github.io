---
title: "How one unbounded ONNX batch pushed our local MCP daemon to 2.25 GB RAM"
slug: "contextd-onnx-batch-memory-spike"
date: "2026-11-25"
tags: "Rust, Local AI, Benchmarks"
summary: "Micro-benchmarks on 100 synthetic chunks hid a 2.25 GB RAM spike and a 16.5-second query stall in contextd. Here is how an end-to-end codebase benchmark caught it, the micro-batch fix, and the v4.1.0 int8 and retrieval eval numbers."
read_time: "6 min"
metric: "2.25 GB -> 989 MB"
metric_note: "Peak indexing RSS dropped from 2,246.1 MB to 988.7 MB in v4.1.0 (int8), with initial repo indexing down to 33.99 s and steady-state hybrid queries at 4.84 ms p50."
repo_url: "https://github.com/sandy-sachin7/contextd"
featured: "false"
poster: "/assets/contextd-poster.png"
poster_alt: "contextd v4.1.0 benchmark plate: length-sorted 16-chunk micro-batching and int8 ONNX drop peak indexing RSS from 2,246.1 MB to 988.7 MB, with warm hybrid queries at 4.84 ms p50 and 5.69 ms p95."
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

## Bonus bug caught by the same script (fixed in v4.1.0)

Inspecting the actual top-3 retrieval hits in `bench_repo.py` caught a second bug that unit tests missed. Querying `"tree sitter AST splitting for Rust and Python"` returned `Cargo.lock` in positions 1 and 3 ahead of `src/indexer/chunker.rs`, because package lockfiles were not excluded by default. Release `v4.1.0` fixes [contextd#25](https://github.com/sandy-sachin7/contextd/issues/25) by excluding common lockfiles (`Cargo.lock`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`, `uv.lock`, `go.sum`, and `Gemfile.lock`) in `src/indexer/ignore.rs`.

## v4.1.0 update: length-sorted batching, int8 weights, and retrieval eval

Micro-batching in `v4.0.2` fixed the RAM spike and query stalls, while full-repo indexing still took `65.14 s` on FP32 weights. Release `v4.1.0` adds four changes to indexing and reliability:

- **Length-sorted cross-file micro-batches.** Initial repository scans group up to 128 chunks across small files, sort each batch by character length so similarly sized chunks share padding, and run up to 8 ONNX intra-op CPU threads.
- **SHA-256 pinned int8 model.** `all-minilm-l6-v2-q8` (`~22 MB`, pinned to `Xenova/all-MiniLM-L6-v2` commit `751bff37182d3f1213fa05d7196b954e230abad9`) is available alongside FP32.
- **Last-known-good index preservation.** Transient failures during file reads, external parser subprocesses (which run with timeouts and output caps), embedding, or SQLite commits leave existing indexed chunks intact instead of pruning the file.
- **Explicit search modes.** `POST /query` and `contextd query` expose `--mode hybrid|vector|fts` and `--json`, alongside FTS5 stopword filtering and rebalanced RRF (`0.85 * norm_rrf + 0.15 * vsim`).

Measured on the same AMD Ryzen 5 5600H machine (`v4.1.0` FP32 alone cut initial indexing from `65.14 s` to `39.22 s` before int8 brought it to `33.99 s`):

| Metric | v4.0.2 (`all-minilm-l6-v2`, FP32) | v4.1.0 (`all-minilm-l6-v2-q8`, int8) |
| :--- | :--- | :--- |
| Initial full-repo index time | 65.14 s | **33.99 s** (1.92x faster) |
| Peak daemon RSS during indexing | 1,177.6 MB | **988.7 MB** |
| Warm HTTP hybrid query p50 | 6.44 ms | **4.84 ms** (min 3.90 ms) |
| Warm HTTP hybrid query p95 | 7.74 ms | **5.69 ms** |
| Cold CLI query median | 190.8 ms | **112.9 ms** (1.69x faster) |
| SQLite DB size (incl. WAL) | 9.8 MB | **6.5 MB** |

Speed means little without retrieval quality numbers. Release `v4.1.0` checks in an uncontaminated 36-query benchmark ([eval/contextd_queries.json](https://github.com/sandy-sachin7/contextd/blob/main/eval/contextd_queries.json), [scripts/eval_retrieval.py](https://github.com/sandy-sachin7/contextd/blob/main/scripts/eval_retrieval.py)) comparing `contextd` (`all-minilm-l6-v2-q8`) against `ripgrep` across exact-symbol, natural-language semantic, and mixed queries:

| Mode | R@1 | R@5 | R@10 | MRR | nDCG@10 | Semantic MRR | Exact MRR | Mixed MRR |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ripgrep` | **0.722** | **0.889** | 0.917 | **0.793** | **0.817** | **0.506** | 0.958 | **0.917** |
| `fts_only` | 0.556 | 0.861 | 0.972 | 0.685 | 0.752 | 0.341 | **1.000** | 0.715 |
| `vector_only` | 0.389 | 0.833 | 0.889 | 0.571 | 0.629 | 0.378 | 0.779 | 0.556 |
| `hybrid_rrf` (`recency=0, freq=0`) | 0.472 | 0.861 | **1.000** | 0.649 | 0.719 | 0.433 | 0.958 | 0.555 |
| `hybrid_default` | 0.556 | 0.806 | 0.972 | 0.676 | 0.736 | 0.379 | **1.000** | 0.647 |

The trade-off shows directly in that table. `hybrid_rrf` hits `1.000` Recall@10 (every expected file appears in the top 10, vs `0.917` for `ripgrep`) and `hybrid_default` hits `1.000` MRR on exact symbols, while `all-minilm-l6-v2-q8` stays within `0.005` MRR of FP32 (`0.676` vs `0.681`). `ripgrep` still leads top-1 MRR (`0.793` vs `0.676`) when `README.md`, `CHANGELOG.md`, and `docs/` are indexed alongside `src/`, because general-text MiniLM scores prose documentation ahead of Rust source chunks. Pass `--paths src/` or `--file-types rs` for code-only queries.

Reproduce both benchmarks on any repository:

```bash
cargo build --release --locked
python3 scripts/bench_repo.py --target . --model all-minilm-l6-v2-q8
python3 scripts/eval_retrieval.py --model all-minilm-l6-v2-q8
```
