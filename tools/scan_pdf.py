# -*- coding: utf-8 -*-
import glob, io
from pypdf import PdfReader

for f in glob.glob('*.pdf'):
    try:
        r = PdfReader(f)
    except Exception as e:
        print(f, 'ERR', e)
        continue
    print('####', f, len(r.pages))
    for i, p in enumerate(r.pages):
        t = p.extract_text() or ''
        if any(k in t for k in ['问卷', '二维码', 'http', '扫码', 'Qwen', 'API']):
            print('--- page', i + 1)
            for line in t.splitlines():
                if any(k in line for k in ['问卷', '二维码', 'http', '扫码', 'Qwen', 'API', '链接']):
                    print('   ', line)
