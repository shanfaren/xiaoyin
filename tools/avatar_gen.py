# -*- coding: utf-8 -*-
"""原创角色"AI森林小博士·小隐"资产生成器。

产出（assets/avatar/）：
- xiaoyin_<state>.svg         可编辑矢量图（四状态各一份 + 合并版 xiaoyin_all.svg）
- xiaoyin_<state>.png         256px 透明背景 PNG（主帧）
- xiaoyin_<state>_f0..f2.png  256px 动画帧（悬浮窗状态动画用）
- xiaoyin_<state>_128/_80/_64.png  下采样小尺寸（网页/低分辨率场景）

四状态：idle 待机 / listening 倾听 / thinking 思考 / speaking 发声。
角色约束：暖白机身 + 森林绿外壳 + 发光眼睛 + 叶片 + 放大镜；不复制任何第三方商标或角色。

运行：python tools/avatar_gen.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from avatar_raster import (C, Scene, arc, circle, downsample, ellipse, encode_png,  # noqa: E402
                            polygon, qleaf, rgba, ring, roundrect, scene_to_svg, star)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'avatar')


# ---------------------------------------------------------------- 场景构建
def body(eye_ry=6.4, eye_r=6.4, eye_a=1.0, glow_a=0.30, hl_y=49.0, hl_a=0.95):
    """角色主体（外壳、脸、面罩、发光眼、放大镜、叶片）。"""
    # 多层柔光：由外向内三层，形成柔和发光感
    glow = [
        circle(40, 51, eye_r + 5.2, rgba(C['sun'], glow_a * 0.35)),
        circle(60, 51, eye_r + 5.2, rgba(C['sun'], glow_a * 0.35)),
        circle(40, 51, eye_r + 3.2, rgba(C['sun'], glow_a * 0.7)),
        circle(60, 51, eye_r + 3.2, rgba(C['sun'], glow_a * 0.7)),
        circle(40, 51, eye_r + 1.4, rgba(C['sun'], min(glow_a * 1.5, 0.6))),
        circle(60, 51, eye_r + 1.4, rgba(C['sun'], min(glow_a * 1.5, 0.6))),
    ]
    prims = [
        # 头顶叶片（先画，压在机身下）
        qleaf(p0=(50, 17), p1=(66, 1), p2=(83, 9), fill=rgba(C['forest500'])),
        polygon([(54.0, 15.0), (56.0, 9.5), (57.6, 14.4)], fill=rgba(C['forest700'])),  # 叶柄
        polygon([(56.5, 13.0), (76.0, 8.8), (76.6, 10.2), (56.9, 14.6)], fill=rgba(C['forest700'], 0.5)),  # 叶脉
        # 外壳与脸
        roundrect(14, 20, 86, 86, 24, rgba(C['forest700'])),
        roundrect(19, 25, 81, 81, 20, rgba(C['cream'])),
        ellipse(50, 32.5, 24, 7.0, rgba((1, 1, 1), 0.5)),  # 额头柔光
        roundrect(27, 37, 73, 65, 13, rgba(C['forest900'], 0.92)),  # 深色面罩
    ] + glow + [
        # 发光眼睛
        ellipse(40, 51, eye_r, eye_ry, rgba(C['sun'], eye_a)),
        ellipse(60, 51, eye_r, eye_ry, rgba(C['sun'], eye_a)),
        circle(41.6, 49.2, 1.9, rgba(C['white'], hl_a)),
        circle(61.6, 49.2, 1.9, rgba(C['white'], hl_a)),
        # 微笑嘴
        arc(50, 58.8, 3.4, 195, 345, 1.7, rgba(C['cream'], 0.95)),
        # 放大镜
        circle(79, 71, 5.0, rgba(C['leaf200'], 0.85)),
        ring(79, 71, 9.0, 3.2, rgba(C['clay'])),
        polygon([(85.2, 76.2), (92.4, 84.2), (89.4, 86.8), (82.2, 78.8)], fill=rgba(C['clay'])),
    ]
    return prims


def scene_idle(blink=False, glow_a=0.30):
    eye_ry = 1.5 if blink else 6.4
    hl_a = 0.0 if blink else 0.95
    return body(eye_ry=eye_ry, eye_r=6.4, glow_a=(0.18 if blink else glow_a),
                hl_y=49.0, hl_a=hl_a)


def wave_arcs(cy=57.0, alphas=(0.90, 0.55, 0.30), color=None, radii=(9.0, 13.0, 17.0)):
    """嘴边三道声波弧（自嘴部向右下展开，避开眼睛与放大镜）。"""
    color = color or C['cream']
    return [arc(50, cy, r, -78, -12, 2.0, rgba(color, a)) for r, a in zip(radii, alphas)]


def scene_listening(wave_alpha=(0.90, 0.55, 0.30), eye_r=6.8, glow_a=0.42):
    prims = body(eye_ry=6.4, eye_r=eye_r, glow_a=glow_a)
    prims += wave_arcs(alphas=wave_alpha)
    return prims


def scene_thinking(bubble_y=22.0, star_rot=-10.0):
    prims = body(eye_ry=6.4, eye_r=6.4, glow_a=0.24, hl_y=47.6)  # 眼睛微微上瞄
    # 思考气泡（右上）
    prims += [
        circle(84, bubble_y, 6.5, rgba(C['white'], 0.95)),
        ring(84, bubble_y, 6.5, 1.0, rgba(C['forest500'], 0.8)),
        circle(84, bubble_y, 2.3, rgba(C['forest700'])),
        circle(77.5, bubble_y + 7.0, 3.2, rgba(C['white'], 0.92)),
        circle(73.5, bubble_y + 11.0, 2.1, rgba(C['white'], 0.88)),
    ]
    # 灵感小星（左上）
    prims += [star(30, 9.5, 4.6, 1.9, rot_deg=star_rot)]
    return prims


def scene_speaking(mouth_ry=3.6, wave_alpha=(0.90, 0.55, 0.30)):
    prims = body(eye_ry=6.4, eye_r=6.4, glow_a=0.34, hl_y=49.0)
    # 替换微笑嘴为张开嘴：追加深色椭圆盖住微笑弧
    prims += [ellipse(50, 58.2, 5.2, mouth_ry, rgba(C['forest900'], 0.97))]
    prims += [ellipse(50, 59.6, 3.0, max(mouth_ry - 1.6, 0.6), rgba(C['clay'], 0.9))]  # 小舌头
    prims += wave_arcs(cy=57.0, alphas=wave_alpha)
    return prims


# ---------------------------------------------------------------- 导出
def export_scene(name, prims, frames=None):
    """导出 PNG（主帧 + 动画帧 + 小尺寸）与 SVG。frames: [(suffix, prims)]"""
    scene = Scene(prims)
    rows = scene.raster(size=256, ss=1)
    paths = []

    def write_png(path, data_rows, w):
        with open(path, 'wb') as f:
            f.write(encode_png(w, w, data_rows))
        paths.append(path)

    main_png = os.path.join(OUT, f'xiaoyin_{name}.png')
    write_png(main_png, rows, 256)
    for size in (128, 80, 64):
        write_png(os.path.join(OUT, f'xiaoyin_{name}_{size}.png'), downsample(rows, 256, size), size)

    if frames:
        for suffix, fprims in frames:
            frows = Scene(fprims).raster(size=256, ss=1)
            write_png(os.path.join(OUT, f'xiaoyin_{name}_{suffix}.png'), frows, 256)

    svg_path = os.path.join(OUT, f'xiaoyin_{name}.svg')
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(scene_to_svg(prims, title=f'小隐·{name}'))
    paths.append(svg_path)
    return paths


def main():
    os.makedirs(OUT, exist_ok=True)
    all = {}

    all['idle'] = export_scene('idle', scene_idle(), frames=[
        ('f0', scene_idle()),
        ('f1', scene_idle(blink=True)),
        ('f2', scene_idle(glow_a=0.45)),
    ])
    all['listening'] = export_scene('listening', scene_listening(), frames=[
        ('f0', scene_listening(wave_alpha=(0.90, 0.55, 0.30))),
        ('f1', scene_listening(wave_alpha=(0.45, 0.85, 0.50), eye_r=7.2, glow_a=0.5)),
        ('f2', scene_listening(wave_alpha=(0.30, 0.50, 0.90))),
    ])
    all['thinking'] = export_scene('thinking', scene_thinking(), frames=[
        ('f0', scene_thinking(bubble_y=22.0, star_rot=-10.0)),
        ('f1', scene_thinking(bubble_y=20.0, star_rot=20.0)),
        ('f2', scene_thinking(bubble_y=21.0, star_rot=-20.0)),
    ])
    all['speaking'] = export_scene('speaking', scene_speaking(), frames=[
        ('f0', scene_speaking(mouth_ry=3.6, wave_alpha=(0.90, 0.55, 0.30))),
        ('f1', scene_speaking(mouth_ry=1.8, wave_alpha=(0.45, 0.85, 0.50))),
        ('f2', scene_speaking(mouth_ry=4.6, wave_alpha=(0.30, 0.50, 0.90))),
    ])

    # 合并 SVG（四状态分组，默认显示 idle）
    combined = ['<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 100 100" '
                'role="img" aria-label="小隐">',
                '<title>AI森林小博士·小隐（原创角色，四状态）</title>',
                '<style>.st{display:none}.st.on{display:block}</style>']
    for i, name in enumerate(('idle', 'listening', 'thinking', 'speaking')):
        combined.append(f'<g id="state-{name}" class="st{" on" if i == 0 else ""}">')
        combined.append(scene_to_svg(all_state_prims(name), title='小隐')
                        .replace('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
                                 'viewBox="0 0 100 100" role="img" aria-label="小隐">', '')
                        .replace('<title>小隐·' + name + '</title>', '')
                        .replace('</svg>', ''))
        combined.append('</g>')
    combined.append('</svg>')
    with open(os.path.join(OUT, 'xiaoyin_all.svg'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(combined))

    total = sum(len(v) for v in all.values()) + 1
    print('已生成 %d 个头像文件 -> %s' % (total, OUT))
    for k, v in all.items():
        print(' ', k, ':', len(v), '文件')


def all_state_prims(name):
    return {'idle': scene_idle, 'listening': scene_listening,
            'thinking': scene_thinking, 'speaking': scene_speaking}[name]()


if __name__ == '__main__':
    main()
