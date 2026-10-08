#!/usr/bin/env python3
"""Inventory SDK declarations from a clean, public HD decomp checkout.

Reads source as data; never imports or executes code from the input repository.
The inventory deliberately contains no function bodies or initialized game data.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

PUBLIC_URL = 'https://github.com/ZeldaWWHDDecomp/wwhd'
VERIFY = re.compile(r'\bVERIFY\(\s*(0x[0-9A-Fa-f]+)\s*,\s*(&?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\)')
DECL = re.compile(r'(?:^|\n)\s*(?:(?:static|inline|extern)\s+)*([\w:<>,*& \t]+?[ \t*&])([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*\{')
LAYOUT = re.compile(r'\bWWHD_(SIZE|OFFSET)\(\s*([^;\n]+?)\s*\)\s*;')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def inventory(root):
    root = root.resolve()
    remote = git(root, 'remote', 'get-url', 'origin').removesuffix('.git').rstrip('/')
    if remote != PUBLIC_URL:
        raise ValueError('input must be a fresh HTTPS clone of the public HD decomp')
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('public source checkout must be clean')
    source = root / 'wwhd_src'
    functions, layouts, unresolved = [], [], []
    for path in sorted(source.rglob('*')):
        if path.suffix not in ('.cpp', '.h'):
            continue
        text = path.read_text()
        relative = path.relative_to(root).as_posix()
        # Preserve positions while masking comments before scanning declarations.
        masked = re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text, flags=re.S)
        declarations = {}
        for match in DECL.finditer(masked):
            declarations.setdefault(match[2], []).append(match)
        for match in VERIFY.finditer(text):
            candidates = [d for d in declarations.get(match[2], []) if d.start() < match.start()]
            if not candidates:
                unresolved.append({'address': int(match[1], 16), 'name': match[2], 'source': relative})
                continue
            decl = candidates[-1]
            functions.append({'address': int(match[1], 16), 'name': match[2],
                              'return': ' '.join(decl[1].split()),
                              'parameters': ' '.join(decl[3].split()), 'source': relative})
        for match in LAYOUT.finditer(text):
            layouts.append({'kind': match[1].lower(), 'arguments': match[2], 'source': relative})
    functions.sort(key=lambda f: (f['address'], f['name'], f['source']))
    return {'public_source': PUBLIC_URL, 'revision': git(root, 'rev-parse', 'HEAD'),
            'functions': functions, 'layout_assertions': layouts, 'unresolved_declarations': unresolved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('public_clone', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inventory(args.public_clone)
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Indexed {len(result['functions'])} functions and {len(result['layout_assertions'])} layout assertions; {len(result['unresolved_declarations'])} declarations need resolution")


if __name__ == '__main__':
    main()
