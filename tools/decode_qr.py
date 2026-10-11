# -*- coding: utf-8 -*-
import glob, os, io
import pypdfium2 as pdfium
import cv2
import numpy as np

out = 'qr_images'
os.makedirs(out, exist_ok=True)
f = sorted(glob.glob('*.pdf'))[0]
pdf = pdfium.PdfDocument(f)
det = cv2.QRCodeDetector()
for pi in range(len(pdf)):
    page = pdf[pi]
    pil = page.render(scale=3).to_pil().convert('RGB')
    arr = np.array(pil)
    ok, decoded, pts, _ = det.detectAndDecodeMulti(arr)
    if ok and decoded:
        print('page', pi + 1)
        for d in decoded:
            if d:
                print('   QR:', d)
    # also save page image if any code found
pil = pdf[6].render(scale=3).to_pil()
pil.save(os.path.join(out, 'page7.png'))
print('saved page7.png')
