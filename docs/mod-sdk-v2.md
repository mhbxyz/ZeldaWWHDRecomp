# Mod SDK v2: PowerPC guest mods (design study and prototype)

Status: **prototype** on branch `sdk2-guest-mods`, off by default. The Native SDK v1
(`runtime/include/wwhd_mod.h`, [mod-manager.md](mod-manager.md)) stays supported and unchanged.

Code mods for this port are written in C (or C++) against mod headers and compiled for the
console CPU: 32-bit big-endian PowerPC, the game's ABI. The package is the same on every
platform. On install, the port translates the mod's PowerPC code to C with its own translator
and compiles it with the player's local compiler (the one setup already uses for the game
code) into a loadable module. Mods hook or replace game functions **at runtime**: the game
code is not translated or compiled again.

This follows the model of Zelda64Recomp / N64Recomp mods (see [Prior art](#prior-art)).

## Contents

- [Prior art](#prior-art)
- [The port today](#the-port-today)
- [Runtime hooking: options and costs](#runtime-hooking-options-and-costs)
- [Mod toolchain and package](#mod-toolchain-and-package)
- [Install-time translation](#install-time-translation)
- [Headers for modders (legal)](#headers-for-modders-legal)
- [Host services](#host-services)
- [Trust](#trust)
- [Mod manager integration](#mod-manager-integration)
- [Prototype: what exists and how to run it](#prototype-what-exists-and-how-to-run-it)
- [Measurements](#measurements)
- [Open decisions](#open-decisions)
- [Road to a production version](#road-to-a-production-version)

## Prior art

Checked on 2026-10-08 in the public sources of
[N64Recomp](https://github.com/N64Recomp/N64Recomp) (`ffb39cd`),
[N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime) (`cdf5abb`),
[Zelda64Recomp](https://github.com/Zelda64Recomp/Zelda64Recomp) (`b65c482`) and
[MMRecompModTemplate](https://github.com/Zelda64Recomp/MMRecompModTemplate) (`0c3e82c`).
Only ideas are described here; no code was copied.

| Topic | Zelda64Recomp / N64Recomp |
| --- | --- |
| Package | `.nrm` = zip of `mod.json` (id, version, authors, `minimum_recomp_version`, dependencies, optional dependencies, `config_schema`, `native_libraries`), `mod_syms.bin` (sections, functions, relocations, imports/exports, replacements, hooks, events) and `mod_binary.bin` (section bytes). Built by `RecompModTool` from a linked ELF (N64Recomp `RecompModTool/main.cpp`, `src/mod_symbols.cpp`). |
| Toolchain | Stock clang + ld.lld for MIPS (`-target mips -mips2 -mabi=32 -O2 -G0 ...`, linked with `--emit-relocs` at 0x81000000; the template's `Makefile` / `mod.ld`). Apple clang lacks the target, so macOS modders use Homebrew LLVM. |
| Marking | `RECOMP_PATCH`, `RECOMP_HOOK("fn")`, `RECOMP_HOOK_RETURN`, `RECOMP_EXPORT`, `RECOMP_IMPORT`, `RECOMP_CALLBACK` are only `section(...)` attributes; the tool reads the sections (template `include/modding.h`). Patch/hook targets are checked by name against the game's reference symbols at build time. |
| Load-time recompilation | A **live recompiler** (sljit JIT) turns the mod's MIPS code into host code at every launch, on all platforms (`LiveRecomp/`). An offline C path (`OfflineModRecomp`, `.offline.nrm` + a native library) exists for debugging only. No cache. |
| Replacement | The runtime **overwrites the first bytes of the native game function** with an absolute jump into the mod (x86-64 `movabs/jmp`, ARM64 `ldr/br`), making the page writable meanwhile (N64ModernRuntime `librecomp/src/mods.cpp`, `patch_func`). Zero cost for functions that are not replaced. |
| Hooks | Per (function, entry/return) a hook slot. The function is **regenerated from the original ROM code** by the live recompiler with `run_hook(slot)` calls inserted and jump-patched in. Needs the original code and a JIT at runtime. Return hooks can read the return value. |
| Conflicts | Two mods replacing one function: error. Replacing a function the port itself patched needs `RECOMP_FORCE_PATCH`. Any number of hooks. |
| Calls | Mod → game: relocations against reference symbols, resolved to direct native calls. Function pointers: every mod function registered at its guest address. |
| Versioning | `minimum_recomp_version`, `game_id`, dependency minimum versions, native library `recomp_api_version == 1`. |
| Events | `RECOMP_DECLARE_EVENT` / `RECOMP_CALLBACK`: callbacks in mod order, register context restored between them. The port declares base events. |
| Native libraries | "extlib": `.dll/.so/.dylib` named in the manifest, loaded next to the mod, functions callable as imports `(rdram, ctx)`. Full process privileges. |
| Config | Typed schema (enum, number, string, ranges), read with `recomp_get_config_*`, stored per mod. |
| Memory | Mod sections copied into emulated RAM from 0x81000000, guard gaps, then the mod heap. |
| Trust | No trust prompt or sandbox found; native libraries run unrestricted. |

The two ideas that do **not** carry over: jump-patching native code (our game code is in the
signed, locally linked executable; macOS on Apple silicon forbids writable code pages of a
signed image, and the hardened runtime of a release would forbid it entirely) and hooking by
regeneration (we have no in-process recompiler or JIT; our "recompiler" is Python + the local
C compiler, used offline at setup). The rest (section-marked hooks, name or address based
imports, conflict rules, typed config, events, function registration for pointers) does.

## The port today

- **Translation** (`tools/recomp/recomp.py`, `ppc2c.py`): each guest function becomes a C
  function `void f_XXXXXXXX(Cpu* c)`; the 39,713 functions of `cking.rpx` go into 78
  `code_NNN.c` files (about 170 MB of C).
- **Calls**: direct `bl` → a direct C call `f_X(c)`; branches to other functions → `MUSTTAIL`
  tail calls; computed calls (`bctrl`, `blrl`, vtables, process method tables) and unknown
  targets → `c->pc = target; ppc_dispatch(c)`, a lookup in a flat 16 MiB-range table
  (`runtime/src/core.cpp`, `dispatch::lookup`, one load) indexed by `(addr - 0x02000000) / 4`.
- **Port hooks** (`tools/recomp/hooks*.txt`): for a listed address the generator emits
  `f_X(c) { hook_X(c); }` and renames the game code to `f_X_orig`; the runtime defines
  `hook_X` (frame interpolation, true 60, gameplay mods). `@ADDR` lines add instruction-level
  `site_X(c)` calls. Changing the list requires translating and compiling the game again.
- **Local build** (`tools/installer/setup.py`): setup runs `recomp.py`, compiles the 80
  sources with the pinned toolchain (`xcrun clang` from Apple's Command Line Tools on macOS,
  llvm-mingw on Windows, zig on Linux; flags from `sdk/manifest.json`, i.e.
  `-O3 -ffp-contract=off -fno-strict-aliasing`), archives them and links them with the
  prebuilt runtime into the executable. On an M-series Mac this takes about 1.5 minutes at
  4 jobs (about 5 CPU minutes).
- **Native mods v1**: `kind: native` packages, `dlopen`/`LoadLibrary` of a prebuilt library
  per platform, a C ABI with frame callbacks and guest-memory access, one-time trust
  confirmation.

## Runtime hooking: options and costs

| Option | Cost per call of an unhooked function | Code size | Hookable | Notes |
| --- | --- | --- | --- | --- |
| **(a) flag check at every function entry** (recommended, prototyped) | 1 load + test + not-taken branch (arm64: `adrp; add; ldrb; cbnz`) | +3.2 MB text (+7.8 %) for the cold paths, +40 KB flags, +318 KB table | every function, also through pointers and tail calls | no change of the call graph; inlining unaffected |
| (b) all direct calls through a function table | an indirect call instead of a direct one (load + `blr`), no inlining across calls | small | every function | indirect branches strain the predictor at ~40k targets; blocks clang's inlining and musttail optimizations |
| (c) only a published "hookable" subset (like `hooks.txt`) | zero for the rest | tiny | the list only | a new hook point needs a port update (and the game rebuilt on the player's machine) |
| (d) patch native code at load (N64Recomp) | zero | zero | every function, but hooks need regeneration | not possible on macOS arm64 for a signed executable; Windows/Linux need writable code pages; hooks would need a JIT |

(a) is the recommendation: every game function is hookable with a cost at the level of the
two checks every function already has (`PPC_ENTER`: trace switch and core preemption), and no
part of the game must be rebuilt when mods change. (c) remains a fallback if the measured cost
were too high (it is not, see [Measurements](#measurements)); (a) and (c) can also be combined
(check only in functions that are not on a "hot leaf" list).

### Mechanism (prototype)

`recomp.py --mod-hooks` (or `WWHD_RECOMP_MOD_HOOKS=1`) emits at the start of every function body:

```c
void f_0200EDC8(Cpu* __restrict c) {
    PPC_ENTER(0x0200EDC8u);
    PPC_MOD_HOOK(515, 0x0200EDC8u);   /* ordinal in g_recomp_funcs, address */
    ...
```

`PPC_MOD_HOOK` (`runtime/include/ppc.h`) tests `g_mod_hook_flags[ordinal]`, one byte per
function (generated in `table.c`). A set flag diverts to `ppc_mod_run`
(`runtime/src/mods/guest_mods.cpp`), which runs the entry hooks, the replacement or the
original, then the return hooks. To run the original, the runtime sets `c->mod_skip` to the
function address and calls the function body (`g_mod_bodies[ordinal]`); the check consumes
the skip. `Cpu::mod_skip` uses what was padding, so `sizeof(Cpu)` and save states are
unchanged.

Calling convention of hooks is the game's: entry and return hooks receive the function's
arguments (r3–r10 and f1–f8 are restored before every hook), a return hook leaves the return
value (r3, r4, f1) as the function produced it, a replacement is the function. r1/r2/r13 are
preserved by every callee (ABI). Return hooks run in reverse load order.

### Port hooks, frame interpolation and true 60

The check sits in the game code (`f_X`, or `f_X_orig` behind a port hook), so the port's
own hooks stay **outermost**: interpolation and true 60 decide first whether and how a game
function runs, and mods hook the game's code below them.

- A mod hooking a logic function runs once per logic step, also at 60/120/240 fps
  interpolation (hold passes skip the logic, so they skip the mod too).
- A mod hooking a drawing function runs once per displayed frame.
- With true 60, the port scales the arguments of the `cLib_addCalc*` family by the step
  length before the game code runs; a mod replacing such a function receives the scaled
  arguments, so its replacement stays 60 Hz correct. Mods that count steps should use a
  host service for the step length (planned: `wwhd_logic_dt`).
- A mod replacement of a function the port hooks itself (all `hooks*.txt` entries) is
  allowed but should be marked in the mod (like N64Recomp's force patch) so the manager can
  warn. Not enforced in the prototype.

## Mod toolchain and package

- **Compiler**: clang with the PowerPC target and ld.lld, free on all three platforms
  (LLVM releases; Homebrew `llvm` + `lld` on macOS; Apple's clang has no PowerPC target). Tested:
  Homebrew clang 20.1.8 and ld.lld 21. `powerpc-eabi-gcc` (devkitPPC) would work as well
  since the output is a standard ELF, but is not needed.
- **Flags** (see `runtime/guest/include/wwhd_guest.h`, `examples/guest-mods/Makefile`):
  `--target=powerpc-unknown-eabi -mcpu=750 -O2 -ffreestanding -fno-builtin -nostdlib
  -fno-jump-tables -ffunction-sections -fdata-sections`. `-mcpu=750` keeps to instructions
  of the game's CPU family (no AltiVec, no `isel`); clang does not use small-data (r2/r13)
  addressing for this target, so the game's r2/r13 stay untouched.
- **Output**: one relocatable ELF per mod (`ld.lld -m elf32ppc -r *.o -o mod.elf`), not linked to an
  address. Relocations and undefined symbols are resolved on install.
- **References to the game** by address, so no symbol database is needed:
  `WWHD_GAME_FUNC(0x0200ED84, void, cLib_addCalc2, (f32*, f32, f32, f32))` declares a game
  function (`__wwhd_game_0x0200ED84` as the symbol), `WWHD_GAME_ORIGINAL(...)` the game's own
  code below all mods, `WWHD_GAME_DATA(addr, type)` a variable. A later SDK can add
  name-based symbols on top (a generated `game_symbols.txt`; see the legal section).
- **Hooks** are descriptors in section `.wwhd_hooks` (`WWHD_REPLACE`, `WWHD_HOOK`,
  `WWHD_HOOK_RETURN`), read by the translator.
- **Memory**: the mod's code, data and bss live in guest memory at a base the mod manager
  assigns, in a region the game and the runtime do not use (`0x7F000000`–`0x80000000`,
  16 MiB). Game code can therefore use pointers into mod data, and mod functions are
  registered in the dispatch table at their guest addresses (function pointers handed to the
  game work). A mod heap (guest `malloc`) is a planned host service.
- **ABI**: the game's: arguments r3–r10 / f1–f8, results r3/r4/f1, stack r1, small-data
  bases r2/r13 owned by the game, big-endian. Varargs follow the SVR4 rules (cr6).
- **Package** (`manifest.json`, the v1 manifest format plus):
  `"kind": "guest", "guest": {"api_version": 1, "elf": "mod.elf"}`. Options, dependencies
  and conflicts as for v1.

## Install-time translation

`tools/guestmod/build_guest_mod.py PACKAGE --out CACHE [--base ADDR] [--cc CC] [--json]`:

1. reads the manifest and the ELF (`tools/guestmod/guestmod.py`): lays the allocatable
   sections out at the base (code, read-only data, data, bss), applies all relocations
   (`ADDR32`, `ADDR16_LO/HI/HA`, `REL24`, `REL14`, `REL32`; anything else, e.g. small-data
   relocations, is an error), resolves undefined symbols (`__wwhd_game_*`, `__wwhd_orig_*`,
   `__wwhd_gdata_*`, otherwise a host service by name);
2. finds the functions (symbols, call targets, address-taken code, cross-function branch
   targets) and translates every instruction with **the game's translator** (`ppc2c.py`);
   unsupported instructions are an install error that names them;
3. writes one C file: the functions, the relocated initial memory image, the function table,
   the hook table and the list of host services; it exports `wwhd_guest_module_v1`
   (`runtime/include/wwhd_guest_abi.h`) and **imports nothing from the executable** (all
   runtime entry points come through a host table), so a module is a plain shared library on
   every platform and does not depend on how the game code was built;
4. compiles it with the local compiler (`-O2 -ffp-contract=off -fno-strict-aliasing -fPIC
   -shared`) into `CACHE/<key>/<id>.dylib|.so|.dll`.

The cache key covers the ELF, the base, the translator version, the module ABI version and
the compiler with its flags. A cached module is reused; a port update that changes the
translator or the ABI changes the key and the module is rebuilt on the next start (a few
hundred milliseconds per mod). A game rebuild alone does not invalidate modules; the runtime
re-validates hook targets on load (every target must be a function entry of this build).

### Manager startup and local tools (phase 1)

Guest packages use the same one-time code trust dialog as native packages. The
fingerprint is the SHA-256 of `mod.elf`, so rebuilding a module does not ask again.
The manager freezes the enabled guest set and options during initialization.
After memory and dispatch initialization, before guest threads start, it inspects,
allocates, builds and loads that set in dependency order. Failures appear in each
package's details in the Mods tab. Later enable, disable, profile and option changes
need a restart; an active guest module remains resident until the process exits.

Memory assignments are 64 KiB aligned and persisted in `profiles.json` under
`guest_regions`. Valid assignments remain stable, including those of disabled
installed mods. Growing a mod may move it and rebuild its module; removing a mod
releases its assignment. Overlapping or invalid saved assignments are repaired.
A guest startup dependency must already be active (content/another guest mod), or
be a settings preset; a native plugin loaded later during gameplay cannot supply
a startup dependency.

Setup writes `guest-sdk.json` in the game data directory with its Python command,
compiler argument vector, translator path and SDK headers. Keep the release tools
and local compiler installed. If they are missing, the Mods tab asks you to run
setup again. Development builds may select an equivalent JSON file with
`WWHD_GUEST_BUILD_CONFIG`. The bridge runs argument vectors directly, without a
shell; `--cc-json '["compiler", "arguments"]'` preserves paths containing spaces.
The original `--cc` interface remains supported for catalogue integrations.

On Windows, the standard LLVM installer and llvm-mingw do not include the PowerPC
backend. Modders should use the MSYS2 CLANG64 clang/lld packages (an all-target build),
while players' host modules still compile with setup's pinned llvm-mingw. Pass
`-m elf32ppc` to lld to select ELF output on Windows, where MSYS2 defaults to PE. The
[MSYS2 LLVM package recipe](https://github.com/msys2/MINGW-packages/blob/master/mingw-w64-llvm/PKGBUILD)
selects all targets for its clang build. CI verifies the actual PowerPC compilation.

### Build-step contract additions (phase 1)

`build_guest_mod.py PACKAGE --inspect --base ADDR --json` reports the relocated
`memory_size`, the 64 KiB rounded `allocation_size`, `base`, package `id` and
`elf_sha256` without invoking a compiler. The manager uses this to allocate the
mod region before building. Bases must be 64 KiB aligned in the mod region.
The existing build command and last-line JSON contract remain supported; successful
build and cache-hit responses now also contain these memory and ELF metadata fields.

Cache keys include the actual guest translator, `ppc2c.py`, build script and runtime
ABI/header bytes, in addition to their version strings, ELF, base, package ID,
compiler command/version and flags. This also invalidates development caches when
the translator or CPU layout changes without a release version bump. ELF paths are
relative to the package; parent paths, absolute paths and symlinks are rejected.

The `guestmods` CI workflow compiles the examples with Apple CLT, pinned llvm-mingw
and pinned zig selected by setup. The modder-side PowerPC compiler remains clang
with lld. These tests use synthetic mod code and require no game files.

Errors for the player are short (`--json`: `{"ok": false, "error": "..."}`), for example
"instructions the translator does not support: …", "the mod needs guest API 2; this game
supports 1", "the local compiler could not build the mod (see …/build.log)". Load-time
errors (hook target is not a game function, function already replaced by another mod, a
host service missing in this version, memory overlap) leave the mod unloaded and are logged.

## Headers for modders (legal)

What a modder needs, and where it can come from:

| Part | Source | Public? |
| --- | --- | --- |
| SDK header (`wwhd_guest.h`): types, hook macros, host services | written for the port | yes (in this branch) |
| Engine semantics: what functions do, struct and class layouts of the GameCube game | [zeldaret/tww](https://github.com/zeldaret/tww) (CC0) | yes |
| HD addresses already used by the public port (≈ 100 named functions in `tools/recomp/hooks*.txt`, save-data address in `cheats.cpp`, `dComIfG_gameInfo.play` in `savestate.cpp`) | this repository | yes |
| HD addresses of the remaining functions, with names (the HD ↔ GameCube function mapping) | **our private decomp (`wwhd_src`)** | **no** |
| HD struct layouts (fields moved or added in HD; e.g. actor fields sit at different offsets than on GameCube) | **our private decomp** (verified there) | **no** |
| Declarations generated from the decomp's verified source | **our private decomp** | **no** |

Nothing of the private decomp is in this branch. A usable header set for more than the few
public addresses depends on it. Options for the maintainer:

1. **Address-only SDK** (prototype state): modders find addresses themselves (Cemu debugger,
   Ghidra on their own dump) and use GameCube names/layouts from zeldaret/tww. Legal and
   public now; poor usability.
2. **Publish a symbol table** (`address → GameCube decomp name`, plus HD-specific names) as a
   generated data file, and let the SDK declare functions by name. Exposes the result of the
   private matching work, not its code. Needs the maintainer's OK.
3. **Publish curated headers** for the common game systems (player, actors, save data, HUD,
   camera) with HD layouts, written fresh from the GameCube headers plus verified HD offsets.
   Needs the maintainer's OK for the offsets taken from the private decomp.
4. **Publish the decomp** later (when it is ready), and generate the SDK headers from it.

## Host services

Services use the game ABI and resolve by name when the module loads. ABI 2 marks each
imported service call with its originating mod instruction address in `Cpu::pc`.
This identifies the owning package even for mod functions called through game function
pointers or nested cross-mod calls. Old modules must rebuild; the cache hashes the ABI
header and translator sources, so this happens automatically.

| Service | Phase 1 behavior |
| --- | --- |
| `wwhd_log`, `_int`, `_hex`, `_float` | Log lines tagged with the calling mod ID. |
| `wwhd_config_int`, `_bool`, `_float`, `_string` | Typed values from the manager's startup snapshot; numeric/bool calls use their fallback on missing or wrong-type values. `_float` returns a double. Strings include enum options and copy into a caller-owned guest buffer. |
| `wwhd_malloc`, `wwhd_free` | Per-mod 16-byte-aligned guest heap. `guest.heap_size` chooses bytes (default 256 KiB, maximum 8 MiB); null on exhaustion. Metadata stays in guest memory, so restoring it restores allocation state. |
| `wwhd_input_read` | Read-only VPAD-style buttons, sticks and touch in `wwhd_input_state`. |
| `wwhd_file_read`, `wwhd_file_write` | Flat filenames in `ModManager/Data/<id>`, at most 1 MiB per call. No directory components, symlinks, hardlinks or Windows device names. Write replaces the file. Both return bytes transferred, or -1 on failure. |
| `wwhd_logic_dt`, `wwhd_logic_step` | Seconds in the current logic step (true-60 scaling included), and the full logic-step counter. |
| `memcpy`, `memmove`, `memset` | Compiler-generated struct copies and explicit guest-memory operations. |

Option and enabled-set changes take effect on restart. `WWHD_GUEST_OPT_*` and the
prototype's unchecked `WWHD_GUEST_MODS` direct-library loading are retired; install
packages through the mod manager and its code trust dialog.

The HUD service is phase 2. Its proposed interface is renderer-independent submission
of text, rectangles and mod-owned RGBA images, with opaque per-mod resource handles,
explicit guest buffer lengths, frame-scoped draw lists and cleanup at shutdown. The
host would copy pixels/text before returning and render the lists through Metal/Vulkan
at the overlay stage. No guest pointers would be retained by a renderer. Audio streams,
events and additional compiler helpers also remain future work.

## Trust

A translated guest mod is compiled to native code in the game process. Two properties limit
it compared with a v1 native library: its loads and stores go to the 4 GiB guest window, and
it reaches the host only through the services above and the game's own functions (including
the runtime's emulated system calls, e.g. the game's file access). That is a mitigation, not
a sandbox: a mod can still crash the game, corrupt the save the game writes, and any bug in
the runtime's emulated system calls is reachable. Recommendation: the same one-time trust
confirmation as v1 native mods, fingerprinting `mod.elf` (the platform-independent code)
instead of a library; a rebuilt module of the same ELF does not ask again. The install step
itself is safe to run on untrusted packages: the generated C contains only numbers and
checked identifiers.

## Mod manager integration

The catalogue's `build_guest_mod` setup step (browse/install/setup flow) runs, per enabled
guest package and after every port update:

```
python3 tools/guestmod/build_guest_mod.py <ModManager>/Mods/<id> --out <ModManager>/GuestBuild \
        --base <assigned base> --cc "<sdk/manifest.json toolchain cc>" --include <sdk>/include --json
```

- The manager assigns each installed guest mod a 64 KiB-aligned base in the guest mod region
  (from its memory size, stored in `profiles.json`) and rebuilds when it changes.
- The last stdout line is JSON: `ok`, `module`, `cached`, `error`. The manager shows `error`
  in the package details and keeps the package unloaded.
- On start, the runtime loads the modules of the enabled guest packages before any guest code
  runs (the prototype takes `WWHD_GUEST_MODS=path,...`). Enabling, disabling and changing the
  load order need a restart in the first version (hooks are installed before the game
  threads start).
- Requires game code built with `--mod-hooks`; setup passes it by default once the decision is
  made. Without it the runtime logs that guest mods are unavailable.

## Save states

Full states capture the complete guest mod region (`0x7F000000`–`0x80000000`),
including module data and guest heap metadata. Zero chunks remain sparse. Restoring a
full state restores allocations as well as the bytes in those allocations.

Both full states and portable `.wwstate` files record the loaded guest mods by ID and
version. Loading a state with a different set displays a warning and continues; ordering
alone does not cause a warning. Older states without this metadata count as an empty mod
set. Portable states restore game progress and position, rather than mod memory.

Guest modules remain selected at startup. Loading a state does not install, build, enable
or disable mods. Use the same mod versions that created a state when reproducing gameplay.

## Prototype: what exists and how to run it

| Part | File |
| --- | --- |
| generator option `--mod-hooks` | `tools/recomp/recomp.py` |
| check macro, `Cpu::mod_skip` | `runtime/include/ppc.h` |
| module ABI | `runtime/include/wwhd_guest_abi.h` |
| loader, hook chains, host services | `runtime/src/mods/guest_mods.cpp` |
| translator, install-time build | `tools/guestmod/guestmod.py`, `tools/guestmod/build_guest_mod.py` |
| SDK header | `runtime/guest/include/wwhd_guest.h` |
| tests | `tools/guestmod/test_guestmod.py` (needs a PowerPC clang: `WWHD_PPC_CLANG`, `WWHD_PPC_LLD`) |
| examples | `examples/guest-mods/heart-ticker` (entry + return hook of Link's per-step function, calls a game function; hearts tick down a quarter at a time to half and refill), `examples/guest-mods/addcalc-replace` (replaces `cLib_addCalc2` by an equivalent implementation; every other call goes to the game's original) |

```sh
python3 tools/recomp/recomp.py game/code/cking.rpx build/gen --mod-hooks
cmake --build build/cmake                                   # as usual
make -C examples/guest-mods CLANG=/opt/homebrew/opt/llvm/bin/clang LLD=/opt/homebrew/opt/lld/bin/ld.lld
python3 tools/guestmod/build_guest_mod.py examples/guest-mods/heart-ticker --out build/guestcache --base 0x7F000000
python3 tools/guestmod/build_guest_mod.py examples/guest-mods/addcalc-replace --out build/guestcache --base 0x7F100000
WWHD_GUEST_MODS=build/guestcache/<key>/heart-ticker.dylib,build/guestcache/<key>/addcalc-replace.dylib ./build/cmake/wwhd
```

Verified end to end on macOS arm64 (headless scripted run, copy of a save): both modules
load, the heart display changes by quarter hearts during gameplay, the replacement handles
half of the ≈ 600,000 `cLib_addCalc2` calls of the run with no visible difference, the mod's
call of a game function goes through the other mod's replacement, and the return hook sees
Link's actor pointer.

## Measurements

Machine: Apple M-series Mac (macOS 26.6), shared with other jobs (load average 9–25 during
the runs, so absolute numbers are noisy). devel = `cf6b8c9`; prototype = this branch with
`--mod-hooks` and **no mods loaded**.

| Metric | devel | prototype | Difference |
| --- | --- | --- | --- |
| translation (`recomp.py`) | 4.6 s | 4.6 s | none |
| game code compile, 4 jobs, load ≈ 10 | 312 CPU s, 82 s | 320 CPU s, 84 s | +2.5 % |
| same, two more runs each, load 15–25 | 547 / 563 CPU s | 570 / 536 CPU s | within noise |
| game code machine code (`__text` of the 80 objects) | 41.2 MB | 44.4 MB | +3.2 MB (+7.8 %), ≈ 80 bytes per function, nearly all in the cold path |
| game code data | 0.65 MB | 0.97 MB + 39 KB flags | +0.36 MB (`g_mod_bodies`, flags) |
| executable `__TEXT` | 44.4 MB | 47.6 MB | +3.2 MB |
| check per call of an unhooked function (arm64) | – | `adrp; add; ldrb; cbnz` | 4 instructions, branch not taken |
| guest function entries per logic step (Outset, walking) | 285,000–350,000 | | counted with a temporary probe |
| estimated cost per logic step | | ≈ 0.1 ms at ~1 cycle per check | ≤ 2–3 % of the ≈ 5.5 ms game-thread time per step, likely less |
| benchmark: `run_bench.py` outset, Vulkan, 30 fps uncapped, 40 s, 6 interleaved runs each: frame ms, median [min–max] | 6.54 [5.55–7.88] | 6.19 [5.56–7.31] | not measurable (spread ±15 %) |
| same: logic steps/s | 158 [131–183] | 162 [137–181] | |
| same: game thread busy ms per frame (frame − waits for the render thread) | 5.87 [5.40–7.67] | 6.02 [5.43–7.14] | |
| same: render thread CPU ms per frame | 5.02 [4.71–6.39] | 4.91 [4.45–5.89] | |
| install-time build of one example mod (translate + compile) | | 2 ms + 70–80 ms | cached afterwards |

The cost of the check is below what the benchmark can resolve on a shared machine; the
estimate from the call count is the upper bound to keep in mind. A quiet-machine A/B
(`run_bench.py` with `--runs 10`, nothing else running) is the check before a release.
Hooked functions cost one hash lookup plus the hook calls (`ppc_mod_run`); the example replacement took ≈ 600,000 calls in a three-minute run
without a visible effect.

Cheaper variants if needed: a thin wrapper per function (`f_X`: check, tail call to the
body; one extra branch per call but ~30 bytes per function), or no check in a list of hot
leaf functions (option (c) for those only).

## Open decisions

1. **Headers and symbols**: which of the options in [Headers for modders](#headers-for-modders-legal)
   (they decide how usable the SDK is).
2. **Hookable set**: all functions (recommended, measured cost below) or a list.
3. **Toolchain**: clang/lld (recommended; same family as the game toolchain on every
   platform) or also devkitPPC gcc; whether the SDK ships a pinned clang for modders.
4. **Trust wording**: same dialog as native mods, or a softer one for guest mods.
5. **Save states**: include the guest mod region in save states (needs the set of active mods
   in the state header) or forbid loading states across a different mod set.
6. **Runtime enable/disable**: restart-only (prototype) or live (needs a quiescent point and
   atomic chain updates).

## Road to a production version

| Work | Estimate |
| --- | --- |
| mod manager: `kind: guest`, base assignment, `build_guest_mod` step, loading enabled packages, trust fingerprint of `mod.elf`, errors in the UI | 3–4 days |
| setup: `--mod-hooks` by default, ship `wwhd_guest_abi.h` + translator in releases, Windows/Linux module flags (llvm-mingw DLL, zig `-shared`) and CI tests | 2–3 days |
| host services: options (all types), step length, mod heap, input, events, compiler helpers | 3–4 days |
| HUD service (Metal + Vulkan panels: text, rectangles, images) | 3–5 days |
| per-mod files, save-state integration of the mod region, live enable/disable | 3–4 days |
| SDK: headers per the legal decision, docs, templates, examples, a test mod suite in CI (translation of every clang-emitted instruction form) | 4–6 days |
| hardening: translator coverage (`ppc2c` on clang output), fuzzing the ELF reader, cross-mod exports/imports and dependency order | 3–4 days |

About 4–6 weeks for one developer, most of it in services, the manager and the SDK; the hooking
core in this prototype is close to final.
