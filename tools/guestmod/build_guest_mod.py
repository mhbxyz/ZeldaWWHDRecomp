#!/usr/bin/env python3
"""Install-time build of a guest mod (Mod SDK v2 prototype, docs/mod-sdk-v2.md).

usage: build_guest_mod.py PACKAGE_DIR --out CACHE_DIR [--base 0x7F000000] [--cc "xcrun clang"] [--json]

PACKAGE_DIR holds manifest.json (kind "guest") and the mod's PowerPC relocatable ELF. The mod is
translated to C (guestmod.py) and compiled by the local compiler into a module
CACHE_DIR/<key>/<id>.<dylib|so|dll>, where <key> covers everything the module depends on: the ELF,
the base address, the translator and module ABI versions, the compiler and its flags. A cached module
is reused; a port update that changes the translator or the ABI gives a new key and so a rebuild.
The game's code is not involved: modules call the game through the runtime's dispatch.

This is the step the mod manager's `build_guest_mod` setup step runs. With --json the last line of
stdout is {"ok": true, "module": PATH, "cached": bool, ...} or {"ok": false, "error": TEXT} for the
player (TEXT is short and readable; the full compiler output goes to CACHE_DIR/<key>/build.log).
"""
import argparse
import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guestmod  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
CFLAGS = ["-O2", "-ffp-contract=off", "-fno-strict-aliasing", "-w", "-fPIC", "-shared"]


def module_ext():
    s = platform.system()
    return ".dll" if s == "Windows" else ".dylib" if s == "Darwin" else ".so"


def default_cc():
    if os.environ.get("CC"):
        return shlex.split(os.environ["CC"])
    if platform.system() == "Darwin":
        return ["xcrun", "clang"]
    return ["clang"]


def abi_version(include):
    for line in open(os.path.join(include, "wwhd_guest_abi.h")):
        if line.startswith("#define WWHD_GUEST_ABI_VERSION"):
            return line.split()[2]
    raise SystemExit("wwhd_guest_abi.h without an ABI version")


def build(pkg, out, base, cc, include):
    man = json.load(open(os.path.join(pkg, "manifest.json")))
    if man.get("kind") != "guest":
        raise guestmod.ModError("not a guest mod package (kind %r)" % man.get("kind"))
    g = man.get("guest", {})
    if g.get("api_version") != 1:
        raise guestmod.ModError("the mod needs guest API %s; this game supports 1" % g.get("api_version"))
    elf_path = os.path.join(pkg, g.get("elf", "mod.elf"))
    elf = open(elf_path, "rb").read()
    ccver = subprocess.run(cc + ["--version"], capture_output=True, text=True).stdout.splitlines()[:1]
    h = hashlib.sha256()
    for part in (elf, b"%08X" % base, guestmod.TRANSLATOR_VERSION.encode(), abi_version(include).encode(),
                 json.dumps([cc, ccver, CFLAGS, module_ext()]).encode()):
        h.update(hashlib.sha256(part).digest())
    key = h.hexdigest()[:16]
    d = os.path.join(out, key)
    mod = os.path.join(d, man["id"] + module_ext())
    if os.path.isfile(mod):
        return {"ok": True, "module": mod, "cached": True, "key": key}
    os.makedirs(d, exist_ok=True)
    t0 = time.time()
    t = guestmod.Translator(guestmod.Elf(elf), base)
    src = os.path.join(d, "module.c")
    with open(src, "w") as f:
        f.write(t.emit(man["id"]))
    t1 = time.time()
    cmd = cc + CFLAGS + ["-I", include, src, "-o", mod + ".tmp"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    with open(os.path.join(d, "build.log"), "w") as f:
        f.write("$ %s\n%s%s" % (" ".join(cmd), p.stdout, p.stderr))
    if p.returncode != 0:
        raise guestmod.ModError("the local compiler could not build the mod (see %s)" % os.path.join(d, "build.log"))
    os.replace(mod + ".tmp", mod)
    return {"ok": True, "module": mod, "cached": False, "key": key, "translate_s": round(t1 - t0, 3),
            "compile_s": round(time.time() - t1, 3), "functions": len(t.entries), "hooks": len(t.hooks),
            "services": t.services}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=guestmod.REGION_START,
                    help="guest address of the mod (the mod manager assigns one per enabled mod)")
    ap.add_argument("--cc", help="compiler command (default: $CC, xcrun clang on macOS, clang)")
    ap.add_argument("--include", default=os.path.join(REPO, "runtime", "include"),
                    help="runtime headers (ppc.h, wwhd_guest_abi.h); sdk/include in a release")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        r = build(a.package, a.out, a.base, shlex.split(a.cc) if a.cc else default_cc(), a.include)
    except (guestmod.ModError, OSError, ValueError, KeyError) as e:
        r = {"ok": False, "error": str(e)}
    print(json.dumps(r) if a.json else ("built %s" % r["module"] if r["ok"] else "error: " + r["error"]))
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
