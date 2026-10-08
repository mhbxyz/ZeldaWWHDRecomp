"""Translate verified public declarations into guest-call ABI declarations."""
import re

SCALARS = {'void', 'u8', 's8', 'u16', 's16', 'u32', 's32', 'f32', 'f64',
           'int', 'unsigned int', 'signed int', 'char', 'unsigned char', 'short', 'unsigned short', 'bool'}


def guest_type(kind):
    kind = re.sub(r'be<(\w+)>', r'\1', kind.strip())
    kind = re.sub(r'\bbool\b', 'u8', kind)
    kind = {'BOOL': 's32', 'cPhs_State': 's32', 'fpc_ProcID': 'u32', 'bool': 'u8', 'double': 'f64', 'float': 'f32'}.get(kind, kind)
    if '*' in kind:
        # Opaque object pointers preserve the PPC ABI without importing host C++ classes.
        base = kind.replace('*', '').replace('const', '').strip()
        if base not in SCALARS:
            return 'const void*' if 'const' in kind else 'void*'
        return kind
    return kind if kind in SCALARS else None


def bindings(index):
    lines = ['/* Generated public HD declarations, CC0-1.0; see public-wwhd-LICENSE.',
             ' * Revision: ' + index['revision'],
             ' * Object pointers are opaque; use the curated views for member access. */',
             '#pragma once', '#include "functions.h"', '#include "../wwhd_guest.h"', '']
    skipped = []
    used = set()
    names = {}
    for function in index['functions']:
        key = re.sub(r'[^A-Za-z0-9_]', '_', function['name'].lstrip('&'))
        names.setdefault(key, set()).add(function['address'])
    for function in index['functions']:
        ret = guest_type(function['return'])
        params = []
        for parameter in function['parameters'].split(','):
            parameter = parameter.strip()
            if not parameter or parameter == 'void':
                continue
            match = re.fullmatch(r'(.+?[\s*&])([A-Za-z_]\w*)', parameter)
            kind = guest_type(match[1]) if match else None
            if kind is None:
                ret = None
                break
            params.append(kind + ' ' + match[2])
        if ret is None:
            skipped.append(function)
            continue
        name = re.sub(r'[^A-Za-z0-9_]', '_', function['name'].lstrip('&'))
        short_name = name
        name += f"_{function['address']:08X}"
        if name in used:
            continue
        used.add(name)
        lines.append(f"WWHD_GAME_FUNC(0x{function['address']:08X}, {ret}, wwhd_{name}, ({', '.join(params) or 'void'}));")
        if len(names[short_name]) == 1:
            lines.append(f'#define wwhd_{short_name} wwhd_{name}')
    return '\n'.join(lines) + '\n', skipped


def save_view(root, revision):
    text = (root / 'wwhd_src/d/d_save.cpp').read_text()
    layout = re.search(r'max life (0), life (2), rupees (4)', text)
    pointer = re.search(r'save info is at \*\(([0-9A-Fa-f]{8})\) \+ (0x[0-9A-Fa-f]+)', text)
    if not layout or not pointer:
        raise ValueError('public save layout documentation changed; review required')
    return f'''/* Generated from public wwhd_src/d/d_save.cpp ({revision}); CC0-1.0.
 * Partial status prefix only; no full save-object size is claimed. */
#pragma once
#include "../wwhd_guest.h"
#define WWHD_ADDR_save_info_pointer 0x{pointer[1]}
#define WWHD_OFFSET_save_info {pointer[2]}
typedef struct dSv_player_status_a_view {{
    u16 max_life;
    u16 life;
    u16 rupees;
}} dSv_player_status_a_view;
#define dComIfGs_player_status_a (*(volatile dSv_player_status_a_view*)(WWHD_GAME_DATA(WWHD_ADDR_save_info_pointer, u32) + WWHD_OFFSET_save_info))
'''
