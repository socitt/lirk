# Benchmarks

Measures how lirk behaves as a repo grows, using generated repos whose
every declared dependency is a real import.

```sh
python3 bench/run.py --preset                       # the standard table
python3 bench/run.py --shape mesh --packages 300    # one custom repo
python3 bench/generate.py /tmp/big --shape deep --packages 500   # just generate
```

Shapes: `wide` (independent packages), `deep` (one long chain), `mesh` (a
seeded random DAG, the closest to a real monorepo). Each scenario runs
the real `lirk` CLI as a subprocess, so times include interpreter
startup, as a user would see them.

## Results

On a fast Linux container (2026-11-21, Python 3.13), after the
import-lookup memo and batched cache saves:

| Repo | cold build | cached build | one-file edit | `fix --dry-run` |
|---|---|---|---|---|
| mesh, 200 targets | 0.14s | 0.07s | 0.14s | 0.12s |
| mesh, 500 targets | 0.35s | 0.17s | 0.34s | 0.30s |
| mesh, 1,000 targets | 0.73s | 0.22s | 0.68s | 0.58s |
| deep chain, 500 targets | 0.30s | 0.14s | 0.30s | 0.26s |

Before those two changes, the 1,000-target cold build took 1.40s: half
of it was the same import lookups repeated in every target, and 17% was
rewriting the whole cache file after each target.

A cold `lirk test` costs about 45ms per test file here, almost all of it
starting a fresh Python process. That's the price of lirk's
one-process-per-file model, and why skipping unchanged tests matters
more than anything else.

The edit scenario changes the module at the bottom of the graph, which
in a mesh nearly everything depends on, so it reruns most targets. It
is the worst case for an edit.

**Still to measure: iSH on an iPhone**, the slowest environment lirk
targets. Run `python3 bench/run.py --preset` there and add a row.
