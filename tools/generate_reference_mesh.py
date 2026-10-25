"""Use the official public TRELLIS.2 demo for a synthetic modeling reference.

No original video, private configuration, or credentials are sent.
Respect guest quotas and authentication requirements; no retries around limits.
"""
from pathlib import Path
import json
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-cache' / '3d-tools'))
from gradio_client import Client, handle_file


def wait(job, label):
    last = None
    while not job.done():
        status = job.status()
        code = str(status.code)
        if code != last:
            print(label, code, flush=True)
            last = code
        time.sleep(5)
    return job.result()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    out = ROOT / 'data' / 'trellis_outputs'
    out.mkdir(exist_ok=True)
    client = Client('https://microsoft-trellis-2.hf.space', verbose=False,
                    download_files=str(out))
    client.predict(api_name='/start_session')
    print('Preprocessing synthetic character reference', flush=True)
    processed = client.predict(handle_file(str(ROOT / 'data/video_reference/explorer_3d_reference.png')),
                                api_name='/preprocess_image')
    print('Preprocessing complete', type(processed).__name__, flush=True)
    (out / 'processed-result.json').write_text(json.dumps(processed), encoding='utf-8')
    result = wait(client.submit(handle_file(processed), seed=73541, resolution='1024',
                  api_name='/image_to_3d'), 'Shape and texture generation')
    (out / 'preview.html').write_text(str(result), encoding='utf-8')
    print('Extracting mobile GLB', flush=True)
    paths = wait(client.submit(decimation_target=100000, texture_size=2048,
                              api_name='/extract_glb'), 'GLB extraction')
    paths = list(paths) if isinstance(paths, (list, tuple)) else [paths]
    mesh = next(Path(p) for p in paths if isinstance(p, str) and p.endswith('.glb'))
    shutil.copy2(mesh, out / 'forest-explorer.glb')
    print('GLB ready', (out / 'forest-explorer.glb').stat().st_size, flush=True)
