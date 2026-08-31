# -*- coding: utf-8 -*-
"""slot_filler.py v3 — 完整闭环填词（B 方案，用户拍板 2026-08-31）

输入: research/slots_v7_l2v4.json (76 槽)
输出: research/slots_v7_filled.json

模型: deepseek-v4-flash:0731 @ ollama-cloud（1M 上下文，实测不烧推理），
      备用 gemma4:31b-cloud。ask() 保留推理剥离防御。

闭环三段（llm-generation-pipeline 铁律）:
  Pass A 生成: 前文滑动窗口注入"已填新词"（修回 v1 丢失逻辑）+ 主题方向轮转
  校验器: 字数对位 + 复读检测（任意3字片段全片>2次 FAIL）+ 叠字结构对位
  Pass B 修复: FAIL 槽带证据重试（字数差几字/撞哪个片段/换主题方向）

v6 台词与 role 一概不复用（用户拍板）：说话人逐槽 LLM 现推。
"""
import json
import os
import re
import sys
import time
from collections import Counter

from openai import OpenAI

BASE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.join(BASE, 'research')

env = {}
for line in open(os.path.expanduser('~/.hermes/.env'), encoding='utf-8'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()

CLIENT = OpenAI(base_url='https://ollama.com/v1', api_key=env['OLLAMA_API_KEY'])
MODELS = ['deepseek-v4-flash:0731', 'gemma4:31b-cloud']

THEMES = ['油耗虚高', '马力虚标', '维权无门', '保值率崩', '加价提车', '售后套路',
          '配置减配', '质检翻车', '营销吹牛', '试驾翻车', '内饰廉价', '空间局促',
          '异响频发', '车机卡顿', '漆面薄脆', '轮胎偷工', '悬挂偏硬', '隔音拉胯']

KEEP_PAT = re.compile(r'哈+|嘿+|呵+|啊+|哦+|嗯+|哎+|唉+|呀+|哇+|额+|呃+|唉哟|哎哟'
                      r'|嗯哼|哦豁|啊这|得了|行吧|算了|完蛋|没辙|服了|绝了')


def char_count(t):
    return len(re.sub(r'[，。？！、,\.\?!~～…·\s]', '', t))


def is_reduplication(t):
    """检测叠字结构: AA 型（爹爹/宝宝）或 AABB 型（虚虚标标）"""
    c = re.sub(r'[^\u4e00-\u9fff]', '', t)
    return len(c) >= 2 and (c == c[0] * len(c) or (len(c) % 4 == 0 and len(set(c)) <= 2))


def dup_trigrams(texts):
    """全片 3 字片段复读检测: 返回出现 >2 次的片段集合"""
    cnt = Counter()
    for t in texts:
        c = re.sub(r'[^\u4e00-\u9fff]', '', t)
        for i in range(len(c) - 2):
            cnt[c[i:i + 3]] += 1
    return {g for g, n in cnt.items() if n > 2}


def ask(prompt, retries=4):
    """调 LLM，防御性剥离 reasoning 模型坑：
    content 空 + reasoning_content 非空 → 判定被推理烧尽，翻倍 max_tokens 重试。
    模型主备链轮换。"""
    mt = 800
    last_err = ''
    for attempt in range(retries):
        model = MODELS[attempt % len(MODELS)]
        try:
            r = CLIENT.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=mt, temperature=0.85,
            )
            msg = r.choices[0].message
            content = (msg.content or '').strip()
            reasoning = getattr(msg, 'reasoning_content', None) or ''
            if content:
                # 防御性剥离: 有的模型把答案尾巴拖在 reasoning 里, 正文已完整则直接用
                return content.split('\n')[0].strip(), model
            if reasoning:
                mt *= 2  # 推理烧尽, 翻倍再试
                last_err = f'reasoning_burned({len(reasoning)}字)'
                continue
            last_err = f'empty_content(model={model})'
        except Exception as e:
            last_err = f'{type(e).__name__}:{str(e)[:80]}'
        time.sleep(1.5)
    return '', f'FAIL:{last_err}'


def build_prompt(slot, before_new, before_orig, after_orig, theme, evidence=''):
    n = slot['chars']
    ev = f'\n上一次尝试被驳回, 证据: {evidence}\n请修正以上问题后重新给出新句。' if evidence else ''
    return f"""你是短视频台词二创填词师。原片是汽车吐槽向内容（吐槽某款新车）。
前文已定稿新台词: {before_new or '（本片开头）'}
前文原台词: {before_orig or '（无）'}
后文原台词: {after_orig or '（无）'}
原句(第{slot['id']}槽, 需替换): {slot['clean']}
要求:
1. 围绕"{theme}"这个方向写一句全新吐槽, 口语化有梗, 贴合上下文衔接
2. 严格{n}个汉字(不含标点)
3. 不用原句里的词; 跟前文已定稿新台词不重复、不撞梗
4. 只输出新句本身, 一行, 无引号无解释{ev}"""


def parse_answer(raw):
    """解析 '说话人|新词' 或纯新词"""
    raw = raw.strip().strip('"\'「」')
    if '|' in raw:
        parts = raw.split('|', 1)
        return parts[0].strip(), parts[1].strip()
    return '', raw


def main():
    slots = json.load(open(os.path.join(RESEARCH, 'slots_v7_l2v4.json')))
    log = open(os.path.join(RESEARCH, 'l3_fill_run.log'), 'w', encoding='utf-8')

    filled = []
    used_texts = []  # 已定稿新词（供复读检测 + 下槽上下文）

    # ---------- Pass A ----------
    for i, s in enumerate(slots):
        # keep 判定: 语气词/拟声/极短承接
        if KEEP_PAT.fullmatch(s['clean']) or s['chars'] <= 2:
            filled.append({**s, 'mode': 'keep_original', 'new_text': s['clean'], 'spk': ''})
            used_texts.append(s['clean'])
            print(f"{s['id']} KEEP")
            log.write(f"{s['id']} KEEP\n")
            continue

        before_orig = ' / '.join(x['clean'] for x in slots[max(0, i - 5):i])
        after_orig = ' / '.join(x['clean'] for x in slots[i + 1:i + 3])
        before_new = ' / '.join(used_texts[-5:])
        theme = THEMES[i % len(THEMES)]

        # 一问双答: 说话人 + 新词
        prompt = build_prompt(s, before_new, before_orig, after_orig, theme)
        prompt += "\n5. 输出格式: 说话人|新句 （说话人从'宁王/唐伯虎/旁白/车主'中选最贴合的）"
        raw, m = ask(prompt)
        spk, line = parse_answer(raw)
        got = char_count(line)
        filled.append({**s, 'mode': 'tts', 'new_text': line, 'spk': spk, 'got_chars': got, 'raw': raw, 'model': m})
        used_texts.append(line)
        print(f"{s['id']} {'OK' if got == s['chars'] else 'RETRY?'} {got}/{s['chars']} [{m}] {line}")
        log.write(f"{s['id']} {got}/{s['chars']} [{m}] spk={spk} {line}\n")
        log.flush()

    # ---------- 校验器 ----------
    def validate(items):
        fails = {}
        # ① 字数对位
        for it in items:
            if it['mode'] != 'tts':
                continue
            if it.get('got_chars') != it['chars']:
                fails[it['id']] = f"字数 {it.get('got_chars')}/{it['chars']}"
        # ② 复读检测（只查 tts 槽）
        tts_texts = [it['new_text'] for it in items if it['mode'] == 'tts']
        dups = dup_trigrams(tts_texts)
        if dups:
            for it in items:
                if it['mode'] != 'tts':
                    continue
                c = re.sub(r'[^\u4e00-\u9fff]', '', it['new_text'])
                hit = [g for g in dups if g in c]
                if hit:
                    fails.setdefault(it['id'], f"撞复读片段 {','.join(hit[:3])}")
        # ③ 叠字结构对位
        for it in items:
            if it['mode'] != 'tts':
                continue
            if is_reduplication(it['clean']) and not is_reduplication(it['new_text']):
                fails.setdefault(it['id'], '原句叠字结构, 新词未保持')
        return fails

    fails = validate(filled)
    print(f"\n=== Pass A done, FAIL {len(fails)} ===")
    log.write(f"\n=== Pass A FAIL {len(fails)}: {fails}\n")

    # ---------- Pass B: 带证据重试 ----------
    for rnd in range(2):
        if not fails:
            break
        print(f"--- Pass B round {rnd + 1}, {len(fails)} fails ---")
        idx_map = {i: s for i, s in enumerate(slots)}
        new_fails = {}
        for fi, f in enumerate(filled):
            if f['id'] not in fails:
                continue
            i = slots.index(next(x for x in slots if x['id'] == f['id']))
            before_orig = ' / '.join(x['clean'] for x in slots[max(0, i - 5):i])
            after_orig = ' / '.join(x['clean'] for x in slots[i + 1:i + 3])
            others = [x['new_text'] for x in filled if x['mode'] == 'tts' and x['id'] != f['id']]
            before_new = ' / '.join(others[-5:])
            theme = THEMES[(i + rnd * 7) % len(THEMES)]  # 换方向
            ev = fails[f['id']]
            prompt = build_prompt(f, before_new, before_orig, after_orig, theme, evidence=ev)
            prompt += "\n5. 输出格式: 说话人|新句 （说话人从'宁王/唐伯虎/旁白/车主'中选最贴合的）"
            raw, m = ask(prompt)
            spk, line = parse_answer(raw)
            got = char_count(line)
            f.update(new_text=line, spk=spk, got_chars=got, raw=raw, model=m)
            print(f"  {f['id']} retry {got}/{f['chars']} [{m}] {line}")
            log.write(f"RETRY {f['id']} r{rnd} {got}/{f['chars']} [{m}] {line}\n")
        # 重校验
        fails = validate(filled)
        print(f"--- after round {rnd + 1}: FAIL {len(fails)} ---")

    # 终态标记
    for f in filled:
        if f['mode'] == 'tts' and f['id'] in fails:
            f['mode'] = 'retry_needed'
            f['fail_reason'] = fails[f['id']]

    json.dump(filled, open(os.path.join(RESEARCH, 'slots_v7_filled.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    n_tts = sum(1 for f in filled if f['mode'] == 'tts')
    n_keep = sum(1 for f in filled if f['mode'] == 'keep_original')
    n_retry = sum(1 for f in filled if f['mode'] == 'retry_needed')
    uniq = len(set(f['new_text'] for f in filled if f['mode'] == 'tts'))
    print(f"\n=== FINAL: tts={n_tts} keep={n_keep} retry_needed={n_retry} uniq={uniq}/{n_tts} ===")
    log.write(f"\n=== FINAL tts={n_tts} keep={n_keep} retry_needed={n_retry} uniq={uniq}/{n_tts} ===\n")
    log.close()


if __name__ == '__main__':
    main()
