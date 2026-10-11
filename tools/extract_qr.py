# -*- coding: utf-8 -*-
import glob, os
import pypdfium2 as pdfium
import cv2
import numpy as np

f = glob.glob('“中国电子杯”*.pdf')[0]
pdf = pdfium.PdfDocument(f)
det = cv2.QRCodeDetector()
for pi in range(len(pdf)):
    pil = pdf[pi].render(scale=3).to_pil().convert('RGB')
    arr = np.array(pil)
    ok, decoded, pts, _ = det.detectAndDecodeMulti(arr)
    if ok and decoded and any(decoded):
        print('page', pi + 1, decoded)
        for quad in pts:
            xs = [int(p[0]) for p in quad]
            ys = [int(p[1]) for p in quad]
            pad = 20
            x0, x1 = max(0, min(xs) - pad), min(arr.shape[1], max(xs) + pad)
            y0, y1 = max(0, min(ys) - pad), min(arr.shape[0], max(ys) + pad)
            crop = arr[y0:y1, x0:x1]
            cv2.imwrite('qr_images/questionnaire_qr.png', cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
            print('saved questionnaire_qr.png', crop.shape)
