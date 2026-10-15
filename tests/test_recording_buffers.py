"""模拟录音设备写入，不操作麦克风或桌面；验证两秒之后的音频仍被保存。"""
import ctypes
import unittest
from unittest.mock import patch, Mock
from desktop import win32ui as W


class RecordingBuffersTest(unittest.TestCase):
    def setUp(self):
        self.device = Mock()
        for name in ('waveInOpen', 'waveInPrepareHeader', 'waveInAddBuffer',
                     'waveInStart', 'waveInStop', 'waveInReset',
                     'waveInUnprepareHeader', 'waveInClose'):
            getattr(self.device, name).return_value = 0
        self.patcher = patch.object(W, 'winmm', self.device)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_sixty_seconds_queued_and_late_sentence_preserved(self):
        recorder = W.WaveInRecorder(max_seconds=60)
        recorder.start()
        self.assertEqual(sum(h.dwBufferLength for h in recorder._headers), 16000*2*60)
        expected = bytearray()
        # 8秒连续语音，最后半秒不足整块；后面未录到的缓冲不得补成静音。
        for i in range(16):
            content = bytes([i+1]) * (8000 if i < 15 else 4000)
            ctypes.memmove(recorder._headers[i].lpData, content, len(content))
            recorder._headers[i].dwBytesRecorded = len(content)
            expected.extend(content)
        self.assertEqual(recorder.stop(), bytes(expected))
        recorder.close()

    def test_no_recorded_bytes_returns_empty_audio(self):
        recorder = W.WaveInRecorder()
        recorder.start()
        self.assertEqual(recorder.stop(), b'')
        recorder.close()

    def test_preview_reads_completed_buffers_without_stopping_device(self):
        recorder = W.WaveInRecorder()
        recorder.start()
        for index in range(8):
            ctypes.memmove(recorder._headers[index].lpData, bytes([index+1])*8000, 8000)
            recorder._headers[index].dwBytesRecorded=8000
            recorder._headers[index].dwFlags=1 if index < 7 else 0
        self.assertEqual(len(recorder.snapshot()), 7*8000)
        self.device.waveInStop.assert_not_called()
        self.assertTrue(recorder._recording)
        self.assertEqual(len(recorder.stop()), 8*8000)
        recorder.close()

    def test_buffer_failure_does_not_silently_limit_recording(self):
        self.device.waveInAddBuffer.side_effect = [0, 0, 1]
        recorder = W.WaveInRecorder()
        with self.assertRaises(RuntimeError):
            recorder.start()
        self.assertFalse(recorder._opened)
        self.assertEqual(recorder._buffers, [])
        self.device.waveInReset.assert_called()


if __name__ == '__main__':
    unittest.main()
