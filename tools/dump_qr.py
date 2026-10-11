# -*- coding: utf-8 -*-
import glob, io, os
from pypdf import PdfReader

out = 'qr_images'
os.makedirs(out, exist_ok=True)
f = sorted(glob.glob('*.pdf'))[0]
r = PdfReader(f)
for pi in (6, 7):
    p = r.pages[pi]
    try:
        imgs = p.images
    except Exception as e:
        print('ERR', e)
        continue
    print('page', pi + 1, len(imgs))
    for j, im in enumerate(imgs):
        name = os.path.join(out, 'p%d_%d_%s' % (pi + 1, j, im.name))
        with open(name, 'wb') as fh:
            fh.write(im.data)
        print('  ', name, len(im.data))
