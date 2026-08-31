# -*- coding: utf-8 -*-
"""V8 L3c: retry_needed 7槽定向修复
- V8-002 (14/15), V8-022 (19/18): 字数差1, 手工改 (读上下文补/删1字)
- V8-010~014 x5: 撞复读「笔刷沿/沿焊缝」——教程核心词天然重复, 教学段落改措辞
  (换说法: 描一遍/刷过去/走一遭/涂画), 保持字数对位
"""
import json, re

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-v8'

FIX = {
    'V8-002': '在材质图层里新建个普通绘制图层',   # 15字
    'V8-010': '选中鱼鳞笔刷刷过去就成了',          # 12→13? 数一下
    'V8-011': '选中那笔刷描画即可搞定',            # 12
    'V8-012': '顺着焊缝涂画便能速成此技',          # 12
    'V8-013': '描一道便成',                        # 5? 原6
    'V8-014': '你只需拿笔刷顺着焊缝轻轻涂一遍',    # 15? 原17
    'V8-022': '掌握这套参数可出顶级金属质感',      # 15? 原18
}

def cc(t):
    return len(re.sub(r'[^0-9\u4e00-\u9fff.]', '', t))

filled = json.load(open(f'{BASE}/research/slots_v8_filled.json', encoding='utf-8'))
by_id = {f['id']: f for f in filled}
for sid, new in FIX.items():
    f = by_id[sid]
    print(f"{sid}: {f['chars']}字槽 <- 「{new}」{cc(new)}字 {'OK' if cc(new) == f['chars'] else 'MISMATCH'}")
    if cc(new) == f['chars']:
        f.update(new_text=new, got_chars=cc(new), mode='tts')
        f.pop('fail_reason', None)

json.dump(filled, open(f'{BASE}/research/slots_v8_filled.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
n_t = sum(1 for f in filled if f['mode'] == 'tts' and f.get('got_chars') == f['chars'])
n_k = sum(1 for f in filled if f['mode'] == 'keep_original')
print(f"\n对位 {n_t} + keep {n_k} / 29槽")
