# -*- coding: utf-8 -*-
"""
v7 L2 v4: 全文 difflib 对齐 (v3 教训: 两 ASR 错字版本不同, 窗口搜索失效)
  A = transcribe_dump 全文 (带标点) — 语义/标点来源
  B = align_dump 字流 (429字) — 时间戳来源
  difflib 全局单调对齐 → A 的每个标点映射到 B 的字符边界 → 槽位切分
"""
import json, wave, audioop, math, re, difflib

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2/research'

td = json.load(open(f'{BASE}/transcribe_dump.json'))
ad = json.load(open(f'{BASE}/align_dump.json'))

# A: 带标点全文 + 字符出处追踪
A_chars = []  # (char, sent_idx, char_idx_in_sent)
for si, s in enumerate(td):
    for ci, ch in enumerate(s['text']):
        if ch.strip():
            A_chars.append((ch, si, ci))
A = ''.join(c[0] for c in A_chars)

# B: 字流
words = []
for s in ad['segments']:
    for w in (s.get('words') or []):
        if w.get('start') is not None and w.get('score', 0) > 0:
            words.append(w)
words.sort(key=lambda x: x['start'])
B = ''.join(w['word'] for w in words)

print(f"A (标点版) {len(A)} 字 | B (字流) {len(B)} 字")
sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
ratio = sm.ratio()
print(f"全文相似度: {ratio:.3f}")

# 映射: A 索引 -> B 索引 (equal blocks 建立, 非匹配区用插值)
a2b = {}
for ab, bb, size in sm.get_matching_blocks():
    for k in range(size):
        a2b[ab+k] = bb+k
# 插值填洞 (单调)
def aidx_to_bidx(i):
    if i in a2b: return a2b[i]
    # 就近线性插值
    lo = max(j for j in a2b if j < i) if any(j < i for j in a2b) else None
    hi = min(j for j in a2b if j > i) if any(j > i for j in a2b) else None
    if lo is None and hi is None: return None
    if lo is None: return a2b[hi]
    if hi is None: return a2b[lo]
    return a2b[lo] + round((a2b[hi]-a2b[lo]) * (i-lo)/(hi-lo))

# 槽位: 句内强标点切 (同 v3) + 弱标点在混战区也切
STRONG = '。！？!？'
WEAK = '，,、；;'
def split_units(text):
    units, cs = [], 0
    for i, ch in enumerate(text):
        if ch in STRONG or ch in WEAK:
            seg = text[cs:i+1]
            clean = re.sub(r'[，。！？；、：,!?;:\s]', '', seg)
            if clean: units.append({'raw': seg, 'clean': clean, 'strength': 'strong' if ch in STRONG else 'weak'})
            cs = i+1
    if cs < len(text):
        seg = text[cs:]
        clean = re.sub(r'[，。！？；、：,!?;:\s]', '', seg)
        if clean: units.append({'raw': seg, 'clean': clean, 'strength': 'strong'})
    return units

# 每个 A 单元 -> B 区间 -> 时间戳
slots = []
b_cursor = 0
for si, s in enumerate(td):
    units = split_units(s['text'])
    # 句内字符偏移 -> 全局 A 索引
    offset = sum(1 for prev in td[:si] for ch in prev['text'] if ch.strip())
    for u in units:
        # A 中区间
        a0 = offset
        a1 = offset + len(u['clean']) - 1
        offset += len(u['clean'])
        b0 = aidx_to_bidx(a0); b1 = aidx_to_bidx(a1)
        if b0 is None or b1 is None or b1 <= b0:
            continue
        # 单调修正 (严格不重叠: 下一槽从上一槽末字+1 开始)
        b0 = max(b0, b_cursor)
        if b1 <= b0: continue
        ws = words[b0:b1+1]
        if not ws: continue
        slots.append({
            'text': u['raw'], 'clean': u['clean'], 'chars': len(u['clean']),
            'strength': u['strength'],
            'start': round(ws[0]['start'], 2), 'end': round(ws[-1]['end'], 2),
            'dur': round(ws[-1]['end']-ws[0]['start'], 2),
            'b_range': [b0, b1],
        })
        b_cursor = b1 + 1

# 能量标注
wf = wave.open(f'{BASE}/tangbohu_16k.wav', 'rb')
SR, SW = wf.getframerate(), wf.getsampwidth()
def rms_db(t0, t1):
    i0, i1 = max(0, int(t0*SR)), min(wf.getnframes(), int(t1*SR))
    if i1 <= i0: return -99.0
    wf.setpos(i0); raw = wf.readframes(i1-i0)
    r = audioop.rms(raw, SW)
    return 20*math.log10(r/32768.0) if r else -99.0

for i, s in enumerate(slots):
    s['id'] = f"V7-{i:03d}"
    if i > 0:
        g0, g1 = slots[i-1]['end'], s['start']
        gap = round(g1-g0, 2)
        db = rms_db(g0, g1) if gap > 0.04 else -99.0
        s['gap'] = {'gap': gap, 'db': round(db,1), 'type': 'continuous' if db > -30 else ('pad' if db > -40 else 'silence')}

covered = sum(s['b_range'][1]-s['b_range'][0]+1 for s in slots)
durs = [s['dur'] for s in slots]
print(f"\n槽位 {len(slots)} (v6=56) | B字流覆盖 {covered}/{len(B)} ({100*covered/len(B):.0f}%)")
print(f"时长: min={min(durs):.1f} 中位={sorted(durs)[len(durs)//2]:.1f} max={max(durs):.1f}s")

print("\n=== 混战区 119-166s ===")
for s in slots:
    if s['end'] >= 119 and s['start'] <= 166:
        g = s.get('gap', {})
        print(f"  [{s['start']:7.2f}-{s['end']:7.2f}] {s['dur']:4.1f}s {s['chars']:2d}字 [{s['strength']}] gap={g.get('gap','-')}s({g.get('type','')[:4]}) {s['clean'][:20]}")

print("\n=== 全片首 12 槽 ===")
for s in slots[:12]:
    print(f"  [{s['start']:7.2f}-{s['end']:7.2f}] {s['dur']:4.1f}s {s['chars']:2d}字  {s['clean'][:24]}")

json.dump(slots, open(f'{BASE}/slots_v7_l2v4.json', 'w'), ensure_ascii=False, indent=1)
print(f"\n落盘 slots_v7_l2v4.json ({len(slots)} 槽)")
