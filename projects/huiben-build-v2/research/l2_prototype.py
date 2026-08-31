# -*- coding: utf-8 -*-
"""
v7 L2 短语聚合 v2: 标点解映射 + 停顿 + 能量三信号
v1 教训: 段层退化后 (7 大段), 段内标点没映射到字流 → 混战区切不开
v2 方案: 段 text 去标点得到字序列, 与 words 对齐 (顺序一致), 标点位置回填到字索引
  边界 = 停顿(GAP) 或 标点(强标点 。！？；切 / 弱标点 ，、：不单独切, 需叠加停顿)
  能量验证: 强边界处测 dB, 分真静默/垫乐/连读
"""
import json, wave, audioop, math, re

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2/research'
GAP_STRONG = 0.40   # 停顿即切
GAP_WEAK   = 0.25   # 弱停顿, 叠加弱标点才切
SIL_TH = -35
STRONG_P = '。！？；!?；'
WEAK_P   = '，、：,:'

d = json.load(open(f'{BASE}/align_dump.json'))
words = []
for s in d['segments']:
    ws = [w for w in (s.get('words') or []) if w.get('start') is not None and w.get('score', 0) > 0]
    if not ws: continue
    # 段文本去标点 → 字序列 (保留标点位置信息)
    chars = []
    for ch in s['text']:
        if ch in STRONG_P: chars.append(('P', 'strong'))
        elif ch in WEAK_P: chars.append(('P', 'weak'))
        elif ch.strip(): chars.append(('C', ch))
    seq = [c for c in chars if c[0] == 'C']
    # 与 words 对齐 (长度可能不等 — Whisper 中文 words 即逐字)
    punct_after = {}  # word_index -> ('strong'|'weak', punct_char)
    if len(seq) == len(ws):
        ci = 0
        for kind, v in chars:
            if kind == 'C':
                ci += 1
            else:
                punct_after[max(0, ci-1)] = (v, True)
        for i, w in enumerate(ws):
            words.append({'t': w['word'], 's': w['start'], 'e': w['end'], 'sc': w['score'],
                          'punct': punct_after.get(i)})
    else:
        # 长度不匹配 (罕见): 只用停顿
        for w in ws:
            words.append({'t': w['word'], 's': w['start'], 'e': w['end'], 'sc': w['score'], 'punct': None})

words.sort(key=lambda x: x['s'])
matched = sum(1 for w in words if w['punct'] is not None or True)
n_punct = sum(1 for w in words if w['punct'])
print(f"字流 {len(words)} 字, 带标点注记 {n_punct} 字")

wf = wave.open(f'{BASE}/tangbohu_16k.wav', 'rb')
SR, SW = wf.getframerate(), wf.getsampwidth()
def rms_db(t0, t1):
    i0, i1 = max(0, int(t0*SR)), min(wf.getnframes(), int(t1*SR))
    if i1 <= i0: return -99.0
    wf.setpos(i0); raw = wf.readframes(i1-i0)
    r = audioop.rms(raw, SW)
    return 20*math.log10(r/32768.0) if r else -99.0

# 切分
phrases, cur, cuts = [], [words[0]], []
for i in range(1, len(words)):
    prev, w = words[i-1], words[i]
    gap = w['s'] - prev['e']
    pu = prev.get('punct')
    ptype = pu[0] if pu else None
    cut, why = False, ''
    if gap >= GAP_STRONG: cut, why = True, f'gap{gap:.2f}'
    elif gap >= GAP_WEAK and ptype: cut, why = True, f'gap{gap:.2f}+{ptype}标点'
    elif ptype == 'strong': cut, why = True, f'强标点({gap:.2f})'
    if cut:
        e_db = rms_db(prev['e'], w['s'])
        etype = 'silence' if e_db <= SIL_TH else ('pad' if e_db <= -20 else 'continuous')
        cuts.append({'at': round((prev['e']+w['s'])/2, 2), 'gap': round(gap, 3), 'why': why,
                     'e_db': round(e_db, 1), 'etype': etype,
                     'ctx': (prev['t'], w['t'])})
        phrases.append(cur); cur = [w]
    else:
        cur.append(w)
phrases.append(cur)

def summarize(pl):
    return [{'text': ''.join(x['t'] for x in p), 'start': round(p[0]['s'], 2), 'end': round(p[-1]['e'], 2),
             'dur': round(p[-1]['e']-p[0]['s'], 2), 'chars': len(p),
             'avg_score': round(sum(x['sc'] for x in p)/len(p), 3),
             'tail_punct': (p[-1].get('punct') or ('weak','，'))[0]} for p in pl]

ph = summarize(phrases)
from collections import Counter
print(f"切分 {len(cuts)} 刀 → {len(ph)} 短语 (v6=56槽 参照)")
print("切分原因:", Counter(c['why'].split('+')[0].rstrip('0123456789.强标点（') or '标点' for c in cuts))
print("边界能量:", Counter(c['etype'] for c in cuts))
durs = [p['dur'] for p in ph]
print(f"时长: min={min(durs):.2f} 中位={sorted(durs)[len(durs)//2]:.2f} max={max(durs):.2f}s; 超长>6s: {sum(1 for x in durs if x>6)}")

print("\n=== 混战区 128-165s ===")
for p in ph:
    if p['end'] >= 128 and p['start'] <= 165:
        print(f"  [{p['start']:7.2f}–{p['end']:7.2f}] {p['dur']:5.2f}s {p['chars']:2d}字 sc={p['avg_score']:.2f} {p['text'][:24]}")

print("\n=== 全片短语表 (首16) ===")
for p in ph[:16]:
    print(f"  [{p['start']:7.2f}–{p['end']:7.2f}] {p['dur']:5.2f}s {p['chars']:2d}字  {p['text'][:26]}")

json.dump({'phrases': ph, 'cuts': cuts, 'meta': {'words': len(words), 'cuts': len(cuts),
           'phrase_count': len(ph), 'v6_reference': 56}}, open(f'{BASE}/phrases_v7.json', 'w'),
          ensure_ascii=False, indent=1)
print(f"\n落盘: {BASE}/phrases_v7.json")
