# -*- coding: utf-8 -*-
"""自实现 OLE2(CFB) 解析 + Word .doc 正文抽取（不依赖第三方包）。"""
import struct, sys, json, os

def read_ole_streams(path):
    data = open(path, 'rb').read()
    assert data[:8] == bytes.fromhex('d0cf11e0a1b11ae1'), 'not OLE2'
    sec_shift = struct.unpack_from('<H', data, 0x1E)[0]
    mini_shift = struct.unpack_from('<H', data, 0x20)[0]
    sec_size = 1 << sec_shift
    mini_size = 1 << mini_shift
    dir_start = struct.unpack_from('<I', data, 0x30)[0]
    mini_cutoff = struct.unpack_from('<I', data, 0x38)[0]
    mini_fat_start = struct.unpack_from('<I', data, 0x3C)[0]
    difat_start = struct.unpack_from('<I', data, 0x44)[0]

    def sec_off(sid):
        return (sid + 1) * sec_size

    difat = list(struct.unpack_from('<109I', data, 0x4C))
    nxt = difat_start
    guard = 0
    while nxt not in (0xFFFFFFFE, 0xFFFFFFFF) and guard < 100000:
        off = sec_off(nxt)
        ents = list(struct.unpack_from('<%dI' % (sec_size // 4), data, off))
        difat.extend(ents[:-1])
        nxt = ents[-1]
        guard += 1
    difat = [d for d in difat if d != 0xFFFFFFFF]

    fat = []
    for sid in difat:
        off = sec_off(sid)
        if off + sec_size > len(data):
            continue
        fat.extend(struct.unpack_from('<%dI' % (sec_size // 4), data, off))

    def chain(start):
        out, sid, g = [], start, 0
        while sid not in (0xFFFFFFFE, 0xFFFFFFFF) and sid < len(fat) and g < 200000:
            out.append(sid)
            sid = fat[sid]
            g += 1
        return out

    def read_chain(start, size=None):
        b = b''
        for sid in chain(start):
            off = sec_off(sid)
            b += data[off:off + sec_size]
        return b[:size] if size is not None else b

    dir_data = read_chain(dir_start)
    entries = []
    for i in range(0, len(dir_data), 128):
        e = dir_data[i:i + 128]
        if len(e) < 128:
            break
        nl = struct.unpack_from('<H', e, 0x40)[0]
        name = e[:max(0, nl - 2)].decode('utf-16-le', 'ignore') if nl > 2 else ''
        entries.append({
            'name': name, 'type': e[0x42],
            'start': struct.unpack_from('<I', e, 0x74)[0],
            'size': struct.unpack_from('<Q', e, 0x78)[0],
        })

    minifat = []
    for sid in chain(mini_fat_start):
        off = sec_off(sid)
        minifat.extend(struct.unpack_from('<%dI' % (sec_size // 4), data, off))

    root = entries[0]
    mini_stream = read_chain(root['start'])

    def read_mini(start, size):
        b, sid, g = b'', start, 0
        while sid not in (0xFFFFFFFE, 0xFFFFFFFF) and sid < len(minifat) and g < 200000:
            off = sid * mini_size
            b += mini_stream[off:off + mini_size]
            sid = minifat[sid]
            g += 1
        return b[:size]

    streams = {}
    for e in entries:
        if e['type'] == 2 and e['name']:
            try:
                if e['size'] < mini_cutoff:
                    streams[e['name']] = read_mini(e['start'], e['size'])
                else:
                    streams[e['name']] = read_chain(e['start'], e['size'])
            except Exception as ex:
                streams[e['name']] = b''
    return streams


def extract_doc_text(streams):
    wd = streams['WordDocument']
    flags = struct.unpack_from('<H', wd, 0x0A)[0]
    tbl_name = '1Table' if (flags & 0x0200) else '0Table'
    tbl = streams.get(tbl_name) or streams.get('1Table') or streams.get('0Table') or b''
    fcClx = struct.unpack_from('<I', wd, 0x01A2)[0]
    lcbClx = struct.unpack_from('<I', wd, 0x01A6)[0]
    clx = tbl[fcClx:fcClx + lcbClx]

    i, pcdt = 0, None
    while i < len(clx):
        t = clx[i]
        if t == 1:
            cb = struct.unpack_from('<h', clx, i + 1)[0]
            i += 3 + cb
        elif t == 2:
            lcb = struct.unpack_from('<I', clx, i + 1)[0]
            pcdt = clx[i + 5:i + 5 + lcb]
            break
        else:
            break

    if pcdt is None:
        # fallback: whole main text region as utf-16
        fcMin = struct.unpack_from('<I', wd, 0x18)[0]
        fcMac = struct.unpack_from('<I', wd, 0x1C)[0]
        return wd[fcMin:fcMac].decode('utf-16-le', 'ignore')

    n = (len(pcdt) - 4) // 12
    cps = struct.unpack_from('<%dI' % (n + 1), pcdt, 0)
    base = 4 * (n + 1)
    text = []
    for k in range(n):
        pcd = pcdt[base + 8 * k: base + 8 * k + 8]
        fc = struct.unpack_from('<I', pcd, 2)[0]
        clen = cps[k + 1] - cps[k]
        if fc & 0x40000000:
            fc2 = (fc & ~0x40000000) // 2
            text.append(wd[fc2:fc2 + clen].decode('cp1252', 'ignore'))
        else:
            text.append(wd[fc:fc + clen * 2].decode('utf-16-le', 'ignore'))
    return ''.join(text)


if __name__ == '__main__':
    p = sys.argv[1]
    streams = read_ole_streams(p)
    print('STREAMS:', [k for k in streams], file=sys.stderr)
    txt = extract_doc_text(streams)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        open(out, 'w', encoding='utf-8').write(txt)
        print('written', out, 'chars=', len(txt))
    else:
        sys.stdout.write(txt)
