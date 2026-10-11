# -*- coding: utf-8 -*-
import glob, os, io
import pypdfium2 as pdfium
import cv2
import numpy as np

out = 'qr_images'
os.makedirs(out, exist_ok=True)
det = cv2.QRCodeDetector()
for f in sorted(glob.glob('*.pdf')):
    pdf = pdfium.PdfDocument(f)
    print('####', f, len(pdf))
    for pi in range(len(pdf)):
        pil = pdf[pi].render(scale=3).to_pil().convert('RGB')
        arr = np.array(pil)
        ok, decoded, pts, _ = det.detectAndDecodeMulti(arr)
        if ok and decoded:
            for d in decoded:
                if d:
                    print('  page', pi + 1, 'QR:', d)
print('done')
