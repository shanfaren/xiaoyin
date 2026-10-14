# -*- coding: utf-8 -*-
"""自实现 QR Code 编码器（纯标准库）+ 往返解码校验器。

为什么自实现：本机 pip 不可用（网络受限），无法安装 `qrcode` 等库；
为保证二维码真实可用，这里按 ISO/IEC 18004 标准实现
字节模式（Byte mode）、纠错等级 M、版本 1—10，并**自带解码校验器**用于验证。

校验方式（见 verify()）：
1. 读取矩阵中两份格式信息 → 去掩码 → BCH(15,5) 校验；
2. 按标准顺序读回数据位 → 反交织 → 还原码字；
3. 对每个 RS 块做**伴随式（syndrome）校验**，全部为 0 才算通过；
4. 解析模式指示符 / 字符计数 / 数据字节 → 与原文逐字节比对。

说明：该往返校验为**自实现编码器的自洽性验证**（含 RS 伴随式与 BCH 格式信息校验），
不等于第三方扫码器验证；最终仍需用手机实测扫码确认。
"""

# ---------------- GF(256) ----------------
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n):
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= _gf_mul(c, _EXP[i])
        g = ng
    return g


def _rs_encode(data, ec_len):
    g = _rs_generator(ec_len)
    res = [0] * ec_len
    for d in data:
        factor = d ^ res[0]
        res = res[1:] + [0]
        if factor:
            for i in range(ec_len):
                res[i] ^= _gf_mul(g[i + 1], factor)
    return res


# ---------------- 版本 / 纠错表（字节模式，纠错等级 M） ----------------
# (version): (total_codewords, ec_per_block, [(blocks, data_cw_per_block), ...])
VERSION_TABLE_M = {
    1:  (26,  10, [(1, 16)]),
    2:  (44,  16, [(1, 28)]),
    3:  (70,  26, [(1, 44)]),
    4:  (100, 18, [(2, 32)]),
    5:  (134, 24, [(2, 43)]),
    6:  (172, 16, [(4, 27)]),
    7:  (196, 18, [(4, 31)]),
    8:  (242, 22, [(2, 38), (2, 39)]),
    9:  (292, 22, [(3, 36), (2, 37)]),
    10: (346, 26, [(4, 43), (1, 44)]),
}

ALIGN_CENTERS = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}

VERSION_INFO = {
    7:  0b000111110010010100,
    8:  0b001000010110111100,
    9:  0b001001101010011001,
    10: 0b001010010011010011,
}

# 纠错等级指示位（M = 0b00）
EC_BITS = {'L': 0b01, 'M': 0b00, 'Q': 0b11, 'H': 0b10}

MASK_FUNCS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _bch15_5(data5):
    d = data5 << 10
    g = 0x537
    for i in range(4, -1, -1):
        if d & (1 << (i + 10)):
            d ^= g << i
    return (data5 << 10) | d


def _format_bits(ec_level, mask):
    return _bch15_5((EC_BITS[ec_level] << 3) | mask) ^ 0x5412


def _data_capacity(version):
    total, ec, groups = VERSION_TABLE_M[version]
    data_cw = sum(b * d for b, d in groups)
    cc_bits = 8 if version <= 9 else 16
    return (data_cw * 8 - 4 - cc_bits) // 8, data_cw, ec, groups


def choose_version(byte_len):
    for v in range(1, 11):
        cap, _, _, _ = _data_capacity(v)
        if byte_len <= cap:
            return v
    raise ValueError(f'内容过长（{byte_len} 字节），本实现支持版本 1—10（最大约 213 字节）。')


# ---------------- 位缓冲 ----------------
class _BitBuf:
    def __init__(self):
        self.bits = []

    def put(self, val, length):
        for i in range(length - 1, -1, -1):
            self.bits.append((val >> i) & 1)

    def __len__(self):
        return len(self.bits)


# ---------------- 编码 ----------------
def _encode_codewords(text_bytes, version, ec_level='M'):
    data_cap, data_cw, ec_len, groups = _data_capacity(version)
    buf = _BitBuf()
    buf.put(0b0100, 4)                      # 字节模式
    buf.put(len(text_bytes), 8 if version <= 9 else 16)
    for b in text_bytes:
        buf.put(b, 8)
    # 终止符
    for _ in range(min(4, data_cw * 8 - len(buf))):
        buf.put(0, 1)
    # 补齐到字节
    while len(buf) % 8 != 0:
        buf.put(0, 1)
    # 填充字节
    pads = [0xEC, 0x11]
    i = 0
    while len(buf) < data_cw * 8:
        buf.put(pads[i % 2], 8)
        i += 1

    codewords = [int(''.join(str(b) for b in buf.bits[i:i + 8]), 2) for i in range(0, len(buf.bits), 8)]
    codewords = codewords[:data_cw]

    # 分块 + RS
    blocks = []
    idx = 0
    for count, dlen in groups:
        for _ in range(count):
            d = codewords[idx:idx + dlen]
            idx += dlen
            blocks.append((d, _rs_encode(d, ec_len)))

    # 交织
    out = []
    max_d = max(len(d) for d, _ in blocks)
    for i in range(max_d):
        for d, _ in blocks:
            if i < len(d):
                out.append(d[i])
    for i in range(ec_len):
        for _, e in blocks:
            out.append(e[i])
    return out


# ---------------- 矩阵构建 ----------------
def _make_matrix(version):
    size = 17 + 4 * version
    m = [[None] * size for _ in range(size)]
    res = [[False] * size for _ in range(size)]

    def setf(r, c, v):
        m[r][c] = v
        res[r][c] = True

    # 定位图案 + 分隔符
    for (r0, c0) in [(0, 0), (0, size - 7), (size - 7, 0)]:
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < size and 0 <= cc < size:
                    inside = 0 <= r <= 6 and 0 <= c <= 6
                    border = r in (0, 6) or c in (0, 6)
                    core = 2 <= r <= 4 and 2 <= c <= 4
                    setf(rr, cc, 1 if (inside and (border or core)) else 0)

    # 定时图案
    for i in range(8, size - 8):
        setf(6, i, 1 if i % 2 == 0 else 0)
        setf(i, 6, 1 if i % 2 == 0 else 0)

    # 校正图案
    centers = ALIGN_CENTERS[version]
    for r0 in centers:
        for c0 in centers:
            if (r0 <= 8 and c0 <= 8) or (r0 <= 8 and c0 >= size - 9) or (r0 >= size - 9 and c0 <= 8):
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    setf(r0 + r, c0 + c, 1 if (max(abs(r), abs(c)) != 1) else 0)

    # 固定暗模块
    setf(size - 8, 8, 1)

    # 预留格式信息区
    for i in range(9):
        if m[8][i] is None:
            setf(8, i, 0)
        if m[i][8] is None:
            setf(i, 8, 0)
    for i in range(8):
        if m[8][size - 1 - i] is None:
            setf(8, size - 1 - i, 0)
        if m[size - 1 - i][8] is None:
            setf(size - 1 - i, 8, 0)

    # 版本信息（v>=7）
    if version >= 7:
        vi = VERSION_INFO[version]
        for i in range(18):
            bit = (vi >> i) & 1
            r, c = i // 3, i % 3
            setf(size - 11 + c, r, bit)
            setf(r, size - 11 + c, bit)

    return m, res


def _place_data(m, res, codewords):
    size = len(m)
    bits = []
    for cw in codewords:
        for i in range(7, -1, -1):
            bits.append((cw >> i) & 1)
    idx = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (col, col - 1):
                if not res[r][c]:
                    m[r][c] = bits[idx] if idx < len(bits) else 0
                    idx += 1
        col -= 2
        upward = not upward
    return idx


def _apply_mask(m, res, mask_id):
    size = len(m)
    f = MASK_FUNCS[mask_id]
    out = [row[:] for row in m]
    for r in range(size):
        for c in range(size):
            if not res[r][c] and f(r, c):
                out[r][c] ^= 1
    return out


def _place_format(m, ec_level, mask_id):
    """按 ISO/IEC 18004 标准摆放 15 位格式信息（bit0 为 LSB，先摆低位）。"""
    size = len(m)
    bits = _format_bits(ec_level, mask_id)
    # 副本1：竖直（第 8 列）
    for i in range(15):
        b = (bits >> i) & 1
        if i < 6:
            m[i][8] = b
        elif i < 8:
            m[i + 1][8] = b
        else:
            m[size - 15 + i][8] = b
    # 副本2：水平（第 8 行）
    for i in range(15):
        b = (bits >> i) & 1
        if i < 8:
            m[8][size - i - 1] = b
        elif i == 8:
            m[8][7] = b
        else:
            m[8][15 - i - 1] = b
    m[size - 8][8] = 1  # 固定暗模块
    return m


def _penalty(m):
    size = len(m)
    score = 0
    # 规则1：连续同色
    for line in list(m) + [[m[r][c] for r in range(size)] for c in range(size)]:
        run = 1
        for i in range(1, size):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    # 规则2：2x2 同色块
    for r in range(size - 1):
        for c in range(size - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    # 规则3：1:1:3:1:1 模式
    pat1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pat2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for line in list(m) + [[m[r][c] for r in range(size)] for c in range(size)]:
        for i in range(size - 10):
            seg = line[i:i + 11]
            if seg == pat1 or seg == pat2:
                score += 40
    # 规则4：深色比例
    dark = sum(sum(row) for row in m)
    ratio = dark * 100 // (size * size)
    score += 10 * (abs(ratio - 50) // 5)
    return score


def make_matrix(text, ec_level='M'):
    """生成 QR 矩阵，返回 (matrix, version, mask_id)。matrix 为 0/1 二维列表。"""
    data = text.encode('utf-8')
    version = choose_version(len(data))
    codewords = _encode_codewords(data, version, ec_level)
    m, res = _make_matrix(version)
    _place_data(m, res, codewords)
    best, best_score, best_mask = None, None, 0
    for mask_id in range(8):
        cand = _apply_mask(m, res, mask_id)
        cand = _place_format(cand, ec_level, mask_id)
        s = _penalty(cand)
        if best_score is None or s < best_score:
            best, best_score, best_mask = cand, s, mask_id
    return best, version, best_mask


# ---------------- 往返校验 ----------------
def _rebuild_reserved(version):
    size = 17 + 4 * version
    res = [[False] * size for _ in range(size)]
    for (r0, c0) in [(0, 0), (0, size - 7), (size - 7, 0)]:
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < size and 0 <= cc < size:
                    res[rr][cc] = True
    for i in range(8, size - 8):
        res[6][i] = True
        res[i][6] = True
    for r0 in ALIGN_CENTERS[version]:
        for c0 in ALIGN_CENTERS[version]:
            if (r0 <= 8 and c0 <= 8) or (r0 <= 8 and c0 >= size - 9) or (r0 >= size - 9 and c0 <= 8):
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    res[r0 + r][c0 + c] = True
    for i in range(9):
        res[8][i] = True
        res[i][8] = True
    for i in range(8):
        res[8][size - 1 - i] = True
        res[size - 1 - i][8] = True
    if version >= 7:
        for i in range(18):
            r, c = i // 3, i % 3
            res[size - 11 + c][r] = True
            res[r][size - 11 + c] = True
    return res


def _read_format(m, version):
    """读回两份格式信息并做 BCH 校验，返回 (ec_level, mask_id) 或 None。"""
    size = len(m)
    # 副本1（竖直）
    v1 = 0
    for i in range(15):
        if i < 6:
            b = m[i][8]
        elif i < 8:
            b = m[i + 1][8]
        else:
            b = m[size - 15 + i][8]
        v1 |= (b & 1) << i
    # 副本2（水平）
    v2 = 0
    for i in range(15):
        if i < 8:
            b = m[8][size - i - 1]
        elif i == 8:
            b = m[8][7]
        else:
            b = m[8][15 - i - 1]
        v2 |= (b & 1) << i

    for val in (v1, v2):
        raw = val ^ 0x5412
        if _bch15_5(raw >> 10) != raw:
            continue
        data5 = raw >> 10
        ec = (data5 >> 3) & 0b11
        mask = data5 & 0b111
        for name, bits in EC_BITS.items():
            if bits == ec:
                return name, mask
    return None


def _deinterleave(codewords, version, ec_level):
    _total, ec_len, groups = VERSION_TABLE_M[version]
    blocks_meta = []
    for count, dlen in groups:
        for _ in range(count):
            blocks_meta.append(dlen)
    n_blocks = len(blocks_meta)
    max_d = max(blocks_meta)
    data_blocks = [[] for _ in range(n_blocks)]
    idx = 0
    for i in range(max_d):
        for bi, dlen in enumerate(blocks_meta):
            if i < dlen:
                if idx < len(codewords):
                    data_blocks[bi].append(codewords[idx])
                idx += 1
    ec_blocks = [[] for _ in range(n_blocks)]
    for i in range(ec_len):
        for bi in range(n_blocks):
            if idx < len(codewords):
                ec_blocks[bi].append(codewords[idx])
            idx += 1
    return data_blocks, ec_blocks, ec_len


def _syndrome_ok(data, ec, ec_len):
    """RS 伴随式校验：对每个 alpha^i (i=0..ec_len-1) 求值，应全为 0。"""
    full = list(data) + list(ec)
    for i in range(ec_len):
        acc = 0
        for cw in full:
            acc = _gf_mul(acc, _EXP[i]) ^ cw
        if acc != 0:
            return False
    return True


def verify(matrix, expected_text):
    """对生成的矩阵做往返解码校验，返回 (ok, detail)。"""
    size = len(matrix)
    version = (size - 17) // 4
    fmt = _read_format(matrix, version)
    if not fmt:
        return False, '格式信息 BCH 校验失败'
    ec_level, mask_id = fmt

    res = _rebuild_reserved(version)
    f = MASK_FUNCS[mask_id]
    unmasked = [row[:] for row in matrix]
    for r in range(size):
        for c in range(size):
            if not res[r][c] and f(r, c):
                unmasked[r][c] ^= 1

    bits = []
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (col, col - 1):
                if not res[r][c]:
                    bits.append(unmasked[r][c])
        col -= 2
        upward = not upward

    total_cw = VERSION_TABLE_M[version][0]
    codewords = []
    for i in range(total_cw):
        seg = bits[i * 8:i * 8 + 8]
        if len(seg) < 8:
            return False, '数据位不足'
        codewords.append(int(''.join(str(b) for b in seg), 2))

    data_blocks, ec_blocks, ec_len = _deinterleave(codewords, version, ec_level)
    for d, e in zip(data_blocks, ec_blocks):
        if not _syndrome_ok(d, e, ec_len):
            return False, 'RS 伴随式校验失败（纠错码字不一致）'

    flat = []
    for d in data_blocks:
        flat.extend(d)

    bitstr = ''.join(format(cw, '08b') for cw in flat)
    mode = int(bitstr[:4], 2)
    if mode != 0b0100:
        return False, f'模式指示符异常：{mode:04b}（期望 0100 字节模式）'
    cc_bits = 8 if version <= 9 else 16
    length = int(bitstr[4:4 + cc_bits], 2)
    payload_bits = bitstr[4 + cc_bits:4 + cc_bits + length * 8]
    if len(payload_bits) < length * 8:
        return False, '数据长度不足'
    out = bytes(int(payload_bits[i:i + 8], 2) for i in range(0, length * 8, 8))
    try:
        decoded = out.decode('utf-8')
    except Exception:
        return False, 'UTF-8 解码失败'
    if decoded != expected_text:
        return False, f'内容不一致：得到 {decoded!r}'
    return True, {'version': version, 'ec_level': ec_level, 'mask': mask_id,
                  'codewords': total_cw, 'bytes': length}
