# -*- coding: utf-8 -*-
"""L3 原型 step1: 从 align_dump.json 程序化构建 LLM 语义切分 prompt"""
import json

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2/research'
d = json.load(open(f'{BASE}/align_dump.json'))

# 全片字符流 (带段号锚点)
lines = []
for si, s in enumerate(d['segments']):
    ws = [w for w in (s.get('words') or []) if w.get('start')]
    if not ws: continue
    chars = ''.join(w['word'] for w in ws)
    lines.append(f"SEG{si}\t{ws[0]['start']:.2f}\t{ws[-1]['end']:.2f}\t{chars}")

open(f'{BASE}/l3_input_segs.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('\n'.join(lines))
print(f"\n共 {sum(len(l.split(chr(9))[3]) for l in lines)} 字 -> l3_input_segs.txt")
