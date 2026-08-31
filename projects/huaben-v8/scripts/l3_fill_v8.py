# -*- coding: utf-8 -*-
"""dahua V8 L3b v2: 全槽 LLM 填词 (v7 slot_filler 同构)
输入: research/slots_v8.json (29 槽, 新时间轴 5.79-125.97s)
输出: research/slots_v8_filled.json

修正 v1 教训: 24 段已验证台词是旧时间轴(前51s)产物, 与新29槽不同轨, 硬映射字数全崩。
v2 回归 v7 正道: 逐槽 LLM 生成, 内容源 = 鱼鳞焊知识结构 (K1-K4+CTA),
说话人按正典剧情硬归属 (紫霞=质疑方, 至尊宝=教学方)。

KEEP: V8-017「我希望是一万年」7字/15.3s 哭腔长音, 表演依赖句铁律保原声。
角色参考段: L4 用 素材/zhizunbao.mp3 + zixia.mp3 全局参考 (v7 复盘改进项1)。
"""
import json, os, re, time
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH = os.path.join(BASE, 'research')

# 说话人按正典剧情归属 (0=至尊宝独白 1-7, 紫霞威胁 6-7? 见下)
# 剧情: 0-5 至尊宝独白 | 6 紫霞(你再往前半步) 7 至尊宝(你应该这么做我也应该死)
#       8-17 至尊宝独白(曾经有一份...一万年) | 18 紫霞(怎么向你的娘子交代)
#       19-23 至尊宝(月光宝盒) | 24 紫霞(你不骗我吧) 25-26 至尊宝(痛恨没本事)
#       27 紫霞(我我帮你) 28 至尊宝(不要太危险了)
SPK = {6: '紫霞', 18: '紫霞', 24: '紫霞', 27: '紫霞'}

# 鱼鳞焊知识结构 → 台词方向池 (按教学顺序)
TEACH_FLOW = [
    '开场亮活:鱼鳞焊我悟了/这点小事难不倒我',
    'K1新建:材质图层里新建普通绘制图层',
    'K2寻笔刷:下方笔刷列表自带鱼鳞焊笔刷,按需挑选',
    'K3用法:选中笔刷沿焊缝路径描画,极其简单',
    'K4属性:右侧属性栏调形状颜色/疏密分布',
    'K4调试:多切换参数,各样焊缝样式都能调出',
    'CTA:想要什么效果都能实现,关注解锁更多建模知识',
    '紫霞质疑向:说得轻巧/形态不对怎么改/真的这么简单/画得歪歪扭扭',
]

KEEP_ID = 'V8-017'


def char_count(t):
    return len(re.sub(r'[^0-9\u4e00-\u9fff.]', '', t))


def dup_trigrams(texts):
    cnt = Counter()
    for t in texts:
        c = re.sub(r'[^\u4e00-\u9fff]', '', t)
        for i in range(len(c) - 2):
            cnt[c[i:i + 3]] += 1
    return {g for g, n in cnt.items() if n > 2}


def build_prompt(slot, spk, before_new, after_orig, teach, evidence=''):
    n = slot['chars']
    ev = f'\n上一次尝试被驳回, 证据: {evidence}\n请修正后重新给出。' if evidence else ''
    persona = ('紫霞(质疑方): 吐槽至尊宝说得轻巧, 追问细节, 傲娇口气'
               if spk == '紫霞' else '至尊宝(教学方): 自信从容, 古风混现代术语的口气')
    return f"""你是短视频台词二创填词师。原片是大话西游名场面, 改成 SP(Substance Painter) 鱼鳞焊教程双人对话。
说话人: {persona}
教学进度方向: {teach}
前文已定稿新台词: {before_new or '(本片开头)'}
后文原台词(仅作衔接参考): {after_orig or '(无)'}
原句(第{slot['id']}槽, 需替换): {slot['clean']}
要求:
1. 写一句全新台词, 口语化, 贴合上下文衔接, 内容围绕教学进度方向
2. 严格{n}个汉字(不含标点)
3. 不用原句里的词; 跟前文已定稿新台词不重复、不撞梗
4. 只输出新句本身, 一行, 无引号无解释{ev}"""


def main():
    slots = json.load(open(os.path.join(RESEARCH, 'slots_v8.json'), encoding='utf-8'))
    log = open(os.path.join(RESEARCH, 'l3_fill_run.log'), 'w', encoding='utf-8')

    from openai import OpenAI
    env = {}
    for ln in open(os.path.expanduser('~/.hermes/.env'), encoding='utf-8'):
        ln = ln.strip()
        if '=' in ln and not ln.startswith('#'):
            k, v = ln.split('=', 1)
            env[k.strip()] = v.strip()
    client = OpenAI(base_url='https://ollama.com/v1', api_key=env['OLLAMA_API_KEY'])
    models = ['deepseek-v4-flash:0731', 'gemma4:31b-cloud']

    def ask(prompt, retries=4):
        mt = 800
        last = ''
        for attempt in range(retries):
            model = models[attempt % len(models)]
            try:
                r = client.chat.completions.create(model=model, messages=[{'role': 'user', 'content': prompt}],
                                                   max_tokens=mt, temperature=0.85)
                msg = r.choices[0].message
                content = (msg.content or '').strip()
                reasoning = getattr(msg, 'reasoning_content', None) or ''
                if content:
                    return content.split('\n')[0].strip(), model
                if reasoning:
                    mt *= 2
                    last = f'reasoning_burned({len(reasoning)})'
                    continue
                last = f'empty({model})'
            except Exception as e:
                last = f'{type(e).__name__}:{str(e)[:60]}'
            time.sleep(1.5)
        return '', f'FAIL:{last}'

    filled = []
    used = []
    for i, s in enumerate(slots):
        if s['id'] == KEEP_ID:
            filled.append({**s, 'mode': 'keep_original', 'new_text': s['clean'], 'spk': ''})
            used.append(s['clean'])
            print(f"{s['id']} KEEP (表演依赖句 7字/15.3s)")
            continue
        spk = SPK.get(i, '至尊宝')
        before_new = ' / '.join(used[-5:])
        after_orig = ' / '.join(x['clean'] for x in slots[i + 1:i + 3])
        # 教学进度: 按位置推进 (紫霞槽用质疑池)
        teach = TEACH_FLOW[7] if spk == '紫霞' else TEACH_FLOW[min(i * 7 // 28, 6)]
        raw, m = ask(build_prompt(s, spk, before_new, after_orig, teach))
        got = char_count(raw)
        filled.append({**s, 'mode': 'tts', 'new_text': raw, 'spk': spk, 'got_chars': got, 'model': m})
        used.append(raw)
        print(f"{s['id']} {got:2d}/{s['chars']:2d} {'OK ' if got == s['chars'] else 'FIX'} [{spk}] {raw}")
        log.write(f"{s['id']} {got}/{s['chars']} [{spk}] {raw}\n")

    # 校验器: 字数 + 复读
    def validate(items):
        fails = {}
        for it in items:
            if it['mode'] != 'tts':
                continue
            if it.get('got_chars') != it['chars']:
                fails[it['id']] = f"字数 {it.get('got_chars')}/{it['chars']}"
        dups = dup_trigrams([it['new_text'] for it in items if it['mode'] == 'tts'])
        if dups:
            for it in items:
                if it['mode'] != 'tts':
                    continue
                c = re.sub(r'[^\u4e00-\u9fff]', '', it['new_text'])
                hit = [g for g in dups if g in c]
                if hit:
                    fails.setdefault(it['id'], f"撞复读 {','.join(hit[:3])}")
        return fails

    fails = validate(filled)
    print(f"\n=== Pass A FAIL {len(fails)} ===")

    # Pass B: 带证据重试 2 轮
    for rnd in range(2):
        if not fails:
            break
        print(f"--- Pass B round {rnd + 1}: {len(fails)} fails ---")
        for f in filled:
            if f['id'] not in fails:
                continue
            i = int(f['id'].split('-')[1])
            spk = SPK.get(i, '至尊宝')
            others = [x['new_text'] for x in filled if x['mode'] == 'tts' and x['id'] != f['id']]
            before_new = ' / '.join(others[-5:])
            after_orig = ' / '.join(x['clean'] for x in slots[i + 1:i + 3])
            teach = TEACH_FLOW[7] if spk == '紫霞' else TEACH_FLOW[min((i + rnd * 3) * 7 // 28, 6)]
            raw, m = ask(build_prompt(f, spk, before_new, after_orig, teach, evidence=fails[f['id']]))
            got = char_count(raw)
            f.update(new_text=raw, got_chars=got, model=m)
            print(f"  retry {f['id']}: {got}/{f['chars']} [{m}] {raw}")
        fails = validate(filled)

    for f in filled:
        if f['mode'] == 'tts' and f['id'] in fails:
            f['mode'] = 'retry_needed'
            f['fail_reason'] = fails[f['id']]

    json.dump(filled, open(os.path.join(RESEARCH, 'slots_v8_filled.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    n_t = sum(1 for f in filled if f['mode'] == 'tts')
    n_k = sum(1 for f in filled if f['mode'] == 'keep_original')
    n_r = sum(1 for f in filled if f['mode'] == 'retry_needed')
    n_ok = sum(1 for f in filled if f['mode'] == 'tts' and f.get('got_chars') == f['chars'])
    print(f"\n=== FINAL: tts={n_t}(对位{n_ok}) keep={n_k} retry_needed={n_r} ===")
    log.write(f"\n=== FINAL tts={n_t} keep={n_k} retry={n_r} ===\n")
    log.close()


if __name__ == '__main__':
    main()
