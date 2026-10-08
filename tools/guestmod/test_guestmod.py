#!/usr/bin/env python3
"""Tests of the guest mod translator (Mod SDK v2 prototype).

Builds the example mods with a PowerPC-capable clang (WWHD_PPC_CLANG / WWHD_PPC_LLD, or clang and
ld.lld on PATH; skipped without one), translates them and compiles the modules with the host
compiler. No game files are needed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import guestmod  # noqa: E402

CLANG = os.environ.get("WWHD_PPC_CLANG") or shutil.which("clang")
LLD = os.environ.get("WWHD_PPC_LLD") or shutil.which("ld.lld")
FLAGS = ["--target=powerpc-unknown-eabi", "-mcpu=750", "-O2", "-ffreestanding", "-fno-builtin", "-nostdlib",
         "-fno-jump-tables", "-ffunction-sections", "-fdata-sections",
         "-I", os.path.join(REPO, "runtime", "guest", "include")]


def ppc_ok():
    if not CLANG or not LLD:
        return False
    p = subprocess.run([CLANG, "--target=powerpc-unknown-eabi", "-x", "c", "-c", "-o", os.devnull, "-"],
                       input="int x;", capture_output=True, text=True)
    return p.returncode == 0


@unittest.skipUnless(ppc_ok(), "no clang with the PowerPC target / ld.lld")
class GuestModTest(unittest.TestCase):
    def build_elf(self, src_text, d):
        src = os.path.join(d, "mod.c")
        with open(src, "w") as f:
            f.write(src_text)
        subprocess.run([CLANG] + FLAGS + ["-c", src, "-o", os.path.join(d, "mod.o")], check=True)
        subprocess.run([LLD, "-r", os.path.join(d, "mod.o"), "-o", os.path.join(d, "mod.elf")], check=True)
        return os.path.join(d, "mod.elf")

    def test_examples_build(self):
        for mod in ("heart-ticker", "addcalc-replace"):
            with tempfile.TemporaryDirectory() as d:
                pkg = os.path.join(d, "pkg")
                os.makedirs(pkg)
                shutil.copy(os.path.join(REPO, "examples", "guest-mods", mod, "manifest.json"), pkg)
                with open(os.path.join(REPO, "examples", "guest-mods", mod, "mod.c")) as f:
                    self.build_elf(f.read(), pkg)
                out = subprocess.run([sys.executable, os.path.join(HERE, "build_guest_mod.py"), pkg, "--out",
                                      os.path.join(d, "cache"), "--json"], capture_output=True, text=True)
                r = json.loads(out.stdout.strip().splitlines()[-1])
                self.assertTrue(r["ok"], r)
                self.assertTrue(os.path.isfile(r["module"]))
                again = subprocess.run([sys.executable, os.path.join(HERE, "build_guest_mod.py"), pkg, "--out",
                                        os.path.join(d, "cache"), "--json"], capture_output=True, text=True)
                self.assertTrue(json.loads(again.stdout.strip().splitlines()[-1])["cached"])

    def test_relocations_and_imports(self):
        src = r'''
#include "wwhd_guest.h"
WWHD_GAME_FUNC(0x02001234, int, game_fn, (int));
WWHD_GAME_ORIGINAL(0x02005678, void, orig_fn, (void));
static int table[4] = {1, 2, 3, 4};
int (*volatile ptr)(int) = 0;
__attribute__((noinline)) static int helper(int x) { return table[x & 3] + game_fn(x); }
WWHD_REPLACE(0x02005678, void, repl, (void)) { ptr = helper; orig_fn(); wwhd_log_int("v", ptr(2)); }
'''
        with tempfile.TemporaryDirectory() as d:
            t = guestmod.Translator(guestmod.Elf(open(self.build_elf(src, d), "rb").read()), 0x7F200000)
            c = t.emit("test")
            self.assertEqual([(k, tg) for k, tg, _, _ in t.hooks], [(1, 0x02005678)])
            self.assertIn("c->pc = 0x02001234u; ppc_dispatch(c);", c)
            self.assertIn("g_host->call_original(c, 0x02005678u);", c)
            self.assertEqual(t.services, ["wwhd_log_int"])
            self.assertTrue(all(0x7F200000 <= e < t.end for e in t.entries))
            self.assertGreaterEqual(len(t.entries), 2)  # helper is address-taken: its own function

    def test_errors(self):
        with self.assertRaises(guestmod.ModError):
            guestmod.Elf(b"not an elf at all" * 4)


if __name__ == "__main__":
    unittest.main()
