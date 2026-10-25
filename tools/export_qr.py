# -*- coding: utf-8 -*-
"""二维码导出工具：把学生端访问地址导出为 PNG / SVG 文件（含往返校验）。

用途：课堂材料（PPT / 打印单）中插入二维码。

用法：
    # 1) 自动探测本机可用地址（优先公网地址，其次局域网 IP）
    python tools/export_qr.py --auto

    # 2) 指定地址（正式部署后推荐）
    python tools/export_qr.py --url https://xiaoyin.example.com/scan

    # 3) 指定输出目录与缩放
    python tools/export_qr.py --url https://xiaoyin.example.com/scan --out assets/qr --scale 12

安全约束：
- 拒绝把 localhost / 127.0.0.1 编码进二维码（学生手机无法访问）；
- 输出前做**矩阵级往返校验**，校验失败则拒绝导出（避免生成扫不出来的码）。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import netutil, qr_encode, qr_image  # noqa: E402


def pick_auto_url(port, public_base_url=''):
    if public_base_url:
        return public_base_url.rstrip('/') + '/scan', 'public'
    cands = netutil.candidate_urls(port, '')
    for c in cands:
        if c['kind'] == 'lan':
            return c['url'], 'lan'
    return None, None


def export_svg(text, path):
    matrix, version, mask = qr_encode.make_matrix(text)
    ok, detail = qr_encode.verify(matrix, text)
    if not ok:
        raise RuntimeError('二维码自校验失败：%s' % detail)
    n = len(matrix)
    border, scale = 4, 8
    size = (n + border * 2) * scale
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d" shape-rendering="crispEdges">' % (size, size, n + border * 2, n + border * 2),
             '<rect width="%d" height="%d" fill="#ffffff"/>' % (n + border * 2, n + border * 2),
             '<path fill="#111111" d="']
    for r in range(n):
        c = 0
        while c < n:
            if matrix[r][c]:
                start = c
                while c < n and matrix[r][c]:
                    c += 1
                parts.append('M%d %dh%dv1h-%dz' % (start + border, r + border, c - start, c - start))
            else:
                c += 1
    parts.append('"/></svg>')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(''.join(parts))
    return {'version': version, 'mask': mask, 'modules': n, 'roundtrip': ok, 'detail': detail}


def main():
    ap = argparse.ArgumentParser(description='导出学生端二维码（PNG / SVG）')
    ap.add_argument('--url', default=None, help='二维码指向的完整地址（建议 /scan 结尾）')
    ap.add_argument('--auto', action='store_true', help='自动探测本机可用地址')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--out', default=os.path.join('assets', 'qr'))
    ap.add_argument('--scale', type=int, default=12)
    ap.add_argument('--name', default=None)
    args = ap.parse_args()

    out_dir = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(out_dir, exist_ok=True)

    if args.url:
        url, kind = args.url, 'explicit'
    elif args.auto:
        url, kind = pick_auto_url(args.port)
    else:
        ap.error('请指定 --url 或 --auto')
    if not url:
        print('[错误] 未探测到可用地址：请确认本机已联网，或用 --url 明确指定。')
        return 1

    low = url.lower()
    if 'localhost' in low or '127.0.0.1' in low:
        print('[拒绝] 不允许把 localhost / 127.0.0.1 编码进二维码（学生手机无法访问）。')
        print('       请改用局域网 IP 或公网 HTTPS 域名。')
        return 2

    name = args.name or ('qr_' + ('public' if kind == 'public' else ('lan' if kind == 'lan' else 'custom')))
    png_path = os.path.join(out_dir, name + '.png')
    svg_path = os.path.join(out_dir, name + '.svg')

    meta = qr_image.save_png(url, png_path, scale=args.scale)
    svg_meta = export_svg(url, svg_path)

    print('=' * 66)
    print(' 二维码已导出')
    print('=' * 66)
    print(' 目标地址 :', url)
    print(' 地址类型 :', kind)
    print(' 矩阵级校验: 通过' if meta.get('roundtrip_verified') else ' 矩阵级校验: 失败')
    print(' 版本/模块 : v%s / %s×%s' % (meta['version'], meta['modules'], meta['modules']))
    print(' PNG      :', png_path)
    print(' SVG      :', svg_path)
    print('-' * 66)
    print(' 提示：正式参赛请使用公网 HTTPS 地址（需完成域名备案 + HTTPS 证书），')
    print('       不要使用局域网地址或 GitHub Pages 链接作为智能体入口。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
