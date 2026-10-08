# Example guest mods (Mod SDK v2 prototype)

Two small mods written in C and compiled for the game's CPU (32-bit big-endian PowerPC). See
[docs/mod-sdk-v2.md](../../docs/mod-sdk-v2.md) for the design. They contain no game code or data:
game functions and variables are referenced by address only.

| Mod | What it shows |
| --- | --- |
| `heart-ticker` | entry and return hooks on Link's per-step function (`0240EBB0`), a call of a game function (`cLib_addCalc2`), an option (`every`). Link's hearts tick down a quarter heart every `every` logic steps to half, then refill. |
| `addcalc-replace` | a full replacement of a small game function (`cLib_addCalc2`, `0200ED84`) with an equivalent implementation; every other call goes to the game's own code (`WWHD_GAME_ORIGINAL`). No visible change; the log counts the calls. |

Build (needs clang with the PowerPC target and ld.lld; on macOS `brew install llvm lld`):

```sh
make CLANG=/opt/homebrew/opt/llvm/bin/clang LLD=/opt/homebrew/opt/lld/bin/ld.lld
```

Each folder is then a package (`manifest.json` + `mod.elf`). Install-time build and a test run
with game code translated with `--mod-hooks`:

```sh
python3 tools/guestmod/build_guest_mod.py examples/guest-mods/heart-ticker --out build/guestcache --base 0x7F000000
python3 tools/guestmod/build_guest_mod.py examples/guest-mods/addcalc-replace --out build/guestcache --base 0x7F100000
WWHD_GUEST_MODS=<module 1>,<module 2> WWHD_GUEST_OPT_every=15 ./build/cmake/wwhd
```
