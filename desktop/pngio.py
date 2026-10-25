# -*- coding: utf-8 -*-
"""最小 PNG 解码器（纯标准库），用于读取本项目生成的透明背景头像 PNG。

支持：8bit 灰度(0) / 真彩(2) / 带 Alpha 真彩(6)，全部 5 种行过滤器。
仅用于读取自己生成的资产，不做通用解码器。
"""
import struct
import zlib


def _unfilter(raw, width, height, channels):
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 0:
            pass
        elif ftype == 1:  # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        else:
            raise ValueError('不支持的 PNG 过滤器类型：%d' % ftype)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out, stride


def decode_png(path_or_bytes):
    """解码 PNG，返回 (width, height, rgba_rows)。
    rgba_rows 为 bytes 列表，每行 width*4 字节（RGBA，straight alpha）。"""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, 'rb') as f:
            data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('不是 PNG 文件')
    pos = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()
    palette = None
    while pos + 8 <= len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if tag == b'IHDR':
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack('>IIBBBBB', chunk[:13])
            if bit_depth != 8:
                raise ValueError('仅支持 8bit PNG，实际 %d' % bit_depth)
            if interlace != 0:
                raise ValueError('不支持隔行扫描 PNG')
        elif tag == b'PLTE':
            palette = chunk
        elif tag == b'IDAT':
            idat += chunk
        elif tag == b'IEND':
            break
        pos += 12 + length

    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError('不支持的颜色类型：%s' % color_type)
    raw = zlib.decompress(bytes(idat))
    pixels, stride = _unfilter(raw, width, height, channels)

    rows = []
    for y in range(height):
        base = y * stride
        if color_type == 6:
            rows.append(bytes(pixels[base:base + stride]))
        elif color_type == 2:
            row = bytearray(width * 4)
            for x in range(width):
                row[x * 4:x * 4 + 3] = pixels[base + x * 3:base + x * 3 + 3]
                row[x * 4 + 3] = 255
            rows.append(bytes(row))
        elif color_type == 0:
            row = bytearray(width * 4)
            for x in range(width):
                v = pixels[base + x]
                row[x * 4] = row[x * 4 + 1] = row[x * 4 + 2] = v
                row[x * 4 + 3] = 255
            rows.append(bytes(row))
        elif color_type == 4:
            row = bytearray(width * 4)
            for x in range(width):
                v = pixels[base + x * 2]
                a = pixels[base + x * 2 + 1]
                row[x * 4] = row[x * 4 + 1] = row[x * 4 + 2] = v
                row[x * 4 + 3] = a
            rows.append(bytes(row))
    return width, height, rows


def scale_rows(rows, src_w, src_h, dst_w, dst_h):
    """最近邻 + 面积平均的简易缩放（用于把 256px 头像缩放到悬浮窗显示尺寸）。"""
    if src_w == dst_w and src_h == dst_h:
        return rows
    out = []
    for y in range(dst_h):
        sy0 = int(y * src_h / dst_h)
        sy1 = max(sy0 + 1, int((y + 1) * src_h / dst_h))
        row = bytearray(dst_w * 4)
        for x in range(dst_w):
            sx0 = int(x * src_w / dst_w)
            sx1 = max(sx0 + 1, int((x + 1) * src_w / dst_w))
            acc = [0, 0, 0, 0]
            n = 0
            for yy in range(sy0, min(sy1, src_h)):
                srow = rows[yy]
                for xx in range(sx0, min(sx1, src_w)):
                    acc[0] += srow[xx * 4]
                    acc[1] += srow[xx * 4 + 1]
                    acc[2] += srow[xx * 4 + 2]
                    acc[3] += srow[xx * 4 + 3]
                    n += 1
            row[x * 4] = acc[0] // n
            row[x * 4 + 1] = acc[1] // n
            row[x * 4 + 2] = acc[2] // n
            row[x * 4 + 3] = acc[3] // n
        out.append(bytes(row))
    return out
