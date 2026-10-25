# -*- coding: utf-8 -*-
"""桌面端集成测试：原生悬浮窗 + 教师对话框 + 退出释放进程。

覆盖（对应需求 8 的桌面验证项）：
- 悬浮窗是真正的原生窗口（HWND / 分层 / 置顶 / 不占任务栏），默认右下角
- 拖动：投递 WM_LBUTTONDOWN → WM_MOUSEMOVE×N → WM_LBUTTONUP，验证窗口随之移动
- 左击（按下/抬起且未移动）→ 打开教师对话框；对话框为原生控件窗口
- 关闭对话框后悬浮头像收回（重新显示）
- 右击 → 弹出原生菜单（窗口类 #32768）
- 退出（菜单「退出小隐」）→ launcher 退出，且**自己启动的后端服务被结束**（端口关闭）

关于输入方式：自动化环境下系统可能拦截鼠标注入（mouse_event 不投递），
因此本测试通过**等价的原生窗口消息**（WM_LBUTTONDOWN / WM_MOUSEMOVE / WM_RBUTTONUP 等）
直接投递给窗口——这验证的是窗口自身的消息处理与窗口管理逻辑；
真实鼠标/触控手感需在教师机上人工实测（见 docs/05_测试记录.md 的待测项）。

运行：python tests/test_desktop.py [--port 8011]
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'desktop'))
sys.path.insert(0, ROOT)

import win32ui as W  # noqa: E402

user32 = W.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CANCELMODE = 0x001F
VK_ESCAPE = 0x1B

FLOAT_CLASS = 'XiaoyinFloating'
DIALOG_CLASS = 'XiaoyinTeacherDialog'
MENU_CLASS = '#32768'
IDM_EXIT = 1004
IDM_RESET_POS = 1003

RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))


def find_window(cls, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = user32.FindWindowW(cls, None)
        if h:
            return h
        time.sleep(0.3)
    return None


def window_rect(h):
    r = W.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def lparam(x, y):
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def post_mouse(hwnd, msg, x=10, y=10, wparam=0):
    user32.PostMessageW(hwnd, msg, wparam, lparam(x, y))


def send_mouse(hwnd, msg, x=10, y=10, wparam=0):
    user32.SendMessageW(hwnd, msg, wparam, lparam(x, y))


def do_drag(hwnd, dx, dy, steps=5):
    """通过原生鼠标消息模拟拖动：按下 → 多次移动 → 抬起。"""
    start_x, start_y = window_rect(hwnd)[:2]
    send_mouse(hwnd, WM_LBUTTONDOWN, 10, 10, 1)
    for i in range(1, steps + 1):
        current_x, current_y = window_rect(hwnd)[:2]
        send_mouse(hwnd, WM_MOUSEMOVE,
                   start_x + 10 + int(dx * i / steps) - current_x,
                   start_y + 10 + int(dy * i / steps) - current_y, 1)
        time.sleep(0.02)
    send_mouse(hwnd, WM_LBUTTONUP, 10, 10, 0)
    time.sleep(0.3)


def do_click(hwnd):
    """按下/抬起且不移动 → 视为单击（打开对话框）。"""
    post_mouse(hwnd, WM_LBUTTONDOWN, 10, 10, 1)
    time.sleep(0.1)
    post_mouse(hwnd, WM_LBUTTONUP, 10, 10, 0)
    time.sleep(0.4)


def do_right_click(hwnd):
    post_mouse(hwnd, WM_RBUTTONDOWN, 10, 10, 2)
    time.sleep(0.1)
    post_mouse(hwnd, WM_RBUTTONUP, 10, 10, 0)


def dismiss_menu(menu):
    """关闭弹出菜单（避免阻塞 launcher 的模态菜单循环）。"""
    if not menu:
        return
    user32.PostMessageW(menu, WM_KEYDOWN, VK_ESCAPE, 0)
    time.sleep(0.15)
    user32.PostMessageW(menu, WM_KEYUP, VK_ESCAPE, 0)
    time.sleep(0.3)
    if user32.IsWindow(menu):
        user32.PostMessageW(menu, WM_CANCELMODE, 0, 0)
        time.sleep(0.3)


WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E


def remote_set_text(hwnd, text):
    """跨进程设置控件文本。

    使用系统消息 WM_SETTEXT（< WM_USER，由系统负责字符串编组），
    因此不需要在目标进程中分配内存；GetWindowText/SetWindowText 对
    其他进程的控件不可靠（返回空），故一律用 SendMessage。
    """
    buf = ctypes.create_unicode_buffer(text)
    user32.SendMessageW(hwnd, WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p).value)
    time.sleep(0.2)


def remote_get_text(hwnd):
    n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if n <= 0:
        return ''
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.SendMessageW(hwnd, WM_GETTEXT, n + 1, ctypes.cast(buf, ctypes.c_void_p).value)
    return buf.value


def get_text(hwnd):
    return remote_get_text(hwnd)


def child_classes(hwnd):
    out = []

    @WNDENUMPROC
    def cb(h, lp):
        buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(h, buf, 128)
        out.append(buf.value)
        return True
    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def port_open(port, host='127.0.0.1'):
    s = socket.socket()
    s.settimeout(1.0)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8011)
    args = ap.parse_args()
    port = args.port
    py = sys.executable

    print('=' * 70)
    print(' 桌面端集成测试（原生悬浮窗 / 教师对话框 / 退出释放进程）')
    print('=' * 70)

    # 清理历史窗口位置记忆，确保验证“默认右下角”
    ui_state = os.path.join(ROOT, 'data', 'desktop_ui.json')
    if os.path.isfile(ui_state):
        os.remove(ui_state)

    log_path = os.path.join(ROOT, 'data', 'desktop_test_launcher.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, 'w', encoding='utf-8')
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env.pop('DEEPSEEK_API_KEY', None)     # 以“未配置真实密钥”的状态验证
    env.pop('ARK_API_KEY', None)
    proc = subprocess.Popen(
        [py, '-u', os.path.join(ROOT, 'desktop', 'launcher.py'), '--port', str(port), '--demo'],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
    print('[启动] launcher PID=%d，端口 %d' % (proc.pid, port))

    try:
        hwnd = find_window(FLOAT_CLASS, timeout=45)
        record('悬浮窗已创建（FindWindow 找到原生窗口）', bool(hwnd), hwnd)
        if not hwnd:
            return 1

        ex = int(user32.GetWindowLongPtrW(hwnd, W.GWL_EXSTYLE) or 0)
        record('悬浮窗为置顶窗口（WS_EX_TOPMOST）', bool(ex & W.WS_EX_TOPMOST))
        record('悬浮窗为分层窗口（WS_EX_LAYERED 逐像素透明）', bool(ex & W.WS_EX_LAYERED))
        record('悬浮窗不显示在任务栏（WS_EX_TOOLWINDOW）', bool(ex & W.WS_EX_TOOLWINDOW))
        record('悬浮窗可见', bool(user32.IsWindowVisible(hwnd)))

        l, t, r, b = window_rect(hwnd)
        wl, wt_, wr, wb = W.get_work_area()
        record('默认停靠在工作区右下角（距右边/下边 < 120px）',
               (wr - r) < 120 and (wb - b) < 120 and r <= wr + 2 and b <= wb + 2,
               '窗口=%s 工作区=%s' % ((l, t, r, b), (wl, wt_, wr, wb)))
        record('后端服务已就绪（端口监听）', port_open(port), port)

        # ---- 拖动 ----
        before = window_rect(hwnd)[:2]
        do_drag(hwnd, -160, -120)
        after = window_rect(hwnd)[:2]
        record('拖动生效（原生鼠标消息驱动窗口移动）',
               abs(after[0] - before[0] + 160) <= 6 and abs(after[1] - before[1] + 120) <= 6,
               '%s -> %s' % (before, after))

        # ---- 左击打开对话框 ----
        do_click(hwnd)
        dlg = find_window(DIALOG_CLASS, timeout=15)
        record('左击打开教师对话框（原生窗口已创建）', bool(dlg), dlg)
        if dlg:
            time.sleep(2.0)
            classes = child_classes(dlg)
            combos = classes.count('ComboBox')
            edits = classes.count('Edit')
            buttons = classes.count('Button')
            statics = classes.count('Static')
            record('对话框包含原生控件（2 下拉框 / 2 文本框 / ≥7 按钮）',
                   combos >= 2 and edits >= 2 and buttons >= 7,
                   'combo=%d edit=%d button=%d static=%d' % (combos, edits, buttons, statics))
            record('对话框可见', bool(user32.IsWindowVisible(dlg)))
            record('打开对话框时悬浮头像已隐藏（收起状态）',
                   not user32.IsWindowVisible(hwnd))

            # ---- 对话框内实际发送一条中文消息（流式回答） ----
            ID_INPUT, ID_SEND, ID_PLAY, ID_TRANSCRIPT = 2005, 2006, 2009, 2004
            inp = user32.GetDlgItem(dlg, ID_INPUT)
            trans = user32.GetDlgItem(dlg, ID_TRANSCRIPT)
            record('可通过控件 ID 定位输入框与对话区', bool(inp) and bool(trans))
            if inp and trans:
                remote_set_text(inp, '猫头鹰为什么躲在树上就看不见了？')
                time.sleep(0.3)
                user32.PostMessageW(dlg, W.WM_COMMAND, ID_SEND, 0)
                time.sleep(6.0)
                text = get_text(trans)
                record('对话框内中文提问已发出并显示在对话区', '猫头鹰' in text)
                record('对话框内收到流式回答（非空）',
                       ('小隐' in text or '演示' in text or '树' in text) and len(text) > 60,
                       '对话区长度=%d' % len(text))
                record('回答明确标注非真实 AI（演示模式）', '非真实' in text or '演示' in text)

                # ---- 播放控制：TTS 未配置时必须明确提示，而不是静默失败 ----
                user32.PostMessageW(dlg, W.WM_COMMAND, ID_PLAY, 0)
                time.sleep(3.0)
                text2 = get_text(trans)
                record('TTS 未配置时给出明确提示（不伪造播放）',
                       '语音合成未配置' in text2 or '缺少参数' in text2,
                       text2[-120:].replace('\r\n', ' / '))

            user32.PostMessageW(dlg, W.WM_CLOSE, 0, 0)
            time.sleep(1.5)
            record('收起面板后窗口隐藏且保留会话',
                   bool(user32.IsWindow(dlg)) and not user32.IsWindowVisible(dlg))
            record('关闭对话框后悬浮头像收回（重新可见）',
                   bool(user32.IsWindowVisible(hwnd)))
        else:
            record('对话框控件检查', False, '对话框未创建')

        # ---- 右击菜单 ----
        do_right_click(hwnd)
        menu = find_window(MENU_CLASS, timeout=6)
        record('右击弹出原生菜单（窗口类 #32768）', bool(menu), menu)
        dismiss_menu(menu)

        # ---- 菜单「回到右下角」 ----
        user32.PostMessageW(hwnd, W.WM_COMMAND, IDM_RESET_POS, 0)
        time.sleep(0.8)
        l3, t3, r3, b3 = window_rect(hwnd)
        record('菜单「回到右下角」生效', (wr - r3) < 120 and (wb - b3) < 120, (l3, t3, r3, b3))

        # ---- 退出：释放进程与服务 ----
        print('\n[退出测试] 发送菜单退出命令（WM_COMMAND IDM_EXIT）…')
        user32.PostMessageW(hwnd, W.WM_COMMAND, IDM_EXIT, 0)
        exited = False
        t0 = time.time()
        while time.time() - t0 < 25:
            if proc.poll() is not None:
                exited = True
                break
            time.sleep(0.3)
        record('退出后 launcher 进程结束（无残留）', exited, 'exit=%s' % proc.poll())
        time.sleep(1.2)
        record('退出后后端服务已释放（端口关闭）', not port_open(port), 'port %d' % port)
        record('退出后悬浮窗已销毁', not user32.IsWindow(hwnd))

    finally:
        try:
            log.close()
        except Exception:
            pass
        if proc.poll() is None:
            print('[清理] 强制结束 launcher 进程')
            proc.terminate()
            time.sleep(0.8)
            if proc.poll() is None:
                proc.kill()
        try:
            if os.path.isfile(ui_state):
                os.remove(ui_state)
        except Exception:
            pass

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r['ok'])
    print('\n' + '=' * 70)
    print(' 汇总：%d/%d 通过' % (passed, total))
    for r in RESULTS:
        if not r['ok']:
            print('  未通过：%s -> %s' % (r['name'], r['detail']))
    print('=' * 70)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
