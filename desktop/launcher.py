# -*- coding: utf-8 -*-
"""一键启动：后端服务 + 原生悬浮窗 + 原生教师对话框。

职责（对应需求 5「退出应释放自己启动的进程和服务」）：
1. 若本机端口上已有健康的后端服务，则直接复用（不重复启动、退出时也不结束它）；
2. 否则以子进程方式启动 `python -m backend.server`，等待 /api/health 就绪；
3. 在主线程创建原生悬浮窗（置顶/拖动/左击开对话框/右击菜单/退出）；
4. 左击时在独立线程创建原生教师对话框；对话框关闭后悬浮头像收回（重新显示）；
5. 退出（右击菜单「退出森林小博士」）时：关闭对话框 → 结束自己启动的后端进程 → 清理临时文件。

用法：
    python desktop/launcher.py                 # 默认 8000 端口
    python desktop/launcher.py --port 8010 --demo
    python desktop/launcher.py --no-server --base http://127.0.0.1:8010
"""
import argparse
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, 'data', 'desktop_server.log')


class DesktopApp:
    def __init__(self, base_url, own_server=None, demo=False, open_chat=False, instance=None):
        self.base_url = base_url.rstrip('/')
        self.server_proc = own_server          # None 表示复用已有服务
        self.demo = demo
        self.dialog = None
        self.dialog_thread = None
        self.floating = None
        self._state = {'value': 'idle'}
        self._exiting = False
        self.open_chat = open_chat
        self.instance = instance

    def activate_existing(self):
        if self.dialog is not None and self.dialog.hwnd:
            self.dialog.bring_to_front()
        elif self.floating:
            self.floating.show()

    # ------------------------------------------------ 状态
    def state_provider(self):
        return self._state['value']

    def set_state(self, value):
        self._state['value'] = value

    # ------------------------------------------------ 对话框
    def open_dialog(self):
        if self.dialog is not None and self.dialog.hwnd:
            self.dialog.bring_to_front()
            if self.floating:
                self.floating.hide()
            return
        if self.dialog_thread and self.dialog_thread.is_alive():
            return

        def run_dialog():
            from chat_panel import ChatPanel
            dlg = ChatPanel(self.base_url, on_close=self._on_dialog_closed,
                                state_setter=self.set_state)
            self.dialog = dlg
            try:
                dlg.create()
            except Exception as e:
                print('[错误] 无法创建教师对话框：%s' % e)
                self.dialog = None
                self._on_dialog_closed()
                return
            dlg.run()          # 阻塞直到窗口销毁

        self.dialog_thread = threading.Thread(target=run_dialog, name='teacher-dialog', daemon=True)
        self.dialog_thread.start()
        if self.floating:
            self.floating.hide()

    def _on_dialog_closed(self):
        if self.dialog is None or not self.dialog.hwnd:
            self.dialog = None
            self.set_state('idle')
        if self.floating and not self._exiting:
            self.floating.show()      # 收回头像

    # ------------------------------------------------ 退出
    def exit_app(self):
        self._exiting = True
        try:
            if self.dialog is not None:
                self.dialog.close()
        except Exception:
            pass
        self._stop_server()

    def _stop_server(self):
        """只结束自己启动的后端进程；复用的外部服务不动。"""
        proc = self.server_proc
        if not proc:
            print('[退出] 后端服务为外部启动，未做处理。')
            return
        if proc.poll() is not None:
            return
        print('[退出] 正在停止本程序启动的后端服务（PID %d）…' % proc.pid)
        try:
            proc.terminate()
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
        except Exception as e:
            print('[退出] 停止后端服务时出现问题：%s' % e)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    # ------------------------------------------------ 主流程
    def run(self):
        from floating import FloatingWindow
        self.floating = FloatingWindow(state_provider=self.state_provider,
                                       on_open_dialog=self.open_dialog,
                                       on_exit=self.exit_app,
                                       activation_provider=self.instance.activation_requested if self.instance else None,
                                       on_activate=self.activate_existing)
        self.floating.create()
        if self.open_chat:
            self.open_dialog()
        print('[就绪] 悬浮窗已显示。左击打开教师对话框，右击打开菜单（含「退出森林小博士」）。')
        self.floating.run()
        print('[退出] 桌面端已关闭。')


def wait_health(base_url, timeout=25):
    from api_client import BackendClient, BackendError
    client = BackendClient(base_url, timeout=3)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            h = client.health()
            if h.get('ok'):
                return h
        except BackendError:
            pass
        time.sleep(0.4)
    return None


def start_server(port, demo):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    log = open(LOG_PATH, 'a', encoding='utf-8', buffering=1)
    log.write('\n===== %s 启动后端服务（端口 %d，演示模式=%s）=====\n'
              % (time.strftime('%Y-%m-%d %H:%M:%S'), port, demo))
    cmd = [sys.executable, '-u', '-m', 'backend.server', '--port', str(port)]
    if demo:
        cmd.append('--demo')
    creationflags = 0
    if os.name == 'nt':
        creationflags = 0x08000000          # CREATE_NO_WINDOW：不弹控制台
    env = dict(os.environ)
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=creationflags, env=env)
    print('[启动] 后端服务子进程 PID=%d，日志：%s' % (proc.pid, LOG_PATH))
    return proc


def main():
    ap = argparse.ArgumentParser(description='森林小博士 · Windows 桌面端（原生悬浮窗 + 教师对话框）')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--base', default=None, help='直接指定后端地址（默认 http://127.0.0.1:<port>）')
    ap.add_argument('--no-server', action='store_true', help='不启动后端，仅连接已有服务')
    ap.add_argument('--demo', action='store_true', help='以演示模式启动后端（规则回答，明确标注非真实 AI）')
    ap.add_argument('--open-chat', action='store_true', help='启动后直接展开悬浮聊天面板')
    args = ap.parse_args()

    if os.name != 'nt':
        print('本桌面端仅支持 Windows。')
        return 2
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    from single_instance import SingleInstance
    instance = SingleInstance()
    try:
        if not instance.acquire():
            instance.activate_existing()
            print('[复用] 森林小博士已在运行，已唤起现有窗口。')
            return 0
        result = _run_primary(args, instance)
    finally:
        instance.close()
    # Native window threads may linger during interpreter teardown.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(result)


def _run_primary(args, instance):
    base = args.base or ('http://127.0.0.1:%d' % args.port)
    own_proc = None

    health = wait_health(base, timeout=1.5)
    if health:
        print('[复用] 检测到已在运行的后端服务：%s（版本 %s）' % (base, health.get('version')))
    elif args.no_server:
        print('[错误] 未检测到后端服务，且指定了 --no-server。请先启动后端。')
        return 1
    else:
        own_proc = start_server(args.port, args.demo)
        health = wait_health(base, timeout=25)
        if not health:
            print('[错误] 后端服务在 25 秒内未就绪。请查看日志：%s' % LOG_PATH)
            try:
                own_proc.terminate()
            except Exception:
                pass
            return 1
        print('[就绪] 后端服务已就绪：%s' % base)

    cap = (health or {}).get('capabilities', {})
    print('       大模型：%s' % cap.get('llm', {}).get('label', '未知'))
    print('       语音识别 ASR：%s' % cap.get('asr', {}).get('label', '未知'))
    print('       语音合成 TTS：%s' % cap.get('tts', {}).get('label', '未知'))

    app = DesktopApp(base, own_server=own_proc, demo=args.demo, open_chat=args.open_chat,
                     instance=instance)
    try:
        app.run()
    except KeyboardInterrupt:
        print('\n[退出] 收到中断信号。')
    finally:
        app.exit_app()
    # Flush logs before main releases the singleton and terminates the process.
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
