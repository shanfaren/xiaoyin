"""HTTP integration tests use fake upstreams; real model quality is checked separately."""
import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend import server, session
from backend.knowledge.followups import parse_questions


class FakeModel:
    def __init__(self):
        self.requests = []

    def is_ready(self): return True
    def is_demo(self): return False

    def generate(self, messages, cancel_check=None):
        self.requests.append(messages)
        if '只返回JSON' in messages[0]['content']:
            text = '["还可以怎么观察？", "能再给一点线索吗？", "这个发现能用在哪里？"]'
        else:
            text = '测试上游返回，仅用于接口验证。'
        return iter([text]), {'is_real_ai':False, 'provider':'test'}


class InteractionAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(session, 'DATA_DIR', self.tmp.name)
        self.data_patch.start()
        self.state = server.AppState()
        self.state.llm = FakeModel()
        self.vision_calls = []
        def vision(*args, **kwargs):
            self.vision_calls.append(kwargs)
            return '照片接口测试返回。'
        self.state.vision = SimpleNamespace(analyze=vision)
        self.state_patch = patch.object(server, 'STATE', self.state)
        self.state_patch.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        self.state_patch.stop()
        self.data_patch.stop()
        self.tmp.cleanup()

    def call(self, path, body=None, stream=False):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request('http://127.0.0.1:%d%s' % (self.http.server_port,path),
                                     data=data, headers={'Content-Type':'application/json'})
        with self.opener.open(req, timeout=5) as response:
            text = response.read().decode()
        if stream:
            return [json.loads(line[6:]) for line in text.splitlines() if line.startswith('data: ')]
        return json.loads(text)

    def create(self, selected):
        return self.call('/api/session', {'stage_id':selected})['session_id']

    def chat(self, sid, text, selected):
        return self.call('/api/chat', {'session_id':sid, 'text':text, 'stage_id':selected}, True)

    def test_exactly_two_entries_and_legacy_mapping(self):
        profiles = self.call('/api/knowledge/stages')['stages']
        self.assertEqual([p['id'] for p in profiles], ['qa','hint'])
        sid = self.create('aichat2')
        self.assertEqual(self.state.store.get(sid).stage_id, 'qa')

    def test_devices_keep_history_selection_and_clear_separate(self):
        a, b = self.create('hint'), self.create('share')
        self.assertNotEqual(a,b)
        self.chat(a, '设备A的独有观察：竹节虫像树枝', 'hint')
        self.chat(b, '设备B正在看猫头鹰', 'share')
        sent_b = json.dumps(self.state.llm.requests[-1], ensure_ascii=False)
        self.assertNotIn('设备A的独有观察', sent_b)
        self.assertIn('【当前入口：qa｜提问答疑】', sent_b)
        self.call('/api/session/%s/stage' % a, {'stage_id':'qa'})
        self.assertEqual(self.state.store.get(b).stage_id,'qa')
        self.call('/api/session/%s/clear' % a, {})
        self.assertTrue(self.state.store.get(b).messages)
        self.assertFalse(self.state.store.get(a).messages)

    def test_switch_changes_actual_prompt_and_metadata(self):
        sid = self.create('hint')
        self.chat(sid, '应该放哪里？', 'hint')
        events = self.chat(sid, '请直接解释原因', 'qa')
        self.assertIn('【当前入口：qa｜提问答疑】',self.state.llm.requests[-1][0]['content'])
        self.assertEqual(next(e for e in events if e['type']=='meta')['stage_id'], 'qa')

    def test_photo_and_followups_use_own_session_and_profile(self):
        a, b = self.create('qa'), self.create('share')
        self.call('/api/vision', {'session_id':a, 'stage_id':'hint',
                                  'image_base64':base64.b64encode(b'test').decode()})
        self.assertEqual(self.vision_calls[-1]['stage_id'],'hint')
        self.assertEqual(self.state.store.get(b).stage_id,'qa')
        result = self.call('/api/session/%s/suggestions' % a, {'stage_id':'hint'})
        self.assertEqual(len(result['questions']),2)
        count = len(self.state.llm.requests)
        self.call('/api/session/%s/suggestions' % a, {'stage_id':'hint'})
        self.assertEqual(len(self.state.llm.requests),count)
        self.assertEqual(self.call('/api/session/%s/suggestions' % b,{})['questions'],[])

    def test_malformed_followups_are_not_fixed_replacements(self):
        self.assertEqual(parse_questions('this is not JSON'),[])
        self.assertEqual(parse_questions('["我可以再看什么？", "我可以再看什么？"]'),[])


if __name__ == '__main__':
    unittest.main()
