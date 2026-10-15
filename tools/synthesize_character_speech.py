"""统一视频台词配音。无参数时生成官方标准试听；不接受音色/语速覆盖。"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import load_config
from backend.adapters.tts import TTSClient
from backend.voice_profile import STANDARD_TEXT, public_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--text', help='视频中的一句台词')
    source.add_argument('--text-file', type=Path, help='UTF-8台词文件')
    parser.add_argument('--output', type=Path,
                        default=ROOT/'assets/audio/森林小博士_统一标准试听.mp3')
    args = parser.parse_args()
    text = args.text_file.read_text(encoding='utf-8-sig').strip() if args.text_file else (args.text or STANDARD_TEXT)
    if not text.strip():
        parser.error('台词不能为空')
    result = TTSClient(load_config()).synthesize(text)
    if len(result['audio']) < 1000:
        raise RuntimeError('合成返回的音频过短')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.new.mp3')
    temporary.write_bytes(result['audio'])
    temporary.replace(args.output)
    args.output.with_suffix('.json').write_text(
        json.dumps(dict(public_profile(), text=text), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Unified voice audio generated: %s bytes; %s' % (len(result['audio']), public_profile()['voice']))


if __name__ == '__main__':
    main()
