"""只发送合成的测试语音，用已有语音凭证验证ASR权限，不输出凭证。"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import load_config, redact
from backend.adapters.tts import TTSClient
from backend.adapters.asr import ASRClient


def main():
    cfg=load_config()
    result={}
    try:
        res=TTSClient(cfg).synthesize('竹节虫为什么像树枝？')
        audio=res['audio']
        (ROOT/'data'/'voice_probe.mp3').write_bytes(audio)
        result.update(tts_ok=True,audio_bytes=len(audio))
        print(json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        result.update(tts_ok=False,error=redact(str(exc)))
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return 1
    test=copy.deepcopy(cfg)
    test['asr'].update(provider='volcengine',enabled=True,
        base_url='https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash',
        resource_id='volc.bigasr.auc_turbo',model='bigmodel',app_id='',api_key=cfg['tts'].get('api_key',''))
    try:
        transcription=ASRClient(test).transcribe(audio,'mp3')
        result.update(asr_with_existing_speech_key=True,recognized=transcription['text'])
    except Exception as exc:
        result.update(asr_with_existing_speech_key=False,error=redact(str(exc)))
    (ROOT/'data'/'voice_probe_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
