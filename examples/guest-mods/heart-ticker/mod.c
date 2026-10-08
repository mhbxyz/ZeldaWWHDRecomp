/* Example guest mod: hooks Link's per-step function and lets his hearts tick down a quarter heart
 * every `every` logic steps, from full to half, then refills them (never below half: harmless).
 * Written for this example; the addresses are public facts used by the port's own runtime
 * (tools/recomp/hooks_mods.txt, runtime/src/mods/cheats.cpp). */
#include "wwhd_guest.h"

#define LINK_EXECUTE 0x0240EBB0     /* daPy_Execute: once per logic step while Link exists */
#define PLAYER_STATUS 0x145AC92C    /* live save data (dSv_player_status_a_c): u16 max life, u16 life */

/* a game function called from the mod: cLib_addCalc2(f32* value, f32 target, f32 scale, f32 max_step) */
WWHD_GAME_FUNC(0x0200ED84, void, cLib_addCalc2, (f32* value, f32 target, f32 scale, f32 max_step));

static u32 steps, returns;
static f32 smooth;

WWHD_HOOK(LINK_EXECUTE, on_link_execute, (void* link)) {
    int every = wwhd_config_int("every", 30);
    if (every < 1) every = 1;
    if (++steps % (u32)every) return;
    u16 max_life = WWHD_GAME_DATA(PLAYER_STATUS + 0, u16);
    u16 life = WWHD_GAME_DATA(PLAYER_STATUS + 2, u16);
    if (max_life < 12 || max_life > 80 || life > max_life) return;  /* no save data loaded */
    u16 next = life > max_life / 2 ? life - 1 : max_life;
    WWHD_GAME_DATA(PLAYER_STATUS + 2, u16) = next;
    cLib_addCalc2(&smooth, (f32)next, 0.5f, 2.0f);
    if (steps % (u32)(every * 4) == 0) {
        wwhd_log_int("heart-ticker: life (quarter hearts)", next);
        wwhd_log_float("heart-ticker: smoothed by the game's cLib_addCalc2", smooth);
    }
}

WWHD_HOOK_RETURN(LINK_EXECUTE, after_link_execute, (void* link)) {
    if (++returns == 1) wwhd_log_hex("heart-ticker: first return hook, Link at", (u32)link);
}
