# -*- coding: utf-8 -*-
import email, quopri, base64, re, io, html

raw = open('2026 华大九天PyAether生态系统工具基础知识-竞赛.mhtml', 'rb').read()
msg = email.message_from_bytes(raw)
print('parts:')
for part in msg.walk():
    print('  ', part.get_content_type(), part.get('Content-Transfer-Encoding'))

best = None
for part in msg.walk():
    if part.get_content_type() == 'text/html':
        payload = part.get_payload(decode=True)
        if payload and (best is None or len(payload) > len(best)):
            best = payload

if best is None:
    raise SystemExit('no html part')

txt = best.decode('utf-8', 'ignore')
open('questionnaire_raw.html', 'w', encoding='utf-8').write(txt)
print('html bytes', len(txt))

# crude text extraction
s = re.sub(r'(?is)<(script|style).*?</\1>', ' ', txt)
s = re.sub(r'(?i)<br\s*/?>', '\n', s)
s = re.sub(r'(?i)</(p|div|li|tr|h[1-6]|td)>', '\n', s)
s = re.sub(r'<[^>]+>', ' ', s)
s = html.unescape(s)
s = re.sub(r'[ \t\xa0]+', ' ', s)
s = re.sub(r'\n\s*\n+', '\n', s)
open('questionnaire_text.txt', 'w', encoding='utf-8').write(s)
print('text bytes', len(s))
