# -*- coding: utf-8 -*-
"""L3 原型 step2: LLM 语义切分 -> 字符区间 -> 机械映射回字级时间戳"""
import json, os, sys

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2/research'
seg_lines = open(f'{BASE}/l3_input_segs.txt', encoding='utf-8').read().strip().split('\n')

prompt = """你是影视对白时间轴编辑。下面是《唐伯虎点秋香》对联混战片段的台词流（7 个语音段，共 437 字，无标点）。任务：把台词流切成**短语级槽位**，用于 AI 填词配音。

规则：
1. 按说话人切换、语义单元（一句话/一次插话/一声喊）切分
2. 每槽 4-15 字为宜，混战区（SEG4/SEG5 对联互怼）可细到 2-8 字
3. 输出 JSON 数组，每项 {"seg": 段号, "s0": 起始字符索引, "s1": 结束字符索引(不含), "text": 该槽文本, "spk": 推测说话人}
4. s0/s1 是该段内 0 起始的字符索引；text 必须严格等于原文切片，禁止增删改字
5. 覆盖所有字符，不留缝隙不重叠

台词流：
""" + '\n'.join(seg_lines) + """

只输出 JSON 数组，不要其他文字。"""

open(f'{BASE}/l3_prompt.txt', 'w', encoding='utf-8').write(prompt)
print(f"prompt {len(prompt)} 字 -> l3_prompt.txt")

# 调 glm-5.3 (jxgpt 本机代理, hermes-model-router 用法)
sys.path.insert(0, '/home/luo/.hermes/skills/hermes-model-router'.replace('hermes-model-router',''))
# 直接用 openai 兼容客户端打 jxgpt
try:
    from openai import OpenAI
except ImportError:
    os.system('pip install openai -q')
    from openai import OpenAI

import subprocess
# 从 hermes config 拿 glm-coding-plan 的 base_url + key (不打印 key)
cfg = subprocess.run(['grep', '-A6', 'glm-coding-plan:', '/home/luo/.hermes/config.yaml'],
                     capture_output=True, text=True).stdout
print("config glm 段:\n", cfg[:400])
