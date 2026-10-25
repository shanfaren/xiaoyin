"""核实已有方舟套餐能否调用官方音频理解模型，不更改聊天配置。"""
import base64
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import load_config,redact

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    cfg=load_config()['llm']['primary']
    audio=base64.b64encode((ROOT/'data'/'voice_probe.mp3').read_bytes()).decode()
    body={'model':'doubao-seed-2-1-lite-260915','messages':[{'role':'user','content':[
        {'type':'input_audio','input_audio':{'data':audio,'format':'mp3'}},
        {'type':'text','text':'只转写音频原文，不解释。'}]}],'stream':False,'max_tokens':80,'thinking':{'type':'disabled'}}
    req=urllib.request.Request(cfg['base_url'].rstrip('/')+'/chat/completions',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+cfg['api_key']})
    result={}
    try:
        with urllib.request.urlopen(req,timeout=30) as res: obj=json.load(res)
        result={'ok':True,'recognized':obj['choices'][0]['message']['content']}
    except urllib.error.HTTPError as exc:
        result={'ok':False,'status':exc.code,'error':redact(exc.read().decode('utf-8','ignore')[:700])}
    except Exception as exc:
        result={'ok':False,'error':redact(str(exc))}
    (ROOT/'data'/'ark_audio_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
