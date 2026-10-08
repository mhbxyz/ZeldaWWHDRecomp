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
Both binaries contain 39,713 recompiled functions. Reading their exported count
symbols confirms 39,713 compiled hook entries in the hooked binary and no mod-hook
table in authoritative devel. Both use `-O3 -DNDEBUG`; the comparison machine is an
Apple M3 Max with 128 GiB of memory.

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
| Native Linux | 43/43 tests passed in latest implementation CI |
| Native Windows | 42/42 tests passed in latest implementation CI |
| Guest-module Python | 11 tests; actual translated native module execution and example builds |
| Public generator | 10 tests |
| Installer guest-build configuration | 2 tests, including moving a portable release |
| Benchmark helper | 10-test suite passed on all desktop CI hosts; Windows skips the POSIX executable fixture |

The module matrix uses setup's Apple CLT, pinned llvm-mingw and pinned Zig host
toolchains, with clang/lld for PowerPC inputs. It also checks the generated SDK as
PowerPC C and C++. Android builds, but guest mods remain unsupported there.

All CI workflows passed for `414dac6`:
[guest modules](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37839371696),
[Linux](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37839371631),
[Windows](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37839371856),
[Android](https://github.com/ZeldaWWHDRecomp/ZeldaWWHDRecomp/actions/runs/37839371930).

## Performance gate: pending

The queued comparison uses Windfall, 60 fps interpolation with uncapped rendering,
60 game seconds per run, fifteen interleaved pairs per renderer, and a discarded warm-up.
The maintainer removed the load1-below-16 requirement on 2026-10-09. Collection
retains the machine load1-30 pause rule and exclusion of other workers' builds,
test drivers and `run_bench.py`. The maintainer explicitly permits concurrent game
processes (`--no-wait --no-watch`), so this comparison spans both exclusive-game
and shared-game conditions; it cannot establish quiet-machine performance. The maintainer also removed the 15 GB disk gate and
is monitoring space directly. Eight completed Metal pairs were retained when
resuming with that change; only successful samples with completion markers and
matching variant, ordinal, environment and executable are reused. The revised comparison
uses fresh output directories; the earlier partial baseline is excluded.
Both executables load no mods. Frame time and actual logic-pass CPU time must each
have fifteen valid samples; reports use inclusive quartiles and IQR. Report all
per-pair hooks-minus-baseline differences (ms and percent). Explicitly flag run IQR
larger than the difference of medians, and paired-difference IQR larger than the
paired median effect; the maintainer will arrange a quiet-window rerun tonight if so.
Interrupted samples are retried in place with `--retry-disturbed`, preserving A/B
order. A new regression simulates four consecutive disturbances in both warm-up
and the first measured sample, then verifies fifteen accepted samples per executable.

| Renderer | Metric | Devel median / IQR | Hooks median / IQR | Median cost |
| --- | --- | --- | --- | --- |
| Metal | Frame ms | 6.0650 / 0.1033 | 6.0894 / 0.1191 | +0.40% |
| Metal | Logic CPU ms | 3.8680 / 0.0520 | 3.9360 / 0.1170 | +1.76% |
| Vulkan | Frame ms | Pending | Pending | Pending |
| Vulkan | Logic CPU ms | Pending | Pending | Pending |

Metal completed all 15 interleaved pairs; all 30 accepted measured runs have
completion markers. The larger variant IQR exceeds the absolute difference of
medians for both metrics:
frame effect 0.0244 ms versus IQRs 0.1033/0.1191 ms, and logic effect 0.0680 ms
versus maximum IQR 0.1170 ms. Paired-difference IQR also exceeds its median:
frame +0.0288 ms / IQR 0.1497 ms; logic +0.0640 ms / IQR 0.0970 ms.
The measured costs are below 2%, but the spread is larger than the effect.
Keep checks opt-in pending Vulkan and the maintainer's quiet-window rerun;
this shared-machine dataset does not prove a quiet-machine performance gate.

Metal per-pair differences (hooks minus baseline; positive means slower):

| Pair | Frame difference ms | Frame difference % | Logic CPU difference ms | Logic CPU difference % |
| --- | --- | --- | --- | --- |
| 1 | +0.0469 | +0.77% | +0.1760 | +4.53% |
| 2 | +0.0259 | +0.42% | +0.1060 | +2.72% |
| 3 | +0.0288 | +0.47% | +0.0640 | +1.64% |
| 4 | +0.2613 | +4.45% | +0.1120 | +2.91% |
| 5 | +0.0822 | +1.40% | +0.0100 | +0.26% |
| 6 | -0.0569 | -0.94% | +0.0120 | +0.31% |
| 7 | -0.0609 | -1.01% | +0.0120 | +0.31% |
| 8 | +0.0476 | +0.79% | +0.1000 | +2.61% |
| 9 | +0.1932 | +3.17% | +0.1560 | +4.04% |
| 10 | -0.2515 | -3.97% | -0.1060 | -2.63% |
| 11 | +0.0619 | +1.01% | +0.1280 | +3.28% |
| 12 | -0.0944 | -1.52% | -0.0360 | -0.91% |
| 13 | -0.1009 | -1.64% | +0.0280 | +0.70% |
| 14 | -0.1237 | -2.05% | +0.0120 | +0.31% |
| 15 | +0.1754 | +2.99% | +0.0720 | +1.88% |

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

Own redundant generated sources, baseline object files and completed functional-run
saves, states and caches have been removed. The functional cleanup reclaimed about
322 MB while retaining aggregate validation evidence. A further 232 MB of unused
objects, obsolete benchmark attempts and completed fixtures were removed; both
comparison executable hashes are unchanged. Comparison executables and
their isolated inputs remain until the gate finishes. Final cleanup must remove
remaining own build/game-test outputs while retaining aggregate statistics. Nothing
outside the task clone has been deleted.

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
- `7728bc2` Retry disturbed benchmark samples without losing the interleaved gate
- `eb7b0ce` Identify guest packages and show their trust status in Mods
- `414dac6` Gate fifteen-pair benchmarks against other worker activity and report paired effects
