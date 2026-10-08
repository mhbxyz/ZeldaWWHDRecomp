# Mod SDK v2 phase 1 report (in progress)

Phase 1 implementation and functional validation are complete. The required performance
comparison and final cleanup are pending; this is not a completion report. Hook checks
remain opt-in until the performance decision is supported by the required measurements.

## Changes from the prototype

| Area | Phase 1 change |
| --- | --- |
| Loader and hooks | Validate module ranges, tables, hook targets and descriptors before publication. Replacement conflicts name both owners. ORIGINAL bypasses mod chains; port wrappers remain outermost. |
| Packages | `kind: guest`, ELF trust fingerprint, dependency-ordered startup, persisted allocations, visible build errors and restart-only enabled/options snapshots. Direct environment loading is retired. |
| Build and cache | Inspect/build JSON contract, explicit PowerPC ELF linker mode, compiler argument vectors, source/ABI/compiler cache keys, portable tool paths and retained host compiler. |
| Services | Owner-tagged logging, typed manager options, guest-memory heap, read-only input, bounded per-mod files, logic-step time and counter. |
| States | Full 16 MiB mod region and allocator metadata; full/portable ID/version metadata; mismatch warnings allow loading. |
| Public SDK | Re-runnable public-source generator, named function addresses/prototypes, curated actor/Link/camera/items/save/messages layouts and data addresses; named examples. |
| Validation | Real translated-module execution, register-pair ABI checks, cross-platform module CI, real Metal/Vulkan game runs and stronger benchmark gates. |

The generated SDK uses public HD revision `47e1dbc3886cfd8233859dffd73efc41a04a9130`,
with its notice retained. All 22,853 unique verified function bindings are represented;
unsupported compound layout fields remain opaque bytes with verified sizes/offsets.
No unpublished decompilation, recompiled game output or game assets are distributed.

## Functional tests

Runtime source `e7fcd27` and baseline devel `872f17e` were built as Release, BOTH
renderers, with AppleClang 17.0.0 on macOS 26.6.2. Test runs used copied saves, hidden
windows, disabled audio and private shader caches in the task clone.

| Test | Result |
| --- | --- |
| Both examples load through the manager/build bridge | Passed on Metal and Vulkan |
| Heart entry/return hooks and game-function call | Passed on Metal and Vulkan |
| Full and portable states restore with the same mod set | Passed on Metal and Vulkan; no mismatch warning |
| Full state includes the complete mod region | Verified in a real saved state |
| Portable state records both example IDs and versions | Verified in a real saved state |
| Legacy no-mod full state warns and loads | Passed on Metal |
| Changed version warns and loads full and portable states | Passed on Metal (`0.1.0` to `0.1.1`) |

The real full state contains 14,749 replacement calls, 7,374 handled by the mod,
and 382 heart entry/return calls. This checks the alternating ORIGINAL path and
the saved mod data. The isolated test package version was restored afterwards.

The initial game run found a recursive manager-lock acquisition during build-tool
initialization. `e7fcd27` resolves the manager directory outside the locked callbacks;
its regression test and subsequent game runs pass.

## Automated tests and CI

| Suite | Evidence |
| --- | --- |
| Native Linux | 43/43 tests passed in runtime-fix CI |
| Native Windows | 42/42 tests passed in runtime-fix CI |
| Guest-module Python | 11 tests; actual translated native module execution and example builds |
| Public generator | 10 tests |
| Installer guest-build configuration | 2 tests, including moving a portable release |
| Benchmark helper | 6 tests; the executable fixture runs on POSIX hosts |

The module matrix uses setup's Apple CLT, pinned llvm-mingw and pinned Zig host
toolchains, with clang/lld for PowerPC inputs. It also checks the generated SDK as
PowerPC C and C++. Android builds, but guest mods remain unsupported there.

All CI workflows passed for `f1cf6fa`:
[guest modules](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37832729578),
[Linux](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37832729350),
[Windows](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37832729560),
[Android](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37832729398).

## Performance gate: pending

The queued comparison uses Windfall, 60 fps interpolation with uncapped rendering,
60 game seconds per run, ten interleaved runs per executable, and a discarded warm-up.
It requires load1 below 12, no other `run_bench.py`, and more than 15 GB free disk.
Both executables load no mods. Frame time and actual logic-pass CPU time must each
have ten valid samples; reports use inclusive quartiles and IQR.

| Renderer | Metric | Devel median / IQR | Hooks median / IQR | Median cost |
| --- | --- | --- | --- | --- |
| Metal | Frame ms | Pending | Pending | Pending |
| Metal | Logic CPU ms | Pending | Pending | Pending |
| Vulkan | Frame ms | Pending | Pending | Pending |
| Vulkan | Logic CPU ms | Pending | Pending | Pending |

The initial capped Metal warm-up is excluded. `e008152` makes `--uncapped` set
the renderer-independent flag. `f1cf6fa` detects macOS's capitalized `Python`
executable in the exclusion gate. Both changes have regression coverage.
Historical prototype timings and functional-run timings do not satisfy this gate.
If either median cost exceeds 2%, retain opt-in checks and report alternatives that
preserve all-function hooking, such as thin wrappers or code/flag-table locality work.

## Phase 2 and existing mod ports

The [SDK design](mod-sdk-v2.md#phase-2-interfaces-and-integration) proposes bounded,
copied HUD draw lists and mod-owned image handles for both renderers; state-load
notifications must rebuild host resources. Audio needs bounded owned PCM streams,
mixing, cancellation and state-load reset. Neither service is implemented in phase 1.
Catalogue follow-up should use the manager's allocation, compiler, trust and cache
through the existing inspect/build contract. Android needs a compilation/loading,
storage and lifecycle design plus device validation.

The [porting plan](mod-sdk-v2.md#porting-the-existing-minimap-and-dragon-prototypes)
moves gc-minimap's state/math into guest code, options into the manager and cache
files into its data folder. Rendering awaits the HUD service and additional public
field curation. Dragon can use typed hooks/replacements plus ORIGINAL, scoped to its
own actors while preserving the port's outer hooks and timing. Its panel and music
await HUD/audio; public accessors, save behavior and existing gameplay limitations
need validation. These are plans, not completed ports.

## Delivery and remaining work

Work is isolated in the fresh GitHub clone `cx-sdk2`, branch `sdk2-phase1`; only
that branch was pushed. Commits use `Lukas S <lukasschaupp@gmail.com>` and the push
guard remains intact. There are no merges, GitHub posts or mods-repository edits.

Own redundant generated sources and baseline object files have been removed.
Comparison executables and isolated inputs remain until the gate finishes. Final
cleanup must remove remaining own build/game-test outputs while retaining aggregate
statistics. Nothing outside the task clone has been deleted.

Remaining: collect and audit both performance tables, make the default-check decision,
finish this report and the README/docs status, verify final CI, and clean own outputs.

## Implementation commits

The following history is based on authoritative GitHub devel `872f17e`.

- `5b56b57` Mod SDK v2 prototype: PowerPC guest mods translated on install, runtime hooks
- `4694048` Validate guest modules before publishing hooks and report replacement owners
- `446ef34` Version guest module cache by source inputs and expose memory inspection
- `b4333f8` Recognize guest packages with ELF trust and restart-only manager state
- `c3ff10c` Show PowerPC compiler diagnostics when CI toolchain probe fails
- `2462796` Build and load trusted guest packages during manager startup
- `a4c8790` Select PowerPC ELF linker mode explicitly on every modder platform
- `ec27923` Add per-mod typed options, guest heap, input and file services
- `219f92d` Preserve guest mod memory and warn on save-state mod mismatches
- `59bdb4c` Inventory public decomp declarations and layout assertions for SDK generation
- `0894255` Generate named hook addresses from verified public HD functions
- `19cc952` Generate public HD guest bindings and curated layouts with named examples
- `bd0ab26` Extract named public HD data pointers and item table addresses
- `b54f0cd` Support compiled A/B benchmark variants with IQR and logic CPU reporting
- `301174a` Enforce quiet benchmark gates and document phase 2 mod porting
- `c2cf86f` Keep portable guest build tools relocatable and retain the host compiler
- `475f3ea` Complete public ABI declarations and execute register-pair guest modules in tests
- `eb32a93` Verify public SDK headers compile as C and C++
- `a5d4627` Preserve all-function hooks in performance fallback options
- `e7fcd27` Avoid recursive manager lock during guest build startup
- `5e1f266` Record Metal and Vulkan guest-mod state validation
- `e008152` Uncap Metal benchmarks and verify changed-mod state warnings
- `f1cf6fa` Detect macOS Python processes in benchmark exclusion gate
