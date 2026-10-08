#include "mods/guest_build.h"
#include <cassert>
#include <chrono>
#include <iostream>
using mods::json::Value;
int main(int argc,char** argv) {
    if(argc>1&&std::string(argv[1])=="--builder") {
        assert(argc>=7);
        std::string package=argv[3];
        if(package=="failure"){std::cout<<"compiler diagnostics\n{\"ok\":false,\"error\":\"compile failed\"}\n";return 1;}
        if(package=="bad-json"){std::cout<<"not JSON\n";return 0;}
        assert(package=="package with spaces & % and $()");
        bool inspect=false,cc=false;
        for(int i=4;i<argc;++i){
            if(std::string(argv[i])=="--inspect")inspect=true;
            if(std::string(argv[i])=="--cc-json"){
                assert(i+1<argc);auto args=mods::json::parse(argv[++i]);
                assert(args.array.size()==3&&args.array[0].text=="compiler with spaces"&&args.array[2].text=="quoted \\\"arg");cc=true;
            }
        }
        assert(inspect!=cc);
        std::cout<<"diagnostic line\n{\"ok\":true,\"allocation_size\":65536,\"module\":\"module path\"}\n";
        return 0;
    }
    guestmods::BuildBridge b;
    b.python={std::filesystem::absolute(argv[0]).string(),"--builder"};
    b.compiler={"compiler with spaces","-target","quoted \\\"arg"};
    b.builder="builder with spaces";b.include="headers with spaces";b.cache="cache with spaces";
    assert(b.run("package with spaces & % and $()",0x7F000000,true).get("allocation_size").number==65536);
    assert(b.run("package with spaces & % and $()",0x7F000000,false).get("module").text=="module path");
    bool failed=false;
    try{b.run("failure",0x7F000000,false);}catch(const std::exception& e){failed=std::string(e.what())=="compile failed";}
    assert(failed);failed=false;
    try{b.run("bad-json",0x7F000000,false);}catch(const std::exception&){failed=true;}
    assert(failed);
    std::cout<<"guest build argument/result bridge passed\n";
}
