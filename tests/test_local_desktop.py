import os
import unittest
from unittest.mock import patch
import urllib.request
from tools.local_web_policy import local_web_content
from backend.adapters.network import open_request

class LocalDesktopTests(unittest.TestCase):
    def test_local_intro_waits_for_character_and_audio(self):
        from pathlib import Path
        app=local_web_content('web/app.js',Path('web/app.js').read_text(encoding='utf-8'))
        self.assertIn('forestDesktop.requestIntro',app)
        self.assertIn('Promise.resolve(S.welcomeEnvelopeLoading).then(playWelcomeVoice)',app)
        self.assertNotIn('if (audio.ended) audio.currentTime = 0;',app)
        companion=local_web_content('web/companion.js',Path('web/companion.js').read_text(encoding='utf-8'))
        self.assertIn("new CustomEvent('forest:character-ready')",companion)
        self.assertIn('ForestDesktopLayout.frame(box.width,box.height)',companion)
        self.assertNotIn('d.camera.position.z=d.camera.aspect<.50?6.5:7;',companion)
        self.assertNotIn("preferred=localStorage.getItem('forest_view_mesh')",companion)
    def test_cloud_network_path_unchanged(self):
        req=urllib.request.Request('https://ark.cn-beijing.volces.com/api/v3/models')
        with patch.dict(os.environ,{'FOREST_LOCAL_DESKTOP':'0'}),patch('urllib.request.urlopen') as call:
            open_request(req,3);call.assert_called_once_with(req,timeout=3)
    def test_only_local_official_ark_uses_direct_tls(self):
        with patch.dict(os.environ,{'FOREST_LOCAL_DESKTOP':'1'}),patch('urllib.request.build_opener') as build:
            open_request('https://ark.cn-beijing.volces.com/api/v3/models',3)
            build.return_value.open.assert_called_once()
        with patch.dict(os.environ,{'FOREST_LOCAL_DESKTOP':'1'}),patch('urllib.request.urlopen') as call:
            open_request('https://example.com/api',3);call.assert_called_once()
