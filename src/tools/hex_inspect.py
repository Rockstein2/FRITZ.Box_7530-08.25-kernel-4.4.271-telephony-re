#!/usr/bin/env python3
import sys
from pathlib import Path

def parse(path):
    mem = {}
    upper = 0
    types = {}
    bad = 0
    for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(':'):
            print(f'{path}:{lineno}: not a record: {line!r}'); bad += 1; continue
        raw = bytes.fromhex(line[1:])
        if len(raw) < 5:
            print(f'{path}:{lineno}: short record'); bad += 1; continue
        n, addr, typ = raw[0], (raw[1] << 8) | raw[2], raw[3]
        data, check = raw[4:4+n], raw[4+n]
        if (sum(raw[:-1]) + check) & 0xff:
            print(f'{path}:{lineno}: bad checksum'); bad += 1
        types[typ] = types.get(typ, 0) + 1
        if typ == 0:
            base = upper + addr
            for i, b in enumerate(data):
                mem[base+i] = b
        elif typ == 1:
            break
        elif typ == 2:
            upper = ((data[0] << 8) | data[1]) << 4
        elif typ == 4:
            upper = ((data[0] << 8) | data[1]) << 16
        else:
            print(f'{path}:{lineno}: unsupported type {typ}')
    return mem, types, bad

for path in sys.argv[1:]:
    mem, types, bad = parse(path)
    addrs = sorted(mem)
    blocks = []
    if addrs:
        s = p = addrs[0]
        for a in addrs[1:]:
            if a != p+1:
                blocks.append((s, p-s+1)); s = a
            p = a
        blocks.append((s, p-s+1))
    print(f'\n=== {path} ===')
    print('record types:', {hex(k): v for k,v in sorted(types.items())}, 'bad:', bad)
    print('data bytes:', len(mem), 'min:', hex(min(addrs)) if addrs else None, 'max:', hex(max(addrs)) if addrs else None)
    print('blocks:', len(blocks))
    for a, n in blocks[:20]:
        print(f'  addr=0x{a:08x} len={n} (0x{n:x})')
    # Predict ihex2bin payload: blocks with BE32 addr + BE32 len + data.
    payload = b''.join(int(a).to_bytes(4,'big') + int(n).to_bytes(4,'big') + bytes(mem[x] for x in range(a,a+n)) for a,n in blocks)
    print('payload bytes (block headers included):', len(payload), f'0x{len(payload):x}')
    print('payload first 32:', payload[:32].hex())
    # outer framing: mode 0 => u16 BE length, mode 1 => u32 BE length, then payload, then XOR checksum
    for mode, hdrlen in [('mode0',2),('mode1',4)]:
        total = hdrlen + len(payload) + 1
        print(f'  {mode}: header={len(payload).to_bytes(hdrlen,"big").hex()} total={total}')
    # first TLV-like bytes after block header
    if blocks:
        a,n = blocks[0]
        data = bytes(mem[x] for x in range(a,a+n))
        print('first block data first 32:', data[:32].hex())
