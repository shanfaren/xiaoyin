"""验证音频模型请求、现代语音凭证与格式边界，不进行外部调用。"""
import copy
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from backend.config import DEFAULTS, _env_override
from backend.adapters.asr import ASRClient
from backend.adapters.errors import UpstreamError


class ASRAudioTests(unittest.TestCase):
    def cfg(self):
        cfg=copy.deepcopy(DEFAULTS)
        cfg['llm']['primary']['api_key']='test-only-not-real'
        cfg['asr'].update(provider='ark_audio',enabled=True,base_url='https://example.invalid/v3',
                          model='doubao-seed-2-1-lite-260915',credential_source='llm.primary')
        with patch.dict(os.environ,{},clear=True):
            return _env_override(cfg)

    def test_existing_key_reference_and_audio_request(self):
        cfg=self.cfg()
        self.assertEqual(cfg['asr']['api_key'],cfg['llm']['primary']['api_key'])
        with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps({
            'choices':[{'message':{'content':'竹节虫为什么像树枝？'}}]}).encode())) as opened:
            result=ASRClient(cfg).transcribe(b'fake-wav-test','wav')
        self.assertEqual(result['text'],'竹节虫为什么像树枝？')
        request=opened.call_args[0][0]
        body=json.loads(request.data)
        self.assertNotIn('test-only-not-real',request.data.decode())
        self.assertEqual(body['messages'][-1]['content'][0]['input_audio']['format'],'wav')
        self.assertEqual(body['model'],'doubao-seed-2-1-lite-260915')

    def test_unsupported_format_never_sent_upstream(self):
        with patch('urllib.request.urlopen') as opened:
            with self.assertRaises(UpstreamError):
                ASRClient(self.cfg()).transcribe(b'test','webm')
        opened.assert_not_called()

    def test_modern_speech_key_does_not_require_app_id(self):
        cfg=self.cfg()
        cfg['asr'].update(provider='volcengine',app_id='')
        ASRClient(cfg)._guard()


if __name__=='__main__':
    unittest.main()
