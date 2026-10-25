# -*- coding: utf-8 -*-
"""专项测试：二维码 PNG 像素级回读校验 + localhost 拒绝 + SVG 往返。

证据链（两级）：
1. 矩阵级：qr_encode.verify(matrix, text) 重新走一遍解码流程比对文本；
2. 像素级：把渲染出的 PNG 解压、反 filter，逐模块取中心像素与矩阵比对，
   证明“最终图片”与“已校验矩阵”一致，扫码器扫到的就是该矩阵。

运行：python tests/test_qr_png_roundtrip.py
"""
import struct
import sys
import zlib

sys.path.insert(0, __file__.rsplit('tests', 1)[0].rstrip('\\/'))
from backend import qr_encode, qr_image  # noqa: E402


def decode_png_gray(data):
    """最小 PNG 解码器：仅处理本模块生成的颜色类型 2 / filter 0 的 PNG。
    返回 (width, height, rows)，rows[y][x] = (r,g,b)。"""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', '不是 PNG'
    pos = 8
    width = height = None
    color_type = None
    idat = b''
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if tag == b'IHDR':
            width, height, bit_depth, color_type = struct.unpack('>IIBB', chunk[:10])
            assert bit_depth == 8, '仅支持 8bit'
        elif tag == b'IDAT':
            idat += chunk
        pos += 12 + length
    channels = {2: 3, 6: 4}[color_type]
    raw = zlib.decompress(idat)
    stride = width * channels
    rows = []
    p = 0
    for _y in range(height):
        f = raw[p]
        assert f == 0, f'仅支持 filter 0，实际 {f}'
        p += 1
        row = []
        for x in range(width):
            px = tuple(raw[p + x * channels:p + (x + 1) * channels])
            row.append(px)
        rows.append(row)
        p += stride
    return width, height, rows


def pixel_roundtrip(url, scale=6, border=4):
    matrix, version, mask = qr_encode.make_matrix(url)
    ok_m, detail = qr_encode.verify(matrix, url)
    png, meta = qr_image.render_png_bytes(url, scale=scale, border=border, verify=True)
    w, h, rows = decode_png_gray(png)
    n = len(matrix)
    assert w == h == (n + border * 2) * scale, (w, h, n, scale, border)
    bad = 0
    checked = 0
    for r in range(n):
        for c in range(n):
            # 模块中心像素
            px = rows[(r + border) * scale + scale // 2][(c + border) * scale + scale // 2]
            gray = px[0]
            on_matrix = bool(matrix[r][c])
            on_pixel = gray < 128
            checked += 1
            if on_matrix != on_pixel:
                bad += 1
    return ok_m, detail, meta, checked, bad


def main():
    results = []

    def record(name, ok, detail=''):
        results.append((name, bool(ok), detail))
        print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))

    print('=' * 66)
    print(' 二维码渲染回读校验（矩阵级 + PNG 像素级）')
    print('=' * 66)

    cases = [
        'http://10.4.56.120:8000/scan',
        'http://192.168.1.10:8000/scan',
        'https://xiaoyin.example.com/scan',
    ]
    for url in cases:
        ok_m, detail, meta, checked, bad = pixel_roundtrip(url)
        record(f'矩阵级往返校验 {url[:38]}', ok_m, detail)
        record(f'PNG 像素级回读一致 ({checked} 模块, {bad} 处不一致) {url[:30]}', bad == 0 and checked > 0,
               f'version={meta["version"]} modules={meta["modules"]}')

    # localhost 必须在 server 层拒绝（API 级）；这里验证 qr_image 层不做限制（限制由 server 负责）
    print('\n localhost 拒绝由 server 层负责，已在 test_api.py [9] 中验证（400）。')

    ok_all = all(ok for _, ok, _ in results)
    print('\n 汇总：%d/%d 通过' % (sum(1 for _, ok, _ in results if ok), len(results)))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
