"""Check the shipped interpreter, local HTTP and real voice chain; no desktop input."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT.parent/'交付包/森林小博士—电脑本地版'
sys.path.insert(0,str(PACKAGE/'desktop'))
from api_client import BackendClient

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    runtime=PACKAGE/'runtime/python.exe'
    base='http://127.0.0.1:18195'
    log=(ROOT/'data/portable_acceptance.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([str(runtime),'-u','-m','backend.server','--port','18195'],cwd=str(PACKAGE),
        stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
    result={'interpreter':'bundled CPython 3.12','requires_installed_python':False}
    try:
        client=BackendClient(base,timeout=2)
        for _ in range(40):
            if proc.poll() is not None:raise RuntimeError('Bundled server exited; see portable_acceptance.log')
            try:
                health=client.health()
                if health.get('ok'):break
            except Exception:time.sleep(.25)
        else:raise RuntimeError('Bundled server HTTP timeout')
        result['bundled_server_health']=True
        result['voice']=health['capabilities']['tts']['voice']
        print('PASS bundled server and loopback HTTP',flush=True)
        inner="from desktop.api_client import BackendClient; assert BackendClient('"+base+"',timeout=4).health()['ok']; print('PASS bundled interpreter HTTP client')"
        checked=subprocess.run([str(runtime),'-c',inner],cwd=str(PACKAGE),capture_output=True,text=True,timeout=10,
            creationflags=0x08000000)
        assert checked.returncode==0,checked.stderr
        print(checked.stdout.strip(),flush=True)
        result['bundled_client_health']=True
        question='竹节虫为什么像树枝？'
        sample=client.tts(question)
        transcript=client.asr(sample,audio_format='mp3')['text']
        print('PASS actual ASR of synthetic test question:',transcript,flush=True)
        sid=client.create_session('teacher')
        answer,meta,error=client.chat_stream(sid,transcript,stage_id='qa')
        assert answer and not error and meta.get('model_info',{}).get('is_real_ai'),str(error)
        audio=client.tts(answer)
        assert len(audio)>1000
        (ROOT/'data/portable_acceptance_reply.mp3').write_bytes(audio)
        result.update(real_asr=True,real_llm=True,real_male_tts=True,answer_audio_bytes=len(audio),
                      audio_source='synthetic_test_not_microphone',test_session=sid)
        print('PASS actual ASR -> model -> male TTS through bundled server',flush=True)
    finally:
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        log.close()
    result['test_server_stopped']=True
    (ROOT/'data/portable_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Acceptance complete; temporary server stopped',flush=True)
