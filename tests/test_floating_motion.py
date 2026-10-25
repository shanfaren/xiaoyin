"""Mock regression tests: real pointer paths, no native windows or mouse injection."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'desktop'))
import floating as F


class FloatingMotionTests(unittest.TestCase):
    def setUp(self):
        self.pos = [400, 300]
        self.moves = []
        self.app = object.__new__(F.FloatingWindow)
        self.app.hwnd = 123
        self.app._dragging = self.app._moved = False
        self.app.frame_idx = 0
        self.app.canvas = SimpleNamespace(update=MagicMock())
        self.app._render = MagicMock()
        self.app._save_pos = MagicMock()
        self.app.on_open_dialog = MagicMock()
        self.app.state_provider = lambda: 'idle'
        self.app.cur_state = 'idle'
        api = SimpleNamespace(SetCapture=MagicMock(), ReleaseCapture=MagicMock(),
                              ClientToScreen=self.to_screen, SetWindowPos=self.move)
        self.patches = [patch.object(F.W, 'user32', api),
                        patch.object(F.W, 'window_rect', lambda h: (*self.pos, 496, 396))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def to_screen(self, hwnd, ptr):
        ptr._obj.x += self.pos[0]
        ptr._obj.y += self.pos[1]
        return 1

    def move(self, hwnd, after, x, y, width, height, flags):
        self.pos[:] = [x, y]
        self.moves.append((x, y))
        return 1

    def event(self, msg, screen_x, screen_y):
        x, y = screen_x-self.pos[0], screen_y-self.pos[1]
        lp = (x & 0xffff) | ((y & 0xffff) << 16)
        self.app._wndproc(123, msg, 0, lp)

    def test_stable_screen_anchor_and_no_duplicate_upload(self):
        self.event(F.W.WM_LBUTTONDOWN, 420, 320)
        for i in range(1, 21):
            self.event(F.W.WM_MOUSEMOVE, 420+i*8, 320-i*3)
        self.assertEqual(self.pos, [560, 240])
        self.assertEqual(self.moves, [(400+i*8, 300-i*3) for i in range(1, 21)])
        self.app.canvas.update.assert_not_called()
        self.event(F.W.WM_LBUTTONUP, 580, 260)
        self.app.on_open_dialog.assert_not_called()

    def test_small_motion_remains_click(self):
        self.event(F.W.WM_LBUTTONDOWN, 420, 320)
        self.event(F.W.WM_MOUSEMOVE, 422, 322)
        self.assertEqual(self.moves, [])
        self.event(F.W.WM_LBUTTONUP, 422, 322)
        self.app.on_open_dialog.assert_called_once()

    def test_animation_pauses_during_drag_and_resumes(self):
        self.event(F.W.WM_LBUTTONDOWN, 420, 320)
        self.app._wndproc(123, F.W.WM_TIMER, 1, 0)
        self.assertEqual(self.app.frame_idx, 0)
        self.app._render.assert_not_called()
        self.event(F.W.WM_LBUTTONUP, 420, 320)
        self.app._wndproc(123, F.W.WM_TIMER, 1, 0)
        self.app._render.assert_called_once()

    def test_capture_loss_never_opens_dialog(self):
        self.event(F.W.WM_LBUTTONDOWN, 420, 320)
        self.app._wndproc(123, 0x0215, 0, 0)
        self.event(F.W.WM_LBUTTONUP, 420, 320)
        self.assertFalse(self.app._dragging)
        self.app.on_open_dialog.assert_not_called()


if __name__ == '__main__':
    unittest.main()
