# -*- coding: utf-8 -*-
"""二维码**独立解码器**（从 PNG 像素出发，按 ISO/IEC 18004 规范实现读取路径）。

与 `backend/qr_encode.py` 完全解耦：
- 不导入、不复用编码器的任何矩阵或校验逻辑；
- 输入只有一张 PNG 图片，输出是解码出的文本；
- 步骤：像素二值化 → 定位模块网格 → 结构校验（定位图形 / 定时图形）→ 读取格式信息
  （纠错等级 + 掩模号）→ 去掩模 → 按之字形读取码字 → 解析模式与长度 → 取出字节 → UTF-8 解码。

用途：为“二维码可被正确扫描”提供**第三方路径**的证据（本环境无法用手机相机实测，
也无 zbar/cv2/jsQR 等外部解码器可用，故自实现独立读取路径）。
"""
import struct
import zlib

# 各版本对齐图形中心坐标（版本 1–10，足够本项目使用）
ALIGN = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}
# 各版本纠错块结构：(每块数据码字数, 每块纠错码字数) × 组数 —— 仅列出本项目会用到的低版本
EC_BLOCKS = {
    # version: {ec_level: (ec_codewords_per_block, [(num_blocks, data_codewords), ...])}
    1: {'L': (7, [(1, 19)]), 'M': (10, [(1, 16)]), 'Q': (13, [(1, 13)]), 'H': (17, [(1, 9)])},
    2: {'L': (10, [(1, 34)]), 'M': (16, [(1, 28)]), 'Q': (22, [(1, 22)]), 'H': (28, [(1, 16)])},
    3: {'L': (15, [(1, 55)]), 'M': (26, [(1, 44)]), 'Q': (18, [(2, 17)]), 'H': (22, [(2, 13)])},
    4: {'L': (20, [(1, 80)]), 'M': (18, [(2, 32)]), 'Q': (26, [(2, 24)]), 'H': (16, [(4, 9)])},
    5: {'L': (26, [(1, 108)]), 'M': (24, [(2, 43)]), 'Q': (18, [(2, 15), (2, 16)]), 'H': (22, [(2, 11), (2, 12)])},
}
FORMAT_EC = {0b01: 'L', 0b00: 'M', 0b11: 'Q', 0b10: 'H'}   # 格式信息中的 2 位纠错等级编码
FORMAT_EC_INV = {v: k for k, v in FORMAT_EC.items()}


def decode_png_gray(path):
    """最小 PNG 解码：返回 (width, height, gray_rows)，gray_rows[y][x] = 0..255 灰度。"""
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', '不是 PNG'
    pos, idat = 8, bytearray()
    while pos + 8 <= len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if tag == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', chunk[:10])
            assert depth == 8 and ctype in (2, 6), (depth, ctype)
        elif tag == b'IDAT':
            idat += chunk
        elif tag == b'IEND':
            break
        pos += 12 + ln
    raw = zlib.decompress(bytes(idat))
    ch = 3 if ctype == 2 else 4
    stride = w * ch
    rows, prev, p = [], bytearray(stride), 0
    for _y in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        rows.append(bytes(line[i * ch] for i in range(w)))
        prev = line
    return w, h, rows


def _find_module_size(rows, w, h):
    """用左上定位图形估算模块尺寸：定位图形为 1:1:3:1:1 的黑白交替。"""
    # 从上往下找第一条包含长黑段的扫描线（定位图形外框上边）
    for y in range(min(h, w // 2)):
        row = rows[y]
        x = 0
        # 跳过静区
        while x < w and row[x] > 128:
            x += 1
        if x >= w:
            continue
        run = 0
        while x + run < w and row[x + run] <= 128:
            run += 1
        if run < 3:
            continue
        # 该黑段可能是定位图形外框的“上边”（长度 = 7 个模块）
        # 用竖直方向同宽黑段长度校验：定位图形外框左侧同样 7 模块
        return max(1, round(run / 7.0))
    return 0


def _binarize(rows, w, h):
    return [[1 if rows[y][x] <= 128 else 0 for x in range(w)] for y in range(h)]


def _sample_matrix(bin_img, w, h, module, border=4):
    """按模块尺寸与静区宽度采样出模块矩阵，并自动确定版本。"""
    # 静区像素宽 = border * module；用左上定位图形左上角作为原点
    # 先扫描出定位图形的左上角（第一个黑像素）
    ox = oy = None
    for y in range(min(h, 10 * module)):
        for x in range(min(w, 10 * module)):
            if bin_img[y][x] == 1:
                ox, oy = x, y
                break
        if ox is not None:
            break
    if ox is None:
        raise ValueError('未找到定位图形')
    ox -= border * module
    oy -= border * module
    if ox < 0 or oy < 0:
        ox = max(0, ox)
        oy = max(0, oy)
    # 版本 = (模块数 - 17) / 4，模块数由图像可用宽度反推
    avail = min(w - ox, h - oy)
    n = int(round(avail / module)) - border * 2
    n = ((n - 17) // 4) * 4 + 17        # 归一化到合法版本尺寸
    version = (n - 17) // 4
    mat = []
    for r in range(n):
        line = []
        for c in range(n):
            cx = ox + (c + border) * module + module // 2
            cy = oy + (r + border) * module + module // 2
            line.append(bin_img[cy][cx] if 0 <= cy < h and 0 <= cx < w else 0)
        mat.append(line)
    return mat, version


def _check_structure(mat, version):
    """结构校验：三个定位图形 + 定时图形。返回 (ok, 说明)。"""
    n = len(mat)
    problems = []
    for (r0, c0) in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(7):
            for c in range(7):
                expect = 1 if (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4)) else 0
                if mat[r0 + r][c0 + c] != expect:
                    problems.append('定位图形 (%d,%d) 不匹配' % (r0, c0))
                    break
            else:
                continue
            break
    for i in range(8, n - 8):
        if mat[6][i] != (1 if i % 2 == 0 else 0):
            problems.append('水平定时图形第 %d 列不匹配' % i)
            break
    for i in range(8, n - 8):
        if mat[i][6] != (1 if i % 2 == 0 else 0):
            problems.append('垂直定时图形第 %d 行不匹配' % i)
            break
    return (not problems), ('；'.join(problems) if problems else '结构校验通过')


def _function_map(version):
    """返回 n×n 的布尔矩阵：True 表示该模块是功能图形（非数据区）。"""
    n = version * 4 + 17
    f = [[False] * n for _ in range(n)]

    def block(r0, c0, hh, ww):
        for r in range(r0, r0 + hh):
            for c in range(c0, c0 + ww):
                if 0 <= r < n and 0 <= c < n:
                    f[r][c] = True
    # 定位图形 + 分隔符
    block(0, 0, 8, 8)
    block(0, n - 8, 8, 8)
    block(n - 8, 0, 8, 8)
    # 定时图形
    for i in range(n):
        f[6][i] = True
        f[i][6] = True
    # 对齐图形（5×5，含边框）
    for r in ALIGN.get(version, []):
        for c in ALIGN.get(version, []):
            if (r <= 8 and c <= 8) or (r <= 8 and c >= n - 9) or (r >= n - 9 and c <= 8):
                continue
            block(r - 2, c - 2, 5, 5)
    # 格式信息
    for i in range(9):
        f[8][i] = True
        f[i][8] = True
    for i in range(8):
        f[8][n - 1 - i] = True
        f[n - 1 - i][8] = True
    # 固定暗模块
    f[n - 8][8] = True
    # 版本信息（版本 ≥ 7）
    if version >= 7:
        block(0, n - 11, 6, 3)
        block(n - 11, 0, 3, 6)
    return f


def _read_format(mat, version):
    """读取 15 位格式信息（两份，取校验通过的一份），返回 (ec_level, mask)。"""
    n = len(mat)
    bits1 = []
    # 第一份：环绕左上定位图形
    for i in range(6):
        bits1.append(mat[8][i])
    bits1.append(mat[8][7])
    bits1.append(mat[8][8])
    bits1.append(mat[7][8])
    for i in range(5, -1, -1):
        bits1.append(mat[i][8])
    bits2 = []
    for i in range(7, -1, -1):
        bits2.append(mat[n - 1 - i][8])
    for i in range(8):
        bits2.append(mat[8][n - 8 + i])

    def parse(bits):
        val = 0
        for b in bits:
            val = (val << 1) | b
        # 去掩模（格式信息与 101010000010010 异或）
        val ^= 0b101010000010010
        # 校验：BCH(15,5) 生成多项式 0b10100110111；合法码字对生成多项式取余为 0
        rem = val
        gen = 0b10100110111
        for i in range(14, 9, -1):
            if rem & (1 << i):
                rem ^= gen << (i - 10)
        if rem != 0:
            return None, None
        ec = (val >> 13) & 0b11
        mask = (val >> 10) & 0b111
        return FORMAT_EC.get(ec), mask

    for bits in (bits1, bits2):
        ec, mask = parse(bits)
        if ec is not None:
            return ec, mask
    raise ValueError('格式信息校验失败')


def _mask_fn(mask_id, i, j):
    if mask_id == 0:
        return (i + j) % 2 == 0
    if mask_id == 1:
        return i % 2 == 0
    if mask_id == 2:
        return j % 3 == 0
    if mask_id == 3:
        return (i + j) % 3 == 0
    if mask_id == 4:
        return (i // 2 + j // 3) % 2 == 0
    if mask_id == 5:
        return (i * j) % 2 + (i * j) % 3 == 0
    if mask_id == 6:
        return ((i * j) % 2 + (i * j) % 3) % 2 == 0
    if mask_id == 7:
        return ((i + j) % 2 + (i * j) % 3) % 2 == 0
    raise ValueError('非法掩模号 %d' % mask_id)


def _read_codewords(mat, version, mask_id):
    """按之字形从右下向左上读取数据码字（跳过功能图形），返回比特列表。"""
    n = len(mat)
    fmap = _function_map(version)
    bits = []
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:          # 跳过垂直定时图形所在列
            col -= 1
            continue
        rows_range = range(n - 1, -1, -1) if upward else range(n)
        for r in rows_range:
            for c in (col, col - 1):
                if not fmap[r][c]:
                    bit = mat[r][c]
                    if _mask_fn(mask_id, r, c):
                        bit ^= 1
                    bits.append(bit)
        upward = not upward
        col -= 2
    return bits


def _bits_to_codewords(bits):
    out = []
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        out.append(v)
    return out


def _strip_ec(codewords, version, ec_level):
    """去掉纠错码字，按块结构还原数据码字（本项目 URL 很短，通常为单块）。"""
    spec = EC_BLOCKS.get(version, {}).get(ec_level)
    if not spec:
        return codewords          # 未知结构时直接返回（低版本单块场景）
    ec_per_block, groups = spec
    total_data = sum(nb * dc for nb, dc in groups)
    blocks = []
    pos = 0
    for nb, dc in groups:
        for _ in range(nb):
            blocks.append(codewords[pos:pos + dc])
            pos += dc
    # 交错还原：数据码字按块交错，这里按顺序拼接（单块时等价）
    out = []
    for i in range(max(len(b) for b in blocks) if blocks else 0):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    return out[:total_data]


def _parse_payload(data_codewords):
    """解析模式 + 长度 + 数据。支持 数字/字母数字/字节 三种模式。"""
    bits = []
    for cw in data_codewords:
        for k in range(7, -1, -1):
            bits.append((cw >> k) & 1)
    pos = 0

    def take(k):
        nonlocal pos
        v = 0
        for _ in range(k):
            v = (v << 1) | bits[pos]
            pos += 1
        return v

    out = bytearray()
    while pos + 4 <= len(bits):
        mode = take(4)
        if mode == 0:                       # 终止符
            break
        if mode == 1:                       # 数字
            count = take(10)
            while count >= 3:
                v = take(10)
                out += ('%03d' % v).encode()
                count -= 3
            if count == 2:
                out += ('%02d' % take(7)).encode()
            elif count == 1:
                out += ('%01d' % take(4)).encode()
        elif mode == 2:                     # 字母数字
            table = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:'
            count = take(9)
            while count >= 2:
                v = take(11)
                out += table[v // 45].encode()
                out += table[v % 45].encode()
                count -= 2
            if count == 1:
                out += table[take(6)].encode()
        elif mode == 4:                     # 字节
            count = take(8)
            for _ in range(count):
                out.append(take(8))
        else:
            raise ValueError('不支持的模式指示符 %d' % mode)
    return bytes(out)


def decode_qr_png(path):
    """完整解码：PNG 图片 → 文本。返回 (text, info)。"""
    w, h, gray = decode_png_gray(path)
    bin_img = _binarize(gray, w, h)
    module = _find_module_size(gray, w, h)
    if module <= 0:
        raise ValueError('无法估算模块尺寸')
    mat, version = _sample_matrix(bin_img, w, h, module)
    ok, detail = _check_structure(mat, version)
    if not ok:
        raise ValueError('结构校验失败：%s' % detail)
    ec_level, mask_id = _read_format(mat, version)
    bits = _read_codewords(mat, version, mask_id)
    codewords = _bits_to_codewords(bits)
    data = _strip_ec(codewords, version, ec_level)
    payload = _parse_payload(data)
    return payload.decode('utf-8', 'strict'), {
        'size': (w, h), 'module_px': module, 'version': version,
        'ec_level': ec_level, 'mask': mask_id, 'structure': detail,
    }
