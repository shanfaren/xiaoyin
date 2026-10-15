"""真实模型验收：保存原输入、入口和原始回复，不用固定回复冒充结果。"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import load_config, redact
from backend.adapters.llm import LLMClient
from backend.knowledge.prompts import build_system_prompt, build_messages
from backend.knowledge.followups import messages_for, parse_questions

CASES = [
    ('qa', '竹节虫为什么像树枝？', [], '直接解释形状和隐藏关系，不只反问'),
    ('hint', '竹节虫应该放到哪里？我还没想好。', [], '提供可观察线索，不直接报栖息地答案'),
    ('hint', '我看了，它又细又长，和旁边的小树枝很像，所以我想放在树枝上。',
     [{'role':'user','content':'竹节虫应该放到哪里？'},
      {'role':'assistant','content':'看看它的身体形状，和什么很像呢？'}], '认可实际尝试并解释，不永远让孩子猜'),
    ('qa', '我想直接知道为什么像树枝，请解释。',
     [{'role':'user','content':'竹节虫应该放在哪里？'},
      {'role':'assistant','content':'看看它的身体形状，和什么很像呢？'}], '切换到答疑后解释，不沿用此前提示策略'),
]


def main():
    cfg = load_config()
    client = LLMClient(cfg)
    if client.is_demo() or not client.is_ready():
        raise RuntimeError('验收需要已配置的真实模型，不能使用演示模式')
    records = []
    output = ROOT / 'data' / 'interaction_acceptance.json'
    for profile, question, history, criterion in CASES:
        prompt = build_system_prompt(cfg['character']['name'], 'student', profile)
        started = time.time()
        try:
            stream, meta = client.generate(build_messages(prompt, history, question))
            answer = ''.join(stream)
            real = bool(meta.get('is_real_ai'))
            record = {'profile':profile, 'question':question, 'criterion':criterion,
                      'answer':answer, 'is_real_ai':real, 'elapsed_seconds':round(time.time()-started, 2)}
            if len(records) < 3:
                suggestions, _ = client.generate(messages_for(profile, question, answer))
                record['suggested_questions'] = parse_questions(''.join(suggestions), question)
        except Exception as exc:
            record = {'profile':profile, 'question':question, 'criterion':criterion,
                      'error':redact(str(exc))}
        records.append(record)
        output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return int(any(not r.get('is_real_ai') or not r.get('answer') for r in records))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
