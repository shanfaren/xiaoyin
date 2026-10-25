"""真实接口验收：合成提问→ASR转写→当前课堂入口回答→合成回复。"""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import load_config
from backend.adapters.asr import ASRClient
from backend.adapters.tts import TTSClient
from backend.adapters.llm import LLMClient
from backend.knowledge.prompts import build_system_prompt,build_messages

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    cfg=load_config()
    question=ASRClient(cfg).transcribe((ROOT/'data'/'voice_probe.mp3').read_bytes(),'mp3')['text']
    print('ASR:',question,flush=True)
    stream,meta=LLMClient(cfg).generate(build_messages(build_system_prompt('小隐','student','qa'),[],question))
    answer=''.join(stream)
    print('Reply:',answer,flush=True)
    audio=TTSClient(cfg).synthesize(answer)['audio']
    (ROOT/'data'/'voice_roundtrip_reply.mp3').write_bytes(audio)
    result={'asr_text':question,'answer':answer,'is_real_ai':meta.get('is_real_ai'),
            'tts_bytes':len(audio),'source':'synthetic_test_audio_not_microphone'}
    (ROOT/'data'/'voice_roundtrip_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('TTS bytes:',len(audio),flush=True)
