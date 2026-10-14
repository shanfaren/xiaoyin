# -*- coding: utf-8 -*-
"""二维码图片渲染（纯标准库实现，无第三方依赖）。

生成 PNG 字节流：zlib 压缩 + 逐行 filter 0。QR 图形只需矩形像素，
因此这里内联一个最小的 PNG 编码器即可，避免依赖 PIL/png 等第三方库。
"""
import os
import struct
import zlib


def _png_chunk(tag, data):
    return (struct.pack('>I', len(data)) + tag + data
            + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))


def encode_png(width, height, rows, color_type=2):
    """把像素行编码为 PNG 字节。

    rows: 长度 height 的列表，每行为 bytes（长度 width*channels）。
    color_type: 2=RGB(8bit) 或 6=RGBA(8bit)。
    """
    if color_type == 2:
        channels = 3
    elif color_type == 6:
        channels = 4
    else:
        raise ValueError('仅支持 color_type 2(RGB) / 6(RGBA)')
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type: None
        row = rows[y]
        if len(row) != width * channels:
            raise ValueError(f'第 {y} 行长度错误：{len(row)} != {width * channels}')
        raw.extend(row)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, color_type, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n'
            + _png_chunk(b'IHDR', ihdr)
            + _png_chunk(b'IDAT', zlib.compress(bytes(raw), 9))
            + _png_chunk(b'IEND', b''))


def render_png_bytes(text, scale=8, border=4, dark=(17, 17, 17), light=(255, 255, 255),
                     ec_level='M', verify=True):
    """返回 (png_bytes, meta)。verify=True 时先做往返解码校验，校验失败抛异常。"""
    matrix, version, mask = _make_matrix(text, ec_level)
    meta = {'text': text, 'version': version, 'mask': mask, 'ec_level': ec_level,
            'modules': len(matrix), 'scale': scale, 'border': border}
    if verify:
        ok, detail = _verify(matrix, text)
        meta['roundtrip_verified'] = bool(ok)
        meta['roundtrip_detail'] = detail
        if not ok:
            raise RuntimeError(f'二维码自校验失败：{detail}')
    n = len(matrix)
    scale = max(1, int(scale))
    size = (n + border * 2) * scale
    rows = []
    for r in range(n + border * 2):
        mr = r - border          # 物理行 r 对应的矩阵行；边框区域为负/越界
        if 0 <= mr < n:
            row = _expand_row(matrix, mr, n, border, scale, dark, light)
        else:
            row = bytes(light) * size
        rows.append(row)
        rows.extend([row] * (scale - 1))   # 垂直方向按 scale 放大
    return encode_png(size, size, rows, color_type=2), meta


def _expand_row(matrix, mr, n, border, scale, dark, light):
    """矩阵第 mr 行 → 一条 PNG 像素行（宽度 (n+2*border)*scale，每模块 scale 像素宽）。"""
    dark_b = bytes(dark)
    light_b = bytes(light)
    out = bytearray()
    for c in range(-border, n + border):
        on = (0 <= c < n) and bool(matrix[mr][c])
        out.extend((dark_b if on else light_b) * scale)
    return bytes(out)


def _make_matrix(text, ec_level):
    from . import qr_encode
    return qr_encode.make_matrix(text, ec_level=ec_level)


def _verify(matrix, text):
    from . import qr_encode
    return qr_encode.verify(matrix, text)


def save_png(text, path, **kw):
    data, meta = render_png_bytes(text, **kw)
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    meta['path'] = path
    return meta


def matrix_text(matrix):
    """把矩阵渲染为终端可读文本（用于快速目视检查）。"""
    return '\n'.join(''.join('██' if v else '  ' for v in row) for row in matrix)
