# -*- coding: utf-8 -*-
"""将扫描PDF逐页渲染为PNG，便于视觉识别(OCR)。"""
import pymupdf, os, sys

def render(pdf, outdir, dpi=110):
    os.makedirs(outdir, exist_ok=True)
    d = pymupdf.open(pdf)
    info = []
    for i, page in enumerate(d):
        r = page.rect
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        name = os.path.join(outdir, 'p%02d.png' % (i + 1))
        pix.save(name)
        info.append((i + 1, round(r.width), round(r.height), pix.width, pix.height, os.path.getsize(name)))
    d.close()
    return info

if __name__ == '__main__':
    pdf = sys.argv[1]
    outdir = sys.argv[2]
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 110
    for row in render(pdf, outdir, dpi):
        print('p%-3d page=%dx%d px=%dx%d size=%dKB' % (row[0], row[1], row[2], row[3], row[4], row[5] // 1024))
