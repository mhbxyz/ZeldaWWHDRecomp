// Exercise the actual hook runner with synthetic game bodies and a port wrapper.
#include "mods/guest_mods.cpp"
#include <cassert>
#include <vector>

static std::vector<int> calls;
static void body(Cpu* c) {
    PPC_MOD_HOOK(0, 0x02000000u);
    calls.push_back(3);
    c->r[3] += 1;
}
static void port(Cpu* c) {
    calls.push_back(1);
    c->r[3] *= 2; // stand-in for true-60 scaling before game code / replacements
    body(c);
    calls.push_back(6);
}
static void entry(Cpu* c) { calls.push_back(2); assert(c->r[3] == 10); c->r[3] = 999; }
static void replacement(Cpu* c) {
    calls.push_back(7); assert(c->r[3] == 10);
    guestmods::call_original(c, 0x02000000);
    assert(c->mod_skip == 0);
}
static void ret_a(Cpu* c) { calls.push_back(4); assert(c->r[3] == 10); c->r[3] = 888; }
static void ret_b(Cpu* c) { calls.push_back(5); assert(c->r[3] == 10); c->r[3] = 777; }
extern "C" {
extern const RecompEntry g_recomp_funcs[] = {{0x02000000, port}};
extern const unsigned g_recomp_func_count = 1;
extern const unsigned g_mod_hook_count = 1;
extern const PpcFunc g_mod_bodies[] = {body};
uint8_t g_mod_hook_flags[1]{};
volatile int g_core_preempt[3]{};
void ppc_dispatch(Cpu*) { std::abort(); }
void ppc_unimplemented(Cpu*, uint32_t, uint32_t) { std::abort(); }
void ppc_trap(Cpu*, uint32_t) { std::abort(); }
uint64_t ppc_timebase() { return 0; }
double ppc_fres(double x) { return x; }
double ppc_frsqrte(double x) { return x; }
void ppc_preempt(Cpu*) {}
}
namespace mem { std::string read_cstr(uint32_t) { return {}; } }
namespace dispatch { void set(uint32_t, PpcFunc) {} }
void log_msg(const char*, ...) {}
[[noreturn]] void fatal(const char*, ...) { std::abort(); }
int main() {
    Cpu c{};
    c.r[3] = 5; port(&c);
    assert((calls == std::vector<int>{1, 3, 6})); assert(c.r[3] == 11);
    auto& chain = guestmods::g_chains[0x02000000];
    chain.addr = 0x02000000; chain.ordinal = 0;
    chain.entry = {entry}; chain.ret = {ret_b, ret_a};
    g_mod_hook_flags[0] = 1;
    calls.clear(); c.r[3] = 5; port(&c);
    assert((calls == std::vector<int>{1, 2, 3, 5, 4, 6})); assert(c.r[3] == 11);
    chain.replace = replacement;
    calls.clear(); c.r[3] = 5; port(&c);
    assert((calls == std::vector<int>{1, 2, 7, 3, 5, 4, 6})); assert(c.r[3] == 11);
    // ORIGINAL bypasses both mods and the port wrapper, and consumes the skip token.
    calls.clear(); c.r[3] = 20; guestmods::call_original(&c, 0x02000000);
    assert((calls == std::vector<int>{3})); assert(c.r[3] == 21); assert(c.mod_skip == 0);
    std::puts("guest hook ordering and original passed");
}
