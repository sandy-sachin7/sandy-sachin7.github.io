---
title: "Inspecting 50,000-file Delta Lake tables in 111ms and 89MB RAM without a JVM"
slug: "deltalens-50k-files-111ms"
date: "2026-11-25"
kind: "Engineering"
tags: "Rust, Storage, Benchmarks"
summary: "How DeltaLens parses NDJSON commits, V2 Parquet checkpoints, sidecars, and Deletion Vectors from a single 13.8 MB binary, plus head-to-head cold and warm benchmarks against delta-rs."
read_time: "6 min"
metric: "2.91 ms / 12.5 MB"
metric_label: "Measured on AMD Ryzen 5 5600H"
metric_note: "Cold CLI inspect on a real 60-commit checkpointed Delta table vs 56.5 ms cold (3.74 ms warm) and 160.9 MB RSS in deltalake Python."
repo_url: "https://github.com/sandy-sachin7/deltalens"
featured: "true"
poster: "/assets/deltalens-poster.png"
poster_alt: "DeltaLens 2.0.1 vs deltalake 1.7.0 benchmark plate: 111.01 ms cold CLI latency and 89.4 MB peak RSS on 50,000 files, and 2.91 ms on a 60-commit checkpointed table."
---

When a Delta Lake table slows down, the first four questions are almost always metadata questions. How many files sit under 32 MB? How skewed are the file sizes? How much dead data is waiting on `VACUUM`? Did last night's `MERGE` drop or narrow a column?

Answering those four questions usually costs 10 to 30 seconds of Spark startup, an active Databricks SQL warehouse, or a Python virtualenv carrying `deltalake` and `pyarrow`. None of those questions touch a single Parquet row. Every answer already lives inside `_delta_log/`.

I built [DeltaLens](https://github.com/sandy-sachin7/deltalens) (`deltalens`, 13.8 MB standalone Rust binary, MIT) to answer them directly from the terminal or CI without Spark, a JVM, or Python.

## Head-to-head benchmarks (cold and warm)

CLI benchmarks often cheat by comparing a compiled binary against cold Python interpreter startup. To keep the comparison honest, [scripts/bench_compare.py](https://github.com/sandy-sachin7/deltalens/blob/main/scripts/bench_compare.py) measures both **cold CLI subprocesses** and **warm in-process** calls in `deltalake 1.7.0` (`delta-rs` Python 3.12.16) on Linux x86_64 (AMD Ryzen 5 5600H, 12 logical CPUs).

<div class="bench-widget" data-bench-widget>
  <div class="bench-head">
    <p class="bench-title">Interactive comparison: 1,000 commits / 50,000 files (no checkpoint)</p>
    <div class="bench-tabs" role="group" aria-label="Select benchmark metric">
      <button type="button" class="bench-tab" data-bench-mode="latency" aria-pressed="true">Latency (ms)</button>
      <button type="button" class="bench-tab" data-bench-mode="memory" aria-pressed="false">Peak RSS (MB)</button>
      <button type="button" class="bench-tab" data-bench-mode="checkpoint" aria-pressed="false">60-Commit Checkpointed</button>
    </div>
  </div>
  <div class="bench-bars" data-bench-panel="latency">
    <div>
      <div class="bench-item-head"><span><strong>deltalens 2.0.1</strong> (cold CLI)</span><span class="bench-val">111.01 ms</span></div>
      <div class="bench-track"><div class="bench-fill" style="width: 27.9%;"></div></div>
    </div>
    <div>
      <div class="bench-item-head"><span>deltalake 1.7.0 (warm in-process)</span><span class="bench-val">285.46 ms</span></div>
      <div class="bench-track"><div class="bench-fill is-baseline" style="width: 71.8%;"></div></div>
    </div>
    <div>
      <div class="bench-item-head"><span>deltalake 1.7.0 (cold CLI)</span><span class="bench-val">397.34 ms</span></div>
      <div class="bench-track"><div class="bench-fill is-baseline" style="width: 100%;"></div></div>
    </div>
  </div>
  <div class="bench-bars hidden" data-bench-panel="memory">
    <div>
      <div class="bench-item-head"><span><strong>deltalens 2.0.1</strong> (cold CLI)</span><span class="bench-val">89.4 MB</span></div>
      <div class="bench-track"><div class="bench-fill" style="width: 4.4%;"></div></div>
    </div>
    <div>
      <div class="bench-item-head"><span>deltalake 1.7.0 (Python / delta-rs)</span><span class="bench-val">2,048.9 MB</span></div>
      <div class="bench-track"><div class="bench-fill is-baseline" style="width: 100%;"></div></div>
    </div>
  </div>
  <div class="bench-bars hidden" data-bench-panel="checkpoint">
    <div>
      <div class="bench-item-head"><span><strong>deltalens 2.0.1</strong> inspect (cold CLI)</span><span class="bench-val">2.91 ms (12.5 MB)</span></div>
      <div class="bench-track"><div class="bench-fill" style="width: 5.2%;"></div></div>
    </div>
    <div>
      <div class="bench-item-head"><span>deltalake 1.7.0 inspect (warm in-process)</span><span class="bench-val">3.74 ms</span></div>
      <div class="bench-track"><div class="bench-fill is-baseline" style="width: 6.6%;"></div></div>
    </div>
    <div>
      <div class="bench-item-head"><span>deltalake 1.7.0 inspect (cold CLI)</span><span class="bench-val">56.50 ms (160.9 MB)</span></div>
      <div class="bench-track"><div class="bench-fill is-baseline" style="width: 100%;"></div></div>
    </div>
  </div>
  <p class="bench-footnote">Lower is better. Peak RSS measured in an isolated child process so parent Arrow allocations never skew the child reading.</p>
</div>

| Workload | deltalens (cold) | deltalake Py (cold) | deltalake Py (warm) | Peak RSS |
| :--- | :--- | :--- | :--- | :--- |
| Real 60-commit table (Parquet checkpoints, schema change, DELETE) inspect | **2.91 ms** | 56.50 ms | 3.74 ms | **12.5 MB** vs 160.9 MB |
| Real 60-commit table lineage (last 20) vs history(20) | **2.34 ms** | 61.04 ms | 4.45 ms | **12.6 MB** vs 221.6 MB |
| Real 60-commit table diff (v0 to v60) | **2.60 ms** | n/a | n/a | **12.4 MB** |
| 100 commits / 1,000 files (full replay, no checkpoint) | **4.24 ms** | 90.72 ms | 16.81 ms | **12.7 MB** vs 398.4 MB |
| 1,000 commits / 50,000 files (full replay, no checkpoint) | **111.01 ms** | 397.34 ms | 285.46 ms | **89.4 MB** vs 2,048.9 MB |

Run the exact script yourself with zero permanent Python installs:

```bash
git clone https://github.com/sandy-sachin7/deltalens.git
cd deltalens
cargo build --release --locked
uv run --with deltalake --with pyarrow python3 scripts/bench_compare.py
```

## Four design choices behind the speed

### 1. Skip historical cloud listings with _last_checkpoint

On an S3 or ADLS table with 40,000 historical commits, a naive `ListObjectsV2` call burns dozens of HTTP round trips before parsing starts. For `inspect`, `schema`, and `diff`, DeltaLens reads `_delta_log/_last_checkpoint` first. When the target version is at or after the checkpoint version `V`, it calls `object_store::ObjectStore::list_with_offset` starting at `{V:020}`. If the hint is missing, stale, or points to an incomplete multi-part checkpoint, it falls back to a cached single listing.

### 2. Keep Tokio for network I/O and Rayon for CPU parsing

Mixing async object-store reads with parallel CPU parsing often ends in nested Tokio runtimes or thread starvation. DeltaLens separates the two phases cleanly. Cloud backends fetch all needed bytes first through a shared process-wide Tokio runtime using `futures::stream::buffer_unordered(32)`. Only after raw byte buffers are in memory does Rayon fan out to parse NDJSON commits and Arrow Parquet checkpoints in parallel.

### 3. Unified Remove-before-Add state machine

Delta operations like `RESTORE` and Deletion Vector updates emit both a `remove` and an `add` for the same physical Parquet path inside one commit. Keying active files by path alone drops live files or double-counts Deletion Vectors. DeltaLens keys live state by `(percent_decoded_path, deletion_vector_unique_id)` and runs Phase 1 (`Remove`) strictly before Phase 2 (`Add`) inside each commit. Tombstone retention parses `delta.deletedFileRetentionDuration` (defaulting to 7 days) so `inspect` reports exact reclaimable bytes.

### 4. Read-only contract and TOCTOU-free local containment

The `StorageBackend` trait defines only read, list, exists, and stat operations. On Linux and macOS, `LocalStorage` pins the table root via `O_DIRECTORY | O_CLOEXEC` and traverses every relative path component with `openat(..., O_NOFOLLOW)`. V2 checkpoint `_sidecars/` references and cloud keys reject `..`, backslashes, and prefix escapes.

## What shipped in v2.1.0: conformance, fuzzing, and live S3 CI

Fast metadata replay only helps if the replay matches the Delta Lake specification on edge cases. Release `v2.1.0` adds protocol checks and conformance suites on top of the `v2.0.1` benchmarked core:

- **Differential conformance against delta-rs.** [scripts/diff_test.py](https://github.com/sandy-sachin7/deltalens/blob/main/scripts/diff_test.py) generates real tables with `deltalake` across four scenarios (Parquet checkpoints, schema evolution, DELETE/UPDATE/MERGE/OPTIMIZE/VACUUM, nested column-mapped schemas, and Deletion Vectors) and checks every active file path, size, row count, and schema against `deltalens inspect --json`.
- **Fail-loudly reader protocol checks.** Any table requiring `minReaderVersion > 3` or an unsupported `readerFeatures` entry (such as `catalogManaged`) returns `DeltaLensError::UnsupportedProtocol` instead of silently misreading log state.
- **Spec-compliant typeWidening rules.** Schema diffing now treats `date` to `timestamp` as breaking, permits `date` to `timestamp_ntz`, allows integer-to-double and bounded integer-to-decimal widenings (`byte`, `short`, `integer`, `long` to `decimal(p, s)` with integral digits at least `3`, `5`, `10`, and `19`), and allows scale-preserving decimal widening.
- **Parser fuzzing and live S3 HTTP CI.** Four `cargo-fuzz` targets under `fuzz/` exercise NDJSON actions, schema JSON, table paths, and V2 sidecar parsing. Integration tests in `tests/cloud_s3.rs` run in GitHub Actions against an ephemeral Moto S3 HTTP server via `scripts/run_s3_test.py`.

## What shipped in v2.2.0: Apache Spark DAT conformance and continuous fuzzing

Comparing against `delta-rs` alone leaves open whether a parser matches tables written by Apache Spark itself. Release `v2.2.0` adds official Spark conformance tests, scheduled fuzzing in CI, and an opt-in live cloud workflow:

- **Official Apache Spark DAT suite (`delta-incubator/dat v0.0.3`).** [scripts/dat_test.py](https://github.com/sandy-sachin7/deltalens/blob/main/scripts/dat_test.py) downloads the SHA-256 pinned `delta-incubator/dat v0.0.3` release archive (`19c045bc...`) and validates all 19 Spark-written Delta tables across 29 expected snapshots (both `latest` and historical versions `v0`, `v1`, and `v2`). All 19 tables and 29 snapshots pass in the `spark-dat` GitHub Actions job on every push.
- **Continuous parser fuzzing in CI.** Checked-in seed corpora under `fuzz/corpus/` drive all four targets (`commit_ndjson`, `last_checkpoint`, `parquet_checkpoint`, `schema_json`) in [.github/workflows/fuzz.yml](https://github.com/sandy-sachin7/deltalens/blob/main/.github/workflows/fuzz.yml) on a weekly schedule, on parser pull requests, and on manual dispatch.
- **Opt-in live cloud check.** [.github/workflows/cloud-live.yml](https://github.com/sandy-sachin7/deltalens/blob/main/.github/workflows/cloud-live.yml) runs `deltalens inspect` against live S3, GCS, or Azure ADLS buckets via `workflow_dispatch` when credentials are supplied.

## Wiring it into CI in five lines

DeltaLens ships a composite GitHub Action with SHA-256 binary verification. Breaking schema changes (column removal, Column Mapping renames, narrowing type conversions, or tightened nullability) exit with code `2` and post a report to `$GITHUB_STEP_SUMMARY`.

```yaml
- uses: sandy-sachin7/deltalens@main
  with:
    command: diff
    path: s3://my-bucket/warehouse/transactions
    args: --v1 ${{ env.PREV_VER }} --v2 ${{ env.CURR_VER }} --fail-on-breaking
```

Install `v2.2.0` with `cargo install deltalens` (or `--no-default-features` for a pure-local build with zero HTTP dependencies).
