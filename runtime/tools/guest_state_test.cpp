// Full-state mod memory and identity metadata, entirely synthetic and never written to disk.
#include "mods/guest_mods.h"
#include "mods/guest_heap.h"
#include "mods/guest_state_section.h"
#include "state_memory.h"
#include <cassert>
#include <iostream>
int main() {
    std::vector<guestmods::ModIdentity> saved={{"a","1.0.0"},{"b","2.0.0"}},read;
    ss::Writer identities;guestmods::save_mod_set(identities,saved);
    assert(guestmods::read_mod_set(ss::Reader(identities.b.data(),identities.b.size()),read));
    assert(!guestmods::different_mods(saved,read));
    std::reverse(read.begin(),read.end());assert(!guestmods::different_mods(saved,read));
    read[0].version="3.0.0";assert(guestmods::different_mods(saved,read));
    read.clear();assert(guestmods::read_mod_set(ss::Reader(nullptr,0),read));
    assert(guestmods::different_mods(saved,read));
    assert(!guestmods::read_mod_set(ss::Reader(identities.b.data(),identities.b.size()-1),read));
    std::vector<uint8_t> memory(guestmods::kRegionSize);
    auto pointer=[&](uint32_t a){assert(a>=guestmods::kRegionStart&&a<guestmods::kRegionStart+memory.size());return memory.data()+a-guestmods::kRegionStart;};
    auto touched=[](const uint8_t*,size_t){return true;};
    guestmods::Heap heap(memory.data()+0x10000,guestmods::kRegionStart+0x10000,0x10000);heap.initialize();
    auto allocation=heap.allocate(64);assert(allocation);pointer(allocation)[0]=123;memory[0]=42; // code/data sentinel
    std::vector<ss::MemoryRegion> regions={{guestmods::kRegionStart,guestmods::kRegionSize}};
    ss::Writer snapshot;ss::capture_regions(snapshot,regions,pointer,touched);
    ss::Reader reader(snapshot.b.data(),snapshot.b.size());ss::MemoryChunks chunks;std::vector<ss::MemoryRegion> parsed;
    assert(ss::read_regions(reader,parsed,chunks)&&parsed.size()==1&&chunks.size()==2);
    assert(heap.release(allocation));memory[0]=0;memory[0x30000]=99;
    ss::restore_regions(parsed,chunks,pointer,touched);
    assert(memory[0]==42&&pointer(allocation)[0]==123&&memory[0x30000]==0);
    assert(heap.release(allocation)); // allocator state restored with guest memory
    auto malformed=snapshot.b;uint32_t invalid_index=guestmods::kRegionSize/ss::kMemoryChunk;
    memcpy(malformed.data()+16,&invalid_index,4);ss::Reader bad(malformed.data(),malformed.size());
    parsed.clear();chunks.clear();assert(!ss::read_regions(bad,parsed,chunks));
    std::cout<<"guest state region and mismatch metadata passed\n";
}
