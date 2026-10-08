// Guest mods (Mod SDK v2 prototype): see guest_mods.cpp and docs/mod-sdk-v2.md.
#pragma once

namespace guestmods {
// loads the modules named in WWHD_GUEST_MODS; call after dispatch::init, before guest code runs
void init();
}  // namespace guestmods
