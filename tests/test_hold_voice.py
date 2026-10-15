"""测试原生按钮消息处理函数，所有窗口API均替换为模拟对象。"""
import unittest
from unittest.mock import Mock, patch
from desktop import teacher_dialog as T


class HoldVoiceTest(unittest.TestCase):
    def make_dialog(self):
        d=T.TeacherDialog.__new__(T.TeacherDialog)
        d._busy=False;d._voice_held=False;d.recording=False
        def start():d.recording=True
        d._on_voice=Mock(side_effect=start)
        d._stop_recording=Mock()
        return d

    def test_down_starts_up_stops_without_toggle(self):
        d=self.make_dialog()
        with patch.object(T.W,'user32'),patch.object(T.time,'monotonic',side_effect=[100,102]):
            d._voice_proc(1,T.W.WM_LBUTTONDOWN,0,0)
            d._voice_proc(1,T.W.WM_LBUTTONDOWN,0,0)
            self.assertEqual(d._on_voice.call_count,1)
            d._voice_proc(1,T.W.WM_LBUTTONUP,0,0)
            d._voice_proc(1,0x0215,0,0)
        d._stop_recording.assert_called_once()
        self.assertFalse(d._voice_cancelled)

    def test_short_press_is_cancelled(self):
        d=self.make_dialog()
        with patch.object(T.W,'user32'),patch.object(T.time,'monotonic',side_effect=[100,100.1]):
            d._voice_proc(1,T.W.WM_LBUTTONDOWN,0,0)
            d._voice_proc(1,T.W.WM_LBUTTONUP,0,0)
        self.assertTrue(d._voice_cancelled)


if __name__=='__main__':unittest.main()
