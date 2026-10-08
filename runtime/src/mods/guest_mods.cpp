// Guest mods (Mod SDK v2 prototype, docs/mod-sdk-v2.md): PowerPC mods translated to C on install and
// compiled into a module by the player's own compiler (tools/guestmod/). They hook or replace game
// functions at runtime through the per-function flag check that recomp.py --mod-hooks puts at the
// start of every game function body (PPC_MOD_HOOK in ppc.h).
//
// Prototype switch: WWHD_GUEST_MODS=<module>[,<module>...] loads translated modules at start, before
// any guest code runs. Without it (or with game code built without --mod-hooks) nothing changes.
#include "guest_mods.h"
#include "guest_validation.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

#include "recomp_table.h"
#include "runtime.h"
#include "wwhd_guest_abi.h"

extern "C" {
extern const unsigned g_mod_hook_count;  // 0: game code built without --mod-hooks
extern const PpcFunc g_mod_bodies[];
extern volatile int g_core_preempt[3];
double ppc_fres(double);
double ppc_frsqrte(double);
}

// Cpu::mod_skip uses former padding: save states (which store sizeof(Cpu) bytes) stay compatible
static_assert(sizeof(void*) != 8 || sizeof(Cpu) == 752, "Cpu layout changed");

namespace guestmods {
namespace {

struct Chain {
    uint32_t addr = 0, ordinal = 0;
    PpcFunc replace = nullptr;
    std::string replace_mod;
    std::vector<PpcFunc> entry, ret;
};
std::unordered_map<uint32_t, Chain> g_chains;  // built before the game starts, read-only afterwards
struct Loaded { std::string path; const WWHDGuestModuleV1* m; };
std::vector<Loaded> g_loaded;

int ordinal_of(uint32_t addr) {
    const RecompEntry* b = g_recomp_funcs;
    const RecompEntry* e = g_recomp_funcs + g_recomp_func_count;
    const RecompEntry* it = std::lower_bound(b, e, addr, [](const RecompEntry& r, uint32_t a) { return r.addr < a; });
    return it != e && it->addr == addr ? (int)(it - b) : -1;
}

void call_original(Cpu* c, uint32_t func) {
    int i = ordinal_of(func);
    if (i < 0) fatal("[guestmods] call_original: %08X is not a game function", func);
    if (g_mod_hook_flags[i]) c->mod_skip = func;  // consumed by the check at the start of the body
    g_mod_bodies[i](c);
}

// ---- host services (imports of guest mods by name; arguments in r3..r10 / f1..f8, result in r3 / f1)
std::string cstr(uint32_t a) { return a ? mem::read_cstr(a) : std::string("(null)"); }
void svc_log(Cpu* c) { LOG("[guestmod] %s", cstr(c->r[3]).c_str()); }
void svc_log_int(Cpu* c) { LOG("[guestmod] %s %d", cstr(c->r[3]).c_str(), (int32_t)c->r[4]); }
void svc_log_hex(Cpu* c) { LOG("[guestmod] %s %08X", cstr(c->r[3]).c_str(), c->r[4]); }
void svc_log_float(Cpu* c) { LOG("[guestmod] %s %g", cstr(c->r[3]).c_str(), c->f[1].ps0); }
void svc_memcpy(Cpu* c) { memmove(mem::ptr(c->r[3]), mem::ptr(c->r[4]), c->r[5]); }  // r3 (dst) stays the result
void svc_memset(Cpu* c) { memset(mem::ptr(c->r[3]), (int)(c->r[4] & 0xFF), c->r[5]); }
// prototype options: WWHD_GUEST_OPT_<id>=<integer> (production: the mod manager's typed options)
void svc_config_int(Cpu* c) {
    std::string id = "WWHD_GUEST_OPT_" + cstr(c->r[3]);
    const char* v = getenv(id.c_str());
    c->r[3] = v ? (uint32_t)strtol(v, nullptr, 0) : c->r[4];  // r4: default
}
const std::unordered_map<std::string, PpcFunc> kServices = {
    {"wwhd_log", svc_log},       {"wwhd_log_int", svc_log_int}, {"wwhd_log_hex", svc_log_hex},
    {"wwhd_log_float", svc_log_float}, {"wwhd_config_int", svc_config_int},
    {"memcpy", svc_memcpy},      {"memmove", svc_memcpy},       {"memset", svc_memset},
};
PpcFunc service(const char* name) {
    auto it = kServices.find(name);
    return it == kServices.end() ? nullptr : it->second;
}

const WWHDGuestHostV1 kHost = {
    sizeof(WWHDGuestHostV1), WWHD_GUEST_ABI_VERSION,
    ppc_dispatch, ppc_unimplemented, ppc_trap, ppc_timebase, ppc_fres, ppc_frsqrte, ppc_preempt,
    g_core_preempt, call_original, service,
};

bool load_one(const std::string& path, std::string& err) {
#ifdef _WIN32
    void* lib = (void*)LoadLibraryA(path.c_str());
    auto init = lib ? (WWHDGuestInitV1)(void*)GetProcAddress((HMODULE)lib, WWHD_GUEST_INIT_SYMBOL) : nullptr;
#else
    void* lib = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    auto init = lib ? (WWHDGuestInitV1)dlsym(lib, WWHD_GUEST_INIT_SYMBOL) : nullptr;
#endif
    if (!lib) { err = "cannot load the module"; return false; }
    struct LibraryGuard {
        void* handle;
        ~LibraryGuard() {
            if (!handle) return;
#ifdef _WIN32
            FreeLibrary((HMODULE)handle);
#else
            dlclose(handle);
#endif
        }
    } guard{lib};
    if (!init) { err = "not a guest mod module (no " WWHD_GUEST_INIT_SYMBOL ")"; return false; }
    const WWHDGuestModuleV1* m = init(&kHost);
    if (!m || m->size < sizeof(WWHDGuestModuleV1) || m->abi_version != WWHD_GUEST_ABI_VERSION) {
        err = "module ABI does not match this game version: rebuild the mod";
        return false;
    }
    if (!validate_module(*m, path,
            [](uint32_t addr) { return ordinal_of(addr) >= 0; },
            [](uint32_t addr) {
                auto it = g_chains.find(addr);
                return it == g_chains.end() ? std::string() : it->second.replace_mod;
            }, err)) return false;
    for (auto& o : g_loaded)
        if (m->mem_base < o.m->mem_base + o.m->mem_size && o.m->mem_base < m->mem_base + m->mem_size) {
            err = "module memory overlaps " + o.path;
            return false;
        }
    memset(mem::ptr(m->mem_base), 0, m->mem_size);
    if (m->image_size) memcpy(mem::ptr(m->mem_base), m->image, m->image_size);
    for (uint32_t i = 0; i < m->func_count; i++) dispatch::set(m->funcs[i].addr, m->funcs[i].fn);
    for (uint32_t i = 0; i < m->hook_count; i++) {
        const WWHDGuestHook& h = m->hooks[i];
        Chain& ch = g_chains[h.target];
        ch.addr = h.target;
        ch.ordinal = (uint32_t)ordinal_of(h.target);
        if (h.kind == WWHD_GUEST_REPLACE) { ch.replace = h.fn; ch.replace_mod = path; }
        else if (h.kind == WWHD_GUEST_HOOK_ENTRY) ch.entry.push_back(h.fn);
        else ch.ret.insert(ch.ret.begin(), h.fn);  // return hooks run in reverse load order
        g_mod_hook_flags[ch.ordinal] = 1;
        LOG("[guestmods] %s %08X", h.kind == WWHD_GUEST_REPLACE ? "replace" : h.kind == WWHD_GUEST_HOOK_ENTRY ? "entry hook" : "return hook",
            h.target);
    }
    g_loaded.push_back({path, m});
    guard.handle = nullptr; // module functions remain resident for the process lifetime
    LOG("[guestmods] loaded %s (translator %s): %u functions, %u hooks, guest memory %08X-%08X", path.c_str(),
        m->translator, m->func_count, m->hook_count, m->mem_base, m->mem_base + m->mem_size);
    return true;
}

struct Args {
    uint32_t r[8];
    double f[8][2];
    void save(const Cpu* c) {
        for (int i = 0; i < 8; i++) { r[i] = c->r[3 + i]; f[i][0] = c->f[1 + i].ps0; f[i][1] = c->f[1 + i].ps1; }
    }
    void load(Cpu* c) const {
        for (int i = 0; i < 8; i++) { c->r[3 + i] = r[i]; c->f[1 + i].ps0 = f[i][0]; c->f[1 + i].ps1 = f[i][1]; }
    }
};

}  // namespace

void init() {
    const char* list = getenv("WWHD_GUEST_MODS");
    if (!list || !*list) return;
    if (g_mod_hook_count == 0) {
        LOG("[guestmods] WWHD_GUEST_MODS ignored: the game code was built without --mod-hooks");
        return;
    }
    std::string s = list;
    size_t p = 0;
    while (p <= s.size()) {
        size_t q = s.find(',', p);
        if (q == std::string::npos) q = s.size();
        std::string path = s.substr(p, q - p);
        std::string err;
        if (!path.empty() && !load_one(path, err)) LOG("[guestmods] %s not loaded: %s", path.c_str(), err.c_str());
        p = q + 1;
    }
}

}  // namespace guestmods

using namespace guestmods;

// A hooked or replaced game function. The calling convention is the game's: hooks get the function's
// arguments (r3..r10, f1..f8 are restored for every hook), a return hook also leaves the return value
// (r3, r4, f1) as the function produced it. r1/r2/r13 are preserved by every callee (ABI).
extern "C" void ppc_mod_run(Cpu* c) {
    uint32_t addr = c->pc;
    auto it = g_chains.find(addr);
    if (it == g_chains.end()) fatal("[guestmods] %08X flagged without hooks", addr);
    const Chain& ch = it->second;
    Args a;
    a.save(c);
    for (PpcFunc h : ch.entry) {
        h(c);
        a.load(c);
    }
    if (ch.replace) ch.replace(c);
    else { c->mod_skip = addr; g_mod_bodies[ch.ordinal](c); }
    if (!ch.ret.empty()) {
        uint32_t r3 = c->r[3], r4 = c->r[4];
        double f1a = c->f[1].ps0, f1b = c->f[1].ps1;
        for (PpcFunc h : ch.ret) {
            a.load(c);
            h(c);
        }
        c->r[3] = r3; c->r[4] = r4; c->f[1].ps0 = f1a; c->f[1].ps1 = f1b;
    }
}
