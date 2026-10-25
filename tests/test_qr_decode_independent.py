# -*- coding: utf-8 -*-
"""专项测试：二维码**独立解码**（不依赖编码器内部矩阵）。

证据强度说明（三级）：
1. 矩阵级：`qr_encode.verify()` 重走解码流程（编码器自带校验）；
2. 像素级：`tests/test_qr_png_roundtrip.py` 把 PNG 逐模块与矩阵比对（证明渲染正确）；
3. **独立解码（本文件）**：只用 PNG 图片像素，按 ISO/IEC 18004 规范自实现读取路径
   （定位图形 → 模块网格 → 格式信息 BCH 校验 → 去掩模 → 之字形读码字 → 解析模式与长度 → UTF-8），
   不导入也不复用 `backend/qr_encode.py` 的任何矩阵或校验逻辑。

本环境无法使用手机相机实测，且无 zbar / cv2 / jsQR 等外部解码器（网络不可用），
故以独立实现的规范解码路径作为最强替代证据；**真机扫码仍需人工实测**。

运行：python tests/test_qr_decode_independent.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from backend import qr_image          # noqa: E402
import qr_decode_ref as decoder       # noqa: E402


def main():
    results = []

    def record(name, ok, detail=''):
        results.append((name, bool(ok), detail))
        print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))

    print('=' * 68)
    print(' 二维码独立解码测试（仅从 PNG 像素出发，不复用编码器逻辑）')
    print('=' * 68)

    cases = [
        'http://10.6.114.47:8000/scan',
        'http://192.168.1.10:8000/scan',
        'http://172.16.5.9:8080/scan',
        'https://xiaoyin.example.com/scan',
        'https://a.example.cn/scan',
        'http://192.168.31.200:8000/scan',        # 更长内容 → 更高版本
    ]
    tmpdir = tempfile.mkdtemp(prefix='qr_decode_')
    versions, masks = set(), set()
    for i, url in enumerate(cases):
        path = os.path.join(tmpdir, 'case%d.png' % i)
        qr_image.save_png(url, path, scale=8)
        try:
            text, info = decoder.decode_qr_png(path)
        except Exception as e:
            record('独立解码 %s' % url, False, '%s: %s' % (type(e).__name__, e))
            continue
        versions.add(info['version'])
        masks.add(info['mask'])
        record('独立解码正确（v%d / mask%d / %s / 模块 %dpx）'
               % (info['version'], info['mask'], info['ec_level'], info['module_px']),
               text == url, '解码结果=%s' % text)

    record('覆盖多个二维码版本', len(versions) >= 2, sorted(versions))
    record('覆盖多个掩模图案', len(masks) >= 2, sorted(masks))

    # 负向验证：损坏的图片必须解码失败（避免“解码器恒真”的假通过）
    bad = os.path.join(tmpdir, 'broken.png')
    qr_image.save_png('http://10.6.114.47:8000/scan', bad, scale=8)
    with open(bad, 'rb') as f:
        data = bytearray(f.read())
    # 破坏中间数据区（把中段像素翻白），保持 PNG 结构合法
    mid = len(data) // 2
    for k in range(mid, min(mid + 400, len(data))):
        data[k] = 0xFF
    with open(bad, 'wb') as f:
        f.write(bytes(data))
    failed = False
    try:
        decoder.decode_qr_png(bad)
    except Exception:
        failed = True
    record('被破坏的二维码解码失败（负向验证，排除恒真）', failed)

    ok_all = all(ok for _, ok, _ in results)
    print('\n 汇总：%d/%d 通过' % (sum(1 for _, ok, _ in results if ok), len(results)))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
