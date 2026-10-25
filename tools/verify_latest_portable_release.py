"""解压实际交付ZIP，以包内Python运行真实接口验收；测试数据不进入正式对话。"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT.parent/'交付包/森林小博士—电脑本地版'
CACHE=ROOT/'build-cache'
RESULT=ROOT/'data/local_release_acceptance_latest.json'

CHECK = r'''
import json,re,sys
from pathlib import Path
from desktop.api_client import BackendClient
from backend.voice_profile import STANDARD_TEXT,public_profile
client=BackendClient('http://127.0.0.1:18198',timeout=8)
health=client.health()
assert health['ok'] and health['capabilities']['tts']['profile']==public_profile()
cfg=client._request('GET','/api/client-config')[1]
assert [p['id'] for p in cfg['stages']]==['qa','hint']
result={'bundled_runtime':sys.version.split()[0],'portable_http':True,'modes':['qa','hint'],
        'voice':public_profile()['voice'],'speech_rate':public_profile()['speech_rate']}
audio=Path('assets/audio/森林小博士_统一标准试听.mp3').read_bytes()
transcript=client.asr(audio,audio_format='mp3')['text']
normalize=lambda text: ''.join(ch for ch in text if ch.isalnum())
assert normalize(transcript)==normalize(STANDARD_TEXT),transcript
result['full_standard_sentence_asr']=True
result['standard_sentence_transcript']=transcript
print('PASS full 6.6-second standard audition transcription',flush=True)
sid=client.create_session('teacher')
answer,meta,error=client.chat_stream(sid,'竹节虫为什么像树枝？',stage_id='qa')
assert answer and not error and meta['model_info']['is_real_ai']
assert meta['stage_id']=='qa'
suggestions=client.suggestions(sid,'qa')
assert len(suggestions)==2,suggestions
result.update(real_ai=True,answer=answer,suggestions=suggestions)
reply=client.tts(answer)
assert len(reply)>1000
result['real_fixed_voice_tts_bytes']=len(reply)
print('PASS actual AI answer, two follow-ups and fixed male speech',flush=True)
hint_sid=client.create_session('teacher')
hint,hint_meta,error=client.chat_stream(hint_sid,'竹节虫应该放在哪里？我还没想好。',stage_id='hint')
assert hint and not error and hint_meta['stage_id']=='hint' and hint_meta['model_info']['is_real_ai']
result['hint_answer']=hint
assert sid!=hint_sid and client.get_session(sid)['messages']!=client.get_session(hint_sid)['messages']
import desktop.chat_panel as panel
assert panel.PROFILE_IDS==('qa','hint')
result['native_modules_loaded']=True
result['separate_sessions']=True
result['physical_microphone_tested']=False
result['classroom_hardware_tested']=False
Path('acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS separate sessions, inquiry mode and native Windows UI modules',flush=True)
'''

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    CACHE.mkdir(exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='本地新版自测_',dir=str(CACHE))).resolve()
    proc=None
    try:
        archive=LOCAL/'森林小博士—电脑本地版.zip'
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for name in z.namelist():
                (temp/name).resolve().relative_to(temp)
            z.extractall(temp)
        package=temp/LOCAL.name
        manifest={str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in package.rglob('*') if p.is_file()}
        runtime=package/'runtime/python.exe'
        assert (package/'启动森林小博士—电脑本地版.exe').read_bytes()[:2]==b'MZ'
        log=ROOT/'data/local_release_acceptance_latest.log'
        with log.open('w',encoding='utf-8') as output:
            proc=subprocess.Popen([str(runtime),'-u','-m','backend.server','--port','18198'],
                cwd=str(package),stdout=output,stderr=subprocess.STDOUT,creationflags=0x08000000)
            # 使用同一个便携解释器检查HTTP，避免依赖开发机的Python环境。
            probe="from desktop.api_client import BackendClient; assert BackendClient('http://127.0.0.1:18198',timeout=1).health()['ok']"
            for _ in range(30):
                if proc.poll() is not None:raise RuntimeError('Extracted server exited; see acceptance log')
                ready=subprocess.run([str(runtime),'-c',probe],cwd=str(package),capture_output=True,timeout=4,
                                     creationflags=0x08000000)
                if ready.returncode==0:break
                time.sleep(.25)
            else:raise RuntimeError('Extracted portable server did not respond')
            tested=subprocess.run([str(runtime),'-u','-c',CHECK],cwd=str(package),
                capture_output=True,encoding='utf-8',errors='replace',timeout=160,creationflags=0x08000000)
            print(tested.stdout, end='',flush=True)
            if tested.returncode:
                raise RuntimeError('Portable acceptance failed: '+tested.stderr[-1600:])
            result=json.loads((package/'acceptance.json').read_text(encoding='utf-8'))
            result.update(release=json.loads((package/'package-info.json').read_text(encoding='utf-8'))['version'],
                          tested_from_zip=True,application_files=manifest)
            RESULT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PASS actual delivered ZIP extracted and tested using bundled Python only',flush=True)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        # 只删除本工具创建的临时解压目录；不触及交付包或正式对话数据。
        assert temp.parent==CACHE.resolve() and temp.name.startswith('本地新版自测_')
        shutil.rmtree(str(temp))

if __name__=='__main__':main()
