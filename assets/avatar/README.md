# AI森林小博士·小隐 · 原创角色头像

> 角色为**完全原创**设计：圆润友好小机器人，暖白机身、森林绿外壳、发光眼睛、头顶叶片、随身放大镜。
> 不复制豆包或任何第三方平台的商标与角色形象。视觉风格取自课件（森林绿 + 暖白、自然卡通、大字号高对比）。

## 文件清单

| 文件 | 用途 |
|---|---|
| `xiaoyin_all.svg` | 四状态合并版（`<g id="state-idle|listening|thinking|speaking">`，默认显示 idle，可用 CSS/JS 切换） |
| `xiaoyin_idle.svg` `xiaoyin_listening.svg` `xiaoyin_thinking.svg` `xiaoyin_speaking.svg` | 单状态可编辑矢量图（256×256 显示，viewBox 0 0 100 100） |
| `xiaoyin_<state>.png` | 256px 透明背景 PNG（主帧） |
| `xiaoyin_<state>_f0/f1/f2.png` | 256px 动画帧（桌面悬浮窗状态动画：眨眼/声波滚动/气泡浮动/张嘴开合） |
| `xiaoyin_<state>_128/_80/_64.png` | 下采样小尺寸（网页与低分辨率场景；64–80px 下仍可辨认） |

## 四状态定义

| 状态 | 含义 | 视觉特征 |
|---|---|---|
| `idle` 待机 | 默认/空闲 | 睁眼微笑；f1 帧眨眼，f2 帧眼光晕呼吸 |
| `listening` 倾听 | 录音/识别中 | 眼睛睁大、光晕增强；嘴边三道声波弧滚动 |
| `thinking` 思考 | 模型生成中 | 眼睛上瞄；头顶灵感小星；右上思考气泡浮动 |
| `speaking` 发声 | 语音播放中 | 张嘴（含小舌）；嘴边声波；f1/f2 帧嘴部开合 |

## 重新生成

```bash
python tools/avatar_gen.py    # 纯标准库，无第三方依赖；约 25 秒
```

渲染引擎为自研 SDF 抗锯齿光栅器（`tools/avatar_raster.py`），同一场景定义同时导出 PNG 与 SVG，保证位图与矢量一致。

## 适配检查

- [x] 透明背景 PNG（RGBA，颜色类型 6）
- [x] 可编辑 SVG（原生图元：rect/circle/ellipse/path/polygon，未转路径）
- [x] 四状态齐备
- [x] 64px / 80px 下轮廓、双眼、叶片、放大镜可辨
- [x] 原创，无第三方商标元素
