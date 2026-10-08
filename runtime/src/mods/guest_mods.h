// Mod SDK v2 runtime. Guest modules load only at startup, through the mod manager's trust flow.
#pragma once
#include <cstdint>
namespace guestmods {
void init(); // after dispatch::init, before guest threads start
void frame(uint64_t step); // logic-step clock exposed to guest mods
}
