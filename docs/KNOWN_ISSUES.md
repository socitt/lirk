# Known Issues

Convention: newest entry at the top. Each entry records what was
found, how it was confirmed, what was done about it, and how the fix
was verified — same rigor regardless of whether the bug is closed or
still open.

---

## Why lirk exists instead of real Bazel — confirmed root cause (2026-07-28)

**Status:** Confirmed, not fixable on this device. This isn't a bug in
lirk or in Bazel — it's a platform limitation that explains why lirk
had to exist in the first place, documented here as the definitive
answer rather than an open theory.

### Background

lirk's README already explains that lirk exists because of an
unresolved `signal: hangup` bug in Please (a Bazel-alike) on this
device — see "Why this exists" in [README.md](../README.md). That
investigation left open a natural follow-up question: could real
Bazel itself be used instead of a Please-alike at all? This entry
answers that question directly: no, and the reason is unrelated to
the Please bug — it's one level further down, in the JVM.

### Environment

- OS: Alpine Linux 3.23 (musl libc), `aarch64`.
- Running under **iSH-AOK**, a Linux-userland-on-iOS app, on an
  **iPhone 15 Pro Max** (A17 Pro). Confirmed via `/proc/cpuinfo`
  (`host device: iPhone 15 Pro Max`, `host arch: arm64e(A17 Pro)`) and
  the iOS-sandbox-specific container mount path.
- No Docker/Podman/proot available as a fallback sandbox. Network
  access is unrestricted (GitHub and Alpine CDN mirrors reachable).

### Test 1 — official Bazel release binary: fails (glibc vs musl)

The official `bazelbuild/bazel` GitHub releases only ship binaries
linked against glibc; Alpine uses musl. The matching `linux-arm64`
build segfaults immediately:

```
$ ./bazel version
Segmentation fault
```

Alpine's `gcompat` shim provides the glibc dynamic loader path
(`/lib/ld-linux-aarch64.so.1`) but is not a full glibc
reimplementation — it's missing the `_FORTIFY_SOURCE` "checked"
symbols (`__memcpy_chk`, `__realpath_chk`, `__strncpy_chk`,
`__longjmp_chk`, ...) that hardened binaries like Bazel are compiled
against:

```
$ ldd ./bazel
Error relocating ./bazel: __realpath_chk: symbol not found
Error relocating ./bazel: __memcpy_chk: symbol not found
Error relocating ./bazel: __strncpy_chk: symbol not found
Error relocating ./bazel: __longjmp_chk: symbol not found
```

This is a permanent, well-known limitation of `gcompat`, not
something a config change fixes.

### Test 2 — Alpine's native musl `bazel8` package: installs, JVM crashes

Alpine maintains its own musl-native Bazel builds in `edge/testing`
(`bazel`, `bazel6`, `bazel7`, `bazel8`). Installing `bazel8` (8.7.0)
plus OpenJDK 21 into an isolated `apk --root` test root (so the real
system was untouched) and running it via `chroot` gets past the
libc problem entirely, then hits a JVM crash:

```
$ JAVA_HOME=/usr/lib/jvm/java-21-openjdk bazel --output_user_root=/tmp/bazel_out version
#
# A fatal error has been detected by the Java Runtime Environment:
#
#  Internal Error (assembler_aarch64.hpp:245), pid=947
#  guarantee(val < (1ULL << nbits)) failed: Field too big for insn
```

To rule out this being Bazel-specific, the raw JDK was tested
directly, with JIT and class-data-sharing both disabled to rule out
the obvious first guesses:

```
$ java -version                 → same crash
$ java -Xint -version           → same crash (interpreter only, JIT disabled)
$ java -Xshare:off -version     → same crash (CDS disabled)
```

It crashes on every JVM invocation, before any Bazel-specific code
runs, regardless of JIT/interpreter mode. **The JVM itself cannot
start on this device.**

### Root cause

`guarantee(val < (1ULL << nbits)) failed: Field too big for insn` in
`assembler_aarch64.hpp` is a known class of HotSpot AArch64 codegen
bug (see OpenJDK JDK-8235385, JDK-8247766, JDK-8266885, and similar
reports against Adoptium/Temurin and GraalVM on various aarch64
hosts). It surfaces when the JVM's AArch64 code generator produces an
instruction whose immediate field doesn't fit — in practice this
tends to happen on non-standard or emulated AArch64 execution
environments. Since this host is iSH-AOK's Linux-on-iOS emulation
layer rather than real or virtualized Linux on bare silicon, the most
likely explanation is that iSH's syscall/CPU emulation doesn't behave
identically enough to real AArch64 hardware for HotSpot's low-level
runtime bootstrap (which runs unconditionally, even under `-Xint`) to
succeed. This is an upstream JVM/host-emulation incompatibility, not
something fixable by lirk, by Bazel, or by iSH-AOK config.

### Bottom line

| Layer | Status | Fixable here? |
|---|---|---|
| Official glibc Bazel binary | Segfaults via `gcompat` (missing `_chk` symbols) | No — `gcompat` is permanently incomplete |
| Alpine's native musl `bazel8` package | Installs fine, resolves the libc problem | Yes, this part works |
| Bundled/system JVM (any Java 21 invocation) | Crashes on startup (`assembler_aarch64.hpp`) | **No** — JVM/iSH-host incompatibility |

Even fully solving the musl/glibc mismatch (which Alpine's own
`bazel8` package does) doesn't help, because Bazel requires a working
JVM, and Java itself cannot start on this device. There is no config
flag or package that works around a JVM that crashes on `java
-version`.

### Practical implications

- Real Bazel is not usable on this device, full stop — not because of
  a missing install, but because the host can't run a JVM at all.
- Any other JVM-based tooling (Gradle, Maven, etc.) will very likely
  hit this same crash for the same reason — this is broader than a
  single-tool bug.
- The only realistic paths forward are external to this device: a
  remote build (Bazel remote execution, a CI runner), or running the
  build on real hardware or a standard Linux VM instead of inside
  iSH-AOK.
- This is independent of, and unrelated to, the Please `signal:
  hangup` bug documented in lirk's README — that bug was about
  process/session handling in a JVM-free tool. Even if that bug were
  fully root-caused and fixed, it would not make real Bazel usable
  here, since Bazel's blocker is one layer further down, in the JVM
  itself. An upstream bug report based on this investigation has been
  **filed against [emkey1/ish-AOK](https://github.com/emkey1/ish-AOK)**;
  the local draft was removed once submitted.

---

## `lirk test` failed on root-relative imports — found and fixed (2026-07-27)

**Status:** Fixed. Confirmed 10/10 across two separate 10-run batches
(fresh shell / fresh cache each run); lirk's own 42-test suite still
passes.

### What was found

Reported via an uncommitted `FINDINGS.md` from a dogfooding session
against `terminal-projects`' `shared/term.py` / `shared/term_test.py`
(2026-07-27; see that repo's `docs/KNOWN_ISSUES.md` and
`docs/ACTIVE_SESSION.md`, commits `3c87816` / `c17c6f8`, for the
dogfooding-side narrative).

`lirk build //shared:term` succeeded, but `lirk test
//shared:term_test` failed **every time (0/10 runs, fresh shell per
attempt)** with an identical `ModuleNotFoundError: No module named
'shared'`. `shared/term_test.py` imports its sibling module with a
root-relative import — `from shared import term` — the convention
Bazel/Please encourage for disambiguating packages, and the same
convention `terminal-projects`' pre-existing Please-based `BUILD`
already relied on.

### Root cause

`lirk/actions.py`'s `run_test` ran each test via `python3 -m unittest
<module>` with `cwd` set to the target's own package directory
(`root / target.package`) and no `PYTHONPATH` set. `python -m` puts
the current directory on `sys.path[0]`, so only modules sitting flat
inside that package directory were importable — `shared` (the package
itself, needed to resolve `from shared import term`) was never on
`sys.path`.

This matched a real scope gap in `lirk`'s own test suite: every
fixture (`tests/fixtures/sample_repo/a/test_a.py` etc.) used a flat
import (`from a import greet`), so this path was never exercised
end-to-end before the `terminal-projects` dogfooding run surfaced it.

### Fix

`lirk/actions.py`, `run_test`: keep `cwd=pkg_dir` (unchanged), but
pass an `env` to `subprocess.run` with `PYTHONPATH` set to the repo
root, prepended in front of any existing `PYTHONPATH` from the calling
environment. This is the smallest of three directions the findings
handoff sketched (the other two — running with `cwd=root` plus a
dotted module path, or scoping v1 to flat imports only and documenting
it as a limitation — were not attempted, since this one resolved it).

Flat imports keep working unchanged (still resolved via `cwd` being
`sys.path[0]`); root-relative imports now resolve via the repo root
being on `PYTHONPATH`. No process-group/session/pty/shell=True
constraints were touched — still one direct `subprocess.run()` call
per test file.

### Verification

- Full existing suite: 42/42 tests still passing after the change.
- Reproduction against `terminal-projects`' `shared:term_test`:
  10/10 passes in `env -i` fresh shells.
  10/10 passes in a second batch with `.lirk-cache.json` deleted
  before *every* run, to force a real subprocess execution each time
  rather than a cached pass/fail result — ruling out "lucky cache hit"
  as an explanation.
- No stray state left in `terminal-projects` (`.lirk-cache.json` is
  gitignored there and was removed after verification).
