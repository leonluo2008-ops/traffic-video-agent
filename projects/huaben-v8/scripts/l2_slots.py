# -*- coding: utf-8 -*-
"""dahua V8 L2: 正典断句 + 字流对位切槽
A = 手写正典 29 句（大话西游名场面，ASR 错字同位修正: 记忆→宝剑, 哀伤→爱上）
B = align_dump 字流 (329 字)
对位: 句子顺序拼接 == B 流（已验证），按累计字数直切
每句时间 = [首字start, 尾字end]; 能量标注源 = dahua_16k.wav
输出: research/slots_v8.json + 控制台预览
"""
import json, wave, audioop, math, re

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-v8'
ad = json.load(open(f'{BASE}/research/align_dump.json'))
words = [w for s in ad['segments'] for w in s.get('words', []) if w.get('start') is not None]
words.sort(key=lambda x: x['start'])
B = ''.join(w['word'] for w in words)

CANON = [
    '当时那把剑离我的喉咙只有0.01公分，',
    '但是四分之一炷香之后，',
    '那把剑的女主人，将会彻底的爱上我。',
    '因为我决定，说一个谎话。',
    '虽然本人生平说了无数的谎话，',
    '但是这一个，我认为是最完美的。',
    '你再往前半步，我就把你给杀了。',
    '你应该这么做，我也应该死。',
    '曾经有一份真诚的爱情放在我面前，',
    '我没有珍惜。',
    '等我失去的时候，我才后悔莫及。',
    '人世间最痛苦的事，莫过于此。',
    '你的宝剑在我的咽喉上割下去吧，',
    '不用再犹豫了。',
    '如果上天能够给我一个再来一次的机会，',
    '我会对那个女孩子说三个字。',
    '如果非要在这份爱上加个期限，',
    '我希望是一万年。',
    '那么你，怎么向你的娘子交代？',
    '所以我一定要拿回那个月光宝盒，',
    '带你一起回去跟他们说清楚。',
    '我不管别人怎么说，我，',
    '我也不怕后世会有千千万万的人对我唾骂。',
    '我一个人承担下来。',
    '你不骗我吧？',
    '但是我痛恨我自己没有本事，',
    '拿回那个月光宝盒。',
    '我，我帮你。',
    '不要太危险了，你不想想。',
]

def clean(t):
    return re.sub(r'[^0-9\u4e00-\u9fff.]', '', t)

joined = ''.join(clean(s) for s in CANON)
# 同位替换容差: 只允许 ASR 错字修正位 (宝剑↔记忆 @150-151, 爱上↔哀伤 @204-205)
ALLOWED_SUB = {150: ('宝', '记'), 151: ('剑', '忆'), 204: ('爱', '哀'), 205: ('上', '伤')}
diffs = [(i, x, y) for i, (x, y) in enumerate(zip(joined, B)) if x != y]
bad = [d for d in diffs if ALLOWED_SUB.get(d[0]) != (d[1], d[2])]
assert len(joined) == len(B) and not bad, f'正典与B流不对位: {len(joined)} vs {len(B)}, bad={bad}'

# 强弱句: 逗号结尾 = weak, 句号/问号 = strong
STRONG = '。！？!？'
WEAK = '，,、；;'

slots = []
cursor = 0
for raw in CANON:
    c = clean(raw)
    n = len(c)
    ws = words[cursor:cursor + n]
    assert len(ws) == n
    strength = 'strong' if raw.rstrip()[-1] in STRONG else 'weak'
    slots.append({
        'text': raw, 'clean': c, 'chars': n,
        'strength': strength,
        'start': round(ws[0]['start'], 2), 'end': round(ws[-1]['end'], 2),
        'dur': round(ws[-1]['end'] - ws[0]['start'], 2),
        'b_range': [cursor, cursor + n - 1],
    })
    cursor += n

# 能量标注: 原声源
wf = wave.open(f'{BASE}/research/dahua_16k.wav', 'rb')
SR, SW = wf.getframerate(), wf.getsampwidth()

def rms_db(t0, t1):
    i0, i1 = max(0, int(t0 * SR)), min(wf.getnframes(), int(t1 * SR))
    if i1 <= i0:
        return -99.0
    wf.setpos(i0)
    raw = wf.readframes(i1 - i0)
    r = audioop.rms(raw, SW)
    return 20 * math.log10(r / 32768.0) if r else -99.0

for i, s in enumerate(slots):
    s['id'] = f"V8-{i:03d}"
    if i > 0:
        g0, g1 = slots[i - 1]['end'], s['start']
        gap = round(g1 - g0, 2)
        db = rms_db(g0, g1) if gap > 0.04 else -99.0
        s['gap'] = {'gap': gap, 'db': round(db, 1),
                    'type': 'continuous' if db > -30 else ('pad' if db > -40 else 'silence')}

durs = [s['dur'] for s in slots]
covered = sum(s['b_range'][1] - s['b_range'][0] + 1 for s in slots)
print(f"槽位 {len(slots)} | B字流覆盖 {covered}/{len(B)} (100%)")
print(f"时长: min={min(durs):.1f} 中位={sorted(durs)[len(durs)//2]:.1f} max={max(durs):.1f}s")

json.dump(slots, open(f'{BASE}/research/slots_v8.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(f"落盘 slots_v8.json ({len(slots)} 槽)")
for s in slots:
    g = s.get('gap', {})
    print(f"  {s['id']} [{s['start']:7.2f}-{s['end']:7.2f}] {s['dur']:4.1f}s {s['chars']:2d}字 [{s['strength']:5s}] gap={g.get('gap','-')}s({g.get('type','')[:4]}) {s['text'][:22]}")
