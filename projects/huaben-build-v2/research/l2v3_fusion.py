# -*- coding: utf-8 -*-
"""
v7 L2 v3: 双 dump 融合切分 (审计后的正解)
  transcribe_dump.json (VAD 模式, 43句, 带标点, 句级时间) = 语义边界来源
  align_dump.json (batch 模式, 7段, 437字级时间戳) = 时间精度来源
  difflib 文本对齐 → 每个标点句边界落到字级时间戳 → 短语槽位
能量验证边界 (真静默/垫乐/连读) + 槽内字数/时长统计
"""
import json, wave, audioop, math, re, difflib

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2/research'

# ---- 数据源 1: transcribe_dump (带标点句) ----
td = json.load(open(f'{BASE}/transcribe_dump.json'))
punct_sents = [{'start': s['start'], 'end': s['end'], 'text': s['text']} for s in td if s.get('text','').strip()]
print(f"transcribe_dump: {len(punct_sents)} 句 (带标点)")

# 句内再按强标点细分 (。！？!) — 对联混战区一句内多次对答
def split_by_strong(sent):
    """句内强标点切分, 返回 [(char_start, char_end, text)]"""
    txt = sent['text']
    pieces, cur_s = [], 0
    for i, ch in enumerate(txt):
        if ch in '。！？!？':
            pieces.append((cur_s, i+1, txt[cur_s:i+1]))
            cur_s = i+1
    if cur_s < len(txt):
        pieces.append((cur_s, len(txt), txt[cur_s:]))
    return pieces or [(0, len(txt), txt)]

fine_units = []  # 语义单元 (短语候选)
for sent in punct_sents:
    for cs, ce, txt in split_by_strong(sent):
        clean = re.sub(r'[，。！？；、：,!?;:\s]', '', txt)
        if not clean: continue
        fine_units.append({'t_start': sent['start'], 't_end': sent['end'],
                           'c0': cs, 'c1': ce, 'raw': txt, 'clean': clean})
print(f"强标点细分: {len(fine_units)} 语义单元")

# ---- 数据源 2: align_dump (字级时间戳) ----
ad = json.load(open(f'{BASE}/align_dump.json'))
words = []
for s in ad['segments']:
    for w in (s.get('words') or []):
        if w.get('start') is not None and w.get('score', 0) > 0:
            words.append({'t': w['word'], 's': w['start'], 'e': w['end']})
words.sort(key=lambda x: x['s'])
full_stream = ''.join(w['t'] for w in words)
print(f"align_dump 字流: {len(words)} 字")

# ---- difflib 对齐: 语义单元 clean 文本 -> 字流区间 ----
stream_idx = {i: full_stream[i] for i in range(len(full_stream))}
slots = []
sm = difflib.SequenceMatcher(None, autojunk=False)
# 把所有 clean 文本拼成一条 (单元间用占位符连接) 与字流整体对齐
unit_texts = [u['clean'] for u in fine_units]
joined = '\x00'.join(unit_texts)  # \x00 不会出现在中文台词里
sm.set_seq2(joined.replace('\x00',''))
# 直接法: 逐单元在字流中顺序搜索 (单调性: 台词顺序 = 时间顺序)
cursor = 0
miss = 0
for ui, u in enumerate(fine_units):
    target = u['clean']
    # 在 [cursor, cursor+window] 内找 target (容忍错字: 找 85% 相似度的窗口)
    L = len(target)
    best, best_ratio = None, 0.0
    window_end = min(len(full_stream), cursor + L + 12)
    for try_pos in range(max(0, cursor-2), window_end - L + 1):
        cand = full_stream[try_pos:try_pos+L]
        if cand == target:
            best, best_ratio = (try_pos, try_pos+L), 1.0
            break
        r = difflib.SequenceMatcher(None, target, cand, autojunk=False).quick_ratio()
        if r > best_ratio:
            # 精确算
            r2 = difflib.SequenceMatcher(None, target, cand, autojunk=False).ratio()
            if r2 > best_ratio: best, best_ratio = (try_pos, try_pos+L), r2
    if best and best_ratio >= 0.6:
        u['w0'], u['w1'] = best
        u['ratio'] = round(best_ratio, 3)
        cursor = best[1]
        slots.append(u)
    else:
        miss += 1
        u['w0'] = u['w1'] = None

print(f"映射成功 {len(slots)}/{len(fine_units)} (miss {miss})")
ratios = [u['ratio'] for u in slots]
print(f"映射相似度: min={min(ratios):.2f} 中位={sorted(ratios)[len(ratios)//2]:.2f}")

# ---- 槽位时间戳 + 能量 ----
wf = wave.open(f'{BASE}/tangbohu_16k.wav', 'rb')
SR, SW = wf.getframerate(), wf.getsampwidth()
def rms_db(t0, t1):
    i0, i1 = max(0, int(t0*SR)), min(wf.getnframes(), int(t1*SR))
    if i1 <= i0: return -99.0
    wf.setpos(i0); raw = wf.readframes(i1-i0)
    r = audioop.rms(raw, SW)
    return 20*math.log10(r/32768.0) if r else -99.0

out_slots = []
for u in slots:
    w0, w1 = u['w0'], u['w1']
    ws = words[w0:w1]
    start, end = ws[0]['s'], ws[-1]['e']
    # 边界间隙能量 (前槽尾到本槽头)
    gap_e = None
    out_slots.append({
        'id': f"L2-{len(out_slots):03d}",
        'text': u['raw'], 'chars': len(u['clean']),
        'start': round(start, 2), 'end': round(end, 2), 'dur': round(end-start, 2),
        'map_ratio': u['ratio'],
        'src_words': [{'t': w['t'], 's': round(w['s'],2), 'e': round(w['e'],2)} for w in ws],
    })

# 间隙能量标注
for i in range(1, len(out_slots)):
    gap0, gap1 = out_slots[i-1]['end'], out_slots[i]['start']
    gap = round(gap1-gap0, 2)
    db = rms_db(gap0, gap1) if gap > 0.05 else -99.0
    etype = 'continuous' if db > -30 else ('pad' if db > -40 else 'silence')
    out_slots[i]['gap_from_prev'] = {'gap': gap, 'db': round(db,1), 'type': etype}

# 覆盖检查
covered = sum(u['w1']-u['w0'] for u in slots)
print(f"\n字流覆盖: {covered}/{len(full_stream)} ({100*covered/len(full_stream):.0f}%)")
durs = [s['dur'] for s in out_slots]
print(f"槽位: {len(out_slots)} 个 (v6=56) | 时长 min={min(durs):.1f} 中位={sorted(durs)[len(durs)//2]:.1f} max={max(durs):.1f}s")

print("\n=== 混战区 119-166s ===")
for s in out_slots:
    if s['end'] >= 119 and s['start'] <= 166:
        g = s.get('gap_from_prev', {})
        print(f"  [{s['start']:7.2f}-{s['end']:7.2f}] {s['dur']:4.1f}s {s['chars']:2d}字 r={s['map_ratio']:.2f} gap={g.get('gap','-')}({g.get('type','')}) {s['text'][:26]}")

json.dump(out_slots, open(f'{BASE}/slots_v7_l2v3.json', 'w'), ensure_ascii=False, indent=1)
print(f"\n落盘 slots_v7_l2v3.json")
