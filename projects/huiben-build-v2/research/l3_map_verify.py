# -*- coding: utf-8 -*-
"""L3 原型 step2: LLM 语义切分 -> 机械映射回字级时间戳 + 质量验证"""
import json, os, time

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2/research'

prompt = open(f'{BASE}/l3_prompt.txt', encoding='utf-8').read()

from openai import OpenAI
client = OpenAI(base_url='https://open.bigmodel.cn/api/coding/paas/v4',
                api_key=os.environ['ZAI_API_KEY'])

# glm-5.3-flash 长输出易空回 — 逐段调用降载 + 重试
def ask_llm(user_prompt, retries=3):
    import time as _t
    for attempt in range(retries):
        t0 = _t.time()
        try:
            r = client.chat.completions.create(
                model='glm-5.3-flash',
                messages=[{'role': 'user', 'content': user_prompt}],
                temperature=0.2, max_tokens=4000, timeout=120)
            out = r.choices[0].message.content or ''
            if out.strip():
                print(f"  LLM ok {len(out)} chars {_t.time()-t0:.0f}s (attempt {attempt+1})")
                return out
            print(f"  LLM 空回 {_t.time()-t0:.0f}s (attempt {attempt+1})")
        except Exception as e:
            print(f"  LLM 异常: {type(e).__name__}: {str(e)[:120]} (attempt {attempt+1})")
        _t.sleep(3)
    return ''

seg_lines = open(f'{BASE}/l3_input_segs.txt', encoding='utf-8').read().strip().split('\n')
all_slots = []
HDR = """你是影视对白时间轴编辑。把下面的台词段切成**短语级槽位**（用于 AI 填词配音）。
规则：按说话人切换、语义单元切分；每槽 4-15 字，快节奏互怼可 2-8 字；
输出 JSON 数组，每项 {"s0": 起始索引, "s1": 结束索引(不含), "text": 原文切片, "spk": 推测说话人}；
s0/s1 是段内 0 起始字符索引；text 必须严格等于原文切片，禁止增删改字；覆盖全段不留缝不重叠。
只输出 JSON 数组。

"""
import json as _json
for line in seg_lines:
    parts = line.split('\t')
    seg_no, t0s, t1s, text = parts[0], parts[1], parts[2], parts[3]
    print(f"{seg_no} ({len(text)}字)...")
    out = ask_llm(HDR + f"{seg_no}: {text}")
    if not out:
        print("  !! 跳过(空回)"); continue
    import re as _re
    m = _re.search(r'\[.*\]', out, _re.S)
    if not m:
        print("  !! 无JSON, 跳过"); continue
    try:
        sl = _json.loads(m.group(0))
    except Exception as e:
        print(f"  !! JSON解析失败: {e}"); continue
    for x in sl:
        x['seg'] = int(seg_no[3:])
    all_slots.extend(sl)
    print(f"  -> {len(sl)} 槽")

print(f"\n共 {len(all_slots)} 槽")


# 机械映射: seg 内字符索引 -> 字级时间戳
d = json.load(open(f'{BASE}/align_dump.json'))
seg_words = {}
for si, s in enumerate(d['segments']):
    ws = [w for w in (s.get('words') or []) if w.get('start')]
    if ws: seg_words[si] = ws

n_ok, n_bad = 0, 0
result = []
for sl in all_slots:
    si, s0, s1 = sl['seg'], sl['s0'], sl['s1']
    ws = seg_words.get(si)
    if ws is None or s0 >= len(ws) or s1 > len(ws) or s1 <= s0:
        sl['valid'] = False; n_bad += 1; continue
    src = ''.join(w['word'] for w in ws[s0:s1])
    if src != sl['text']:
        sl['valid'] = False; sl['src'] = src; n_bad += 1
        print(f"  MISMATCH seg{si}[{s0}:{s1}] llm={sl['text']!r} src={src!r}")
        continue
    sl['valid'] = True; n_ok += 1
    sl['start'] = round(ws[s0]['start'], 3)
    sl['end'] = round(ws[s1-1]['end'], 3)
    sl['dur'] = round(sl['end'] - sl['start'], 3)
    sl['scores'] = [round(w['score'], 3) for w in ws[s0:s1]]
    result.append(sl)

# 覆盖完整性: 每段字符应被不重叠覆盖
from collections import defaultdict
cover = defaultdict(list)
for sl in result:
    cover[sl['seg']].append((sl['s0'], sl['s1']))
print("\n覆盖检查:")
for si in sorted(cover):
    ivs = sorted(cover[si]); total_len = len(seg_words[si])
    covered = sum(e-s for s, e in ivs)
    # 重叠检查
    overlap = 0
    for i in range(1, len(ivs)):
        if ivs[i][0] < ivs[i-1][1]: overlap += 1
    print(f"  SEG{si}: {len(ivs)}槽 覆盖{covered}/{total_len}字 重叠{overlap}")

print(f"\n有效槽 {n_ok} / 无效 {n_bad} (v6 slots_v3=56)")
print("\n=== 混战区 128-165s ===")
for sl in sorted(result, key=lambda x: x['start']):
    if sl.get('end', 0) >= 128 and sl.get('start', 0) <= 165:
        print(f"  [{sl['start']:7.2f}-{sl['end']:7.2f}] {sl['dur']:5.2f}s {len(sl['text']):2d}字 {sl.get('spk','?'):6s} {sl['text']}")

json.dump(result, open(f'{BASE}/slots_v7_l3.json', 'w'), ensure_ascii=False, indent=1)
print(f"\n落盘 slots_v7_l3.json")
