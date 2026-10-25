# -*- coding: utf-8 -*-
"""原创角色"AI森林小博士·小隐"的矢量场景渲染引擎（纯标准库）。

设计目标：
- 同一份"场景定义"可导出两种产物：透明背景 PNG（位图）与可编辑 SVG（矢量）；
- 位图渲染使用 SDF（有符号距离场）抗锯齿，不依赖 PIL/第三方库；
- 小尺寸 PNG 由 256px 主图高质量下采样生成。

场景图元（100×100 坐标系，与 SVG viewBox 一致）：
  roundrect {x0,y0,x1,y1,r,fill:(r,g,b,a)}
  circle   {cx,cy,r,fill}
  ellipse  {cx,cy,rx,ry,fill}
  ring     {cx,cy,r,w,fill}              描边圆（放大镜框）
  arc      {cx,cy,r,a0,a1,w,fill}        圆弧（声波；角度制，0°指向右，顺时针）
  polygon  {pts:[(x,y)...],fill}          实心多边形（叶子、星星）
  qleaf    {p0,p1,p2,fill}                二次贝塞尔闭合叶片（离散为多边形）
颜色 fill 为 (r,g,b,a) 浮点 0..1。
"""
import math
import struct
import zlib


# ---------------------------------------------------------------- 基础工具
def _hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


C = {
    'forest900': _hex2rgb('#1D3B28'),
    'forest700': _hex2rgb('#2F6B3F'),
    'forest500': _hex2rgb('#4A8F56'),
    'leaf200': _hex2rgb('#D7E9CF'),
    'cream': _hex2rgb('#FBF7EC'),
    'white': (1.0, 1.0, 1.0),
    'sun': _hex2rgb('#F2C14E'),
    'clay': _hex2rgb('#C8552F'),
    'ink': _hex2rgb('#1C2A1E'),
}


def rgba(color, alpha=1.0):
    r, g, b = color[:3]
    return (r, g, b, color[3] if len(color) > 3 else alpha)


# ---------------------------------------------------------------- 图元基类
class Prim:
    __slots__ = ('op', 'kw')

    def __init__(self, op, **kw):
        f = kw.get('fill')
        if f is not None and len(f) == 3:
            kw['fill'] = (f[0], f[1], f[2], 1.0)
        self.op = op
        self.kw = kw


def roundrect(x0, y0, x1, y1, r, fill):
    return Prim('roundrect', x0=x0, y0=y0, x1=x1, y1=y1, r=r, fill=fill)


def circle(cx, cy, r, fill):
    return Prim('circle', cx=cx, cy=cy, r=r, fill=fill)


def ellipse(cx, cy, rx, ry, fill):
    return Prim('ellipse', cx=cx, cy=cy, rx=rx, ry=ry, fill=fill)


def ring(cx, cy, r, w, fill):
    return Prim('ring', cx=cx, cy=cy, r=r, w=w, fill=fill)


def arc(cx, cy, r, a0, a1, w, fill):
    return Prim('arc', cx=cx, cy=cy, r=r, a0=a0, a1=a1, w=w, fill=fill)


def polygon(pts, fill):
    return Prim('polygon', pts=[(float(x), float(y)) for x, y in pts], fill=fill)


def qleaf(p0, p1, p2, fill, segments=64):
    """二次贝塞尔叶片：p0→p2 为主轴，p1 为控制点，返回闭合多边形。"""
    pts = []
    for i in range(segments + 1):
        t = i / segments
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    # 用一段对称的控制点补全另一侧（近似镜像），形成叶片
    mid = ((p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2)
    q1 = (2 * mid[0] - p1[0], 2 * mid[1] - p1[1])
    back = []
    for i in range(segments + 1):
        t = i / segments
        mt = 1 - t
        x = mt * mt * p2[0] + 2 * mt * t * q1[0] + t * t * p0[0]
        y = mt * mt * p2[1] + 2 * mt * t * q1[1] + t * t * p0[1]
        back.append((x, y))
    return polygon(pts + back, fill)


def star(cx, cy, r_out, r_in, points=5, rot_deg=0, fill=C['sun']):
    """五角星（思考状态头顶的灵感星）。"""
    pts = []
    for i in range(points * 2):
        ang = math.radians(rot_deg + i * 180.0 / points)
        rr = r_out if i % 2 == 0 else r_in
        pts.append((cx + rr * math.cos(ang), cy - rr * math.sin(ang)))
    return polygon(pts, fill)


# ---------------------------------------------------------------- SDF 求值
def _sd_rect(x, y, x0, y0, x1, y1, r):
    qx = abs(x - (x0 + x1) / 2) - (x1 - x0) / 2
    qy = abs(y - (y0 + y1) / 2) - (y1 - y0) / 2
    # 圆角矩形 SDF
    mx = max(qx + r, 0.0)
    my = max(qy + r, 0.0)
    outside = math.hypot(mx, my) + min(max(qx, qy), 0.0) - r
    return outside


def _sd_circle(x, y, cx, cy, r):
    return math.hypot(x - cx, y - cy) - r


def _sd_ellipse(x, y, cx, cy, rx, ry):
    # 近似椭圆 SDF（对 rx≈ry 时精确；本角色的眼/嘴 rx 与 ry 接近，视觉无差）
    nx = (x - cx) / max(rx, 1e-6)
    ny = (y - cy) / max(ry, 1e-6)
    return (math.hypot(nx, ny) - 1.0) * min(rx, ry)


def _sd_ring(x, y, cx, cy, r, w):
    return abs(_sd_circle(x, y, cx, cy, r)) - w / 2


def _sd_arc(x, y, cx, cy, r, a0, a1, w):
    d_ring = abs(_sd_circle(x, y, cx, cy, r)) - w / 2
    ang = math.degrees(math.atan2(-(y - cy), x - cx)) % 360.0
    lo, hi = a0 % 360.0, a1 % 360.0
    span = (hi - lo) % 360.0          # 角度跨度（恒 ≥ 0）
    da = (ang - lo) % 360.0            # 当前点相对起点的角度
    if da <= span:
        ad = 0.0                        # 在角度范围内
    else:
        ad = min(da - span, 360.0 - da)  # 到近端的角度边界距离
    # 将角度边界转为近似线性距离：半径处 1° ≈ r*π/180
    return max(d_ring, ad * math.pi / 180.0 * r)


def _seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c1 = vx * wx + vy * wy
    if c1 <= 0:
        return math.hypot(px - ax, py - ay)
    c2 = vx * vx + vy * vy
    if c2 <= c1:
        return math.hypot(px - bx, py - by)
    t = c1 / c2
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _poly_alpha(x, y, pts):
    """多边形：射线法定内外 + 边界 SDF 抗锯齿。"""
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < x_cross:
                inside = not inside
        j = i
    dmin = min(_seg_dist(x, y, pts[i][0], pts[i][1], pts[(i + 1) % n][0], pts[(i + 1) % n][1])
               for i in range(n))
    sdf = dmin if inside else -dmin
    return min(max(sdf + 0.5, 0.0), 1.0)


# ---------------------------------------------------------------- 渲染器
class Scene:
    def __init__(self, prims):
        self.prims = prims

    # ---- 图元在该点的覆盖率 ----
    def _coverage(self, prim, x, y):
        op = prim.op
        k = prim.kw
        if op == 'roundrect':
            sdf = _sd_rect(x, y, k['x0'], k['y0'], k['x1'], k['y1'], k['r'])
        elif op == 'circle':
            sdf = _sd_circle(x, y, k['cx'], k['cy'], k['r'])
        elif op == 'ellipse':
            sdf = _sd_ellipse(x, y, k['cx'], k['cy'], k['rx'], k['ry'])
        elif op == 'ring':
            sdf = _sd_ring(x, y, k['cx'], k['cy'], k['r'], k['w'])
        elif op == 'arc':
            sdf = _sd_arc(x, y, k['cx'], k['cy'], k['r'], k['a0'], k['a1'], k['w'])
        elif op == 'polygon':
            return _poly_alpha(x, y, k['pts']), k['fill']
        else:
            return 0.0, k['fill']
        # SDF 约定：内部为负、外部为正；覆盖率 = clamp(0.5 - sdf)
        return min(max(0.5 - sdf, 0.0), 1.0), k['fill']

    # ---- 包围盒 ----
    def _bbox(self, prim):
        op, k = prim.op, prim.kw
        if op == 'roundrect':
            return (k['x0'] - 1, k['y0'] - 1, k['x1'] + 1, k['y1'] + 1)
        if op in ('circle', 'ring', 'arc'):
            rr = k['r'] + k.get('w', 0) / 2 + 1
            return (k['cx'] - rr, k['cy'] - rr, k['cx'] + rr, k['cy'] + rr)
        if op == 'ellipse':
            return (k['cx'] - k['rx'] - 1, k['cy'] - k['ry'] - 1, k['cx'] + k['rx'] + 1, k['cy'] + k['ry'] + 1)
        if op == 'polygon':
            xs = [p[0] for p in k['pts']]
            ys = [p[1] for p in k['pts']]
            return (min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
        return (0, 0, 100, 100)

    def raster(self, size=256, ss=3):
        """光栅化为 RGBA 字节行（size×size）。ss 为超采样倍数。"""
        W = size
        H = size
        buf = [[(0.0, 0.0, 0.0, 0.0)] * W for _ in range(H)]  # (r,g,b,a) 预乘未存储，直接存非预乘+alpha
        # 用样例缓冲加速：每个像素的 ss×ss 采样按图元包围盒裁剪
        for prim in self.prims:
            x0, y0, x1, y1 = self._bbox(prim)
            ix0 = max(0, int(math.floor(x0 * size / 100.0)))
            iy0 = max(0, int(math.floor(y0 * size / 100.0)))
            ix1 = min(W - 1, int(math.ceil(x1 * size / 100.0)))
            iy1 = min(H - 1, int(math.ceil(y1 * size / 100.0)))
            fr, fg, fb, fa = prim.kw['fill']
            if ix1 < ix0 or iy1 < iy0:
                continue
            for py in range(iy0, iy1 + 1):
                row = buf[py]
                for px in range(ix0, ix1 + 1):
                    # 超采样
                    acc = 0.0
                    for sy in range(ss):
                        yy = (py + (sy + 0.5) / ss) * 100.0 / size
                        for sx in range(ss):
                            xx = (px + (sx + 0.5) / ss) * 100.0 / size
                            cov, _ = self._coverage(prim, xx, yy)
                            acc += cov
                    a = acc / (ss * ss) * fa
                    if a <= 0.001:
                        continue
                    # src-over 合成到非预乘缓冲
                    cur = row[px]
                    ca = cur[3]
                    out_a = a + ca * (1 - a)
                    if out_a <= 0.001:
                        row[px] = (0.0, 0.0, 0.0, 0.0)
                        continue
                    out_r = (fr * a + cur[0] * ca * (1 - a)) / out_a
                    out_g = (fg * a + cur[1] * ca * (1 - a)) / out_a
                    out_b = (fb * a + cur[2] * ca * (1 - a)) / out_a
                    row[px] = (out_r, out_g, out_b, out_a)
        # 转字节行
        rows = []
        for y in range(H):
            rb = bytearray(W * 4)
            row = buf[y]
            for x in range(W):
                r, g, b, a = row[x]
                rb[x * 4] = int(round(min(max(r, 0.0), 1.0) * 255))
                rb[x * 4 + 1] = int(round(min(max(g, 0.0), 1.0) * 255))
                rb[x * 4 + 2] = int(round(min(max(b, 0.0), 1.0) * 255))
                rb[x * 4 + 3] = int(round(min(max(a, 0.0), 1.0) * 255))
            rows.append(bytes(rb))
        return rows


# ---------------------------------------------------------------- PNG 编码
def encode_png(width, height, rgba_rows):
    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))
    raw = bytearray()
    for row in rgba_rows:
        raw.append(0)
        raw.extend(row)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def downsample(rows, src, dst):
    """面积平均下采样（src→dst，4 通道）。"""
    if src == dst:
        return rows
    out = []
    ratio = src / dst
    for y in range(dst):
        sy0 = int(y * ratio)
        sy1 = max(sy0 + 1, int((y + 1) * ratio))
        rb = bytearray(dst * 4)
        for x in range(dst):
            sx0 = int(x * ratio)
            sx1 = max(sx0 + 1, int((x + 1) * ratio))
            acc = [0, 0, 0, 0]
            cnt = 0
            for yy in range(sy0, min(sy1, src)):
                row = rows[yy]
                for xx in range(sx0, min(sx1, src)):
                    acc[0] += row[xx * 4]
                    acc[1] += row[xx * 4 + 1]
                    acc[2] += row[xx * 4 + 2]
                    acc[3] += row[xx * 4 + 3]
                    cnt += 1
            rb[x * 4] = acc[0] // cnt
            rb[x * 4 + 1] = acc[1] // cnt
            rb[x * 4 + 2] = acc[2] // cnt
            rb[x * 4 + 3] = acc[3] // cnt
        out.append(bytes(rb))
    return out


# ---------------------------------------------------------------- SVG 序列化
def _svg_color(fill):
    r, g, b, a = fill
    return '#%02X%02X%02X' % (int(r * 255), int(g * 255), int(b * 255)), a


def scene_to_svg(prims, size=256, title='小隐'):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 100 100" role="img" aria-label="%s">' % (size, size, title)]
    parts.append('<title>AI森林小博士·小隐（原创角色）</title>')
    for p in prims:
        k = p.kw
        col, a = _svg_color(k['fill'])
        fill_attr = f'fill="{col}"' + (f' fill-opacity="{a:.3f}"' if a < 0.999 else '')
        if p.op == 'roundrect':
            parts.append(f'<rect x="{k["x0"]}" y="{k["y0"]}" width="{k["x1"]-k["x0"]}" '
                         f'height="{k["y1"]-k["y0"]}" rx="{k["r"]}" {fill_attr}/>')
        elif p.op == 'circle':
            parts.append(f'<circle cx="{k["cx"]}" cy="{k["cy"]}" r="{k["r"]}" {fill_attr}/>')
        elif p.op == 'ellipse':
            parts.append(f'<ellipse cx="{k["cx"]}" cy="{k["cy"]}" rx="{k["rx"]}" ry="{k["ry"]}" {fill_attr}/>')
        elif p.op == 'ring':
            parts.append(f'<circle cx="{k["cx"]}" cy="{k["cy"]}" r="{k["r"]}" fill="none" '
                         f'stroke="{col}" stroke-width="{k["w"]}"'
                         + (f' stroke-opacity="{a:.3f}"' if a < 0.999 else '') + '/>')
        elif p.op == 'arc':
            import math as _m
            a0, a1, r = k['a0'], k['a1'], k['r']
            x0 = k['cx'] + r * _m.cos(_m.radians(a0))
            y0 = k['cy'] - r * _m.sin(_m.radians(a0))
            x1 = k['cx'] + r * _m.cos(_m.radians(a1))
            y1 = k['cy'] - r * _m.sin(_m.radians(a1))
            span = (a1 - a0) % 360.0
            large = 1 if span > 180 else 0
            # 本模块角度约定：a 增大 = 屏幕逆时针 → SVG sweep-flag=0
            sweep = 0 if a1 > a0 else 1
            parts.append(f'<path d="M{x0:.2f} {y0:.2f} A{r} {r} 0 {large} {sweep} {x1:.2f} {y1:.2f}" '
                         f'fill="none" stroke="{col}" stroke-width="{k["w"]}" stroke-linecap="round"'
                         + (f' stroke-opacity="{a:.3f}"' if a < 0.999 else '') + '/>')
        elif p.op == 'polygon':
            pts = ' '.join(f'{x:.2f},{y:.2f}' for x, y in k['pts'])
            parts.append(f'<polygon points="{pts}" {fill_attr}/>')
    parts.append('</svg>')
    return '\n'.join(parts)
