# Draft upstream issue — pending review, not yet filed

**Status: DRAFT.** This is a draft for a GitHub issue against
[emkey1/ish-AOK](https://github.com/emkey1/ish-AOK), written to
upstream bug-report standards and committed here for review. It has
**not** been filed yet — do not open it upstream until this draft has
been reviewed and approved. Everything below the `---` is the
proposed issue body/title as it would be submitted.

---

**Title:** JVM (OpenJDK/HotSpot) fails to start on aarch64 — "Field too big for insn in assembler_aarch64.hpp"

**Body:**

## Summary

Any JVM invocation (`java -version` included) crashes on startup with
a HotSpot internal error in `assembler_aarch64.hpp`. This happens
before any application code runs, and persists with both JIT and
class-data-sharing disabled. This is not specific to any one
JVM-based tool — it blocks all JVM-based tooling (Bazel, Gradle,
Maven, etc.) on this platform.

## Environment

- iSH-AOK: [FILL IN — exact app version / build number from the app's
  About/Settings screen; not captured in the original investigation]
- Alpine Linux 3.23, `aarch64`, musl libc
- Device: iPhone 15 Pro Max (A17 Pro), per `/proc/cpuinfo`:
  `host device: iPhone 15 Pro Max`, `host arch: arm64e(A17 Pro)`
- JVM: OpenJDK 21 (Alpine's `openjdk21` package, installed as a
  dependency of Alpine's `bazel8` package)

## Steps to reproduce

1. On an Alpine 3.23 aarch64 rootfs under iSH-AOK, install OpenJDK 21:
   ```
   apk add openjdk21
   ```
2. Run:
   ```
   java -version
   ```

## Expected result

JVM starts and prints its version string.

## Actual result

The JVM crashes immediately with a HotSpot internal error:

```
#
# A fatal error has been detected by the Java Runtime Environment:
#
#  Internal Error (assembler_aarch64.hpp:245), pid=947
#  guarantee(val < (1ULL << nbits)) failed: Field too big for insn
```

## Ruling out JIT/CDS as the cause

To check whether this was specific to JIT compilation or
class-data-sharing, both were tested independently with the same
result:

```
$ java -version                 → crashes as above
$ java -Xint -version           → same crash (interpreter-only mode, JIT fully disabled)
$ java -Xshare:off -version     → same crash (class-data-sharing disabled)
```

The crash occurs identically in all three modes, before any
bytecode from `-version`'s own implementation would run. This rules
out JIT compilation and CDS as the trigger — the failure is in the
JVM's low-level startup/bootstrap path, which runs unconditionally
regardless of these flags.

## Impact

This blocks **any** JVM-based tool on this platform, not just one
specific package. Confirmed impact so far: Alpine's native musl-built
`bazel8` package (which otherwise correctly resolves the separate
musl/glibc issue that affects the official glibc-linked Bazel
binaries) cannot run because it depends on this same JVM. The same
crash should be expected for any other JVM-based tooling — Gradle,
Maven, Kotlin, Scala, etc. — since the failure is in JVM startup
itself, not in anything Bazel-specific.

## Suspected root cause (not confirmed, flagging honestly)

`guarantee(val < (1ULL << nbits)) failed: Field too big for insn` in
`assembler_aarch64.hpp` matches a known class of HotSpot AArch64
code-generation bug reported upstream against OpenJDK itself (e.g.
JDK-8235385, JDK-8247766, JDK-8266885) and against other AArch64 JVM
distributions (Adoptium/Temurin, GraalVM) on non-standard or emulated
AArch64 hosts. This looks like an upstream OpenJDK/HotSpot AArch64
codegen issue rather than something specific to iSH-AOK's packaging —
it's plausible that iSH-AOK's syscall/CPU emulation layer doesn't
behave identically enough to real AArch64 hardware for HotSpot's
runtime bootstrap to succeed, but that's a hypothesis, not something
verified here. Filing this here rather than (or in addition to)
upstream OpenJDK because it's iSH-AOK users who hit it in practice,
and because pinning down whether it's reproducible on other
iSH-AOK/device combinations would help clarify whether it's
emulation-specific before escalating further upstream.

## What would help

- Confirmation (or refutation) that this reproduces on other
  iSH-AOK versions / other physical devices, to help narrow down
  whether this is specific to a particular emulation code path.
- Any pointers on whether iSH-AOK's CPU emulation has known gaps in
  the instruction sequences HotSpot's AArch64 backend emits during
  startup.

Happy to provide the full crash log / hs_err_pid file if useful.
