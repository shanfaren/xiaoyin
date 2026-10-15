import base64
import copy
import json
import os
import unittest
from unittest.mock import patch
from backend.config import DEFAULTS, _env_override
from backend.adapters.tts import TTSClient
from backend.voice_profile import VOICE_ID, SPEECH_RATE, STYLE, STANDARD_TEXT


class VoiceProfileTest(unittest.TestCase):
    def test_stale_file_and_env_cannot_change_character_voice(self):
        cfg = copy.deepcopy(DEFAULTS)
        cfg['tts'].update(voice='old-female', speech_rate=60, context_texts=['old-style'])
        with patch.dict(os.environ, {'TTS_VOICE': 'another-female'}):
            result = _env_override(cfg)['tts']
        self.assertEqual((result['voice'], result['speech_rate'], result['context_texts']),
                         (VOICE_ID, SPEECH_RATE, [STYLE]))

    def test_request_cannot_override_voice_rate_or_style(self):
        cfg = copy.deepcopy(DEFAULTS)
        cfg['tts'].update(enabled=True, api_key='test-only', voice='bad',
                          speech_rate=90, context_texts=['bad'])
        frame = json.dumps({'code': 0, 'data': base64.b64encode(b'test-audio').decode()}).encode()
        with patch('urllib.request.urlopen') as call:
            call.return_value.__iter__.return_value = iter([frame])
            result = TTSClient(cfg).synthesize(STANDARD_TEXT, voice='female-override')
        body = json.loads(call.call_args.args[0].data)['req_params']
        self.assertEqual(body['speaker'], VOICE_ID)
        self.assertEqual(body['audio_params']['speech_rate'], SPEECH_RATE)
        self.assertEqual(body['context_texts'], [STYLE])
        self.assertEqual(body['text'], STANDARD_TEXT)
        self.assertEqual(result['voice'], VOICE_ID)


if __name__ == '__main__':
    unittest.main()
