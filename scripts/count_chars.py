#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编排稿字数计算 + 元数据生成器
================================
读编排稿 md，机器计算每段原台词/目标台词字数，校验"差距≤2字"约束，
产出元数据 JSON 供下游工段（TTS 生成、裁切、打包）直接使用——
下游不再手数/目测字数。

计字规则（2026-08-16 与用户确认）：
  - 剔除标点（，。！？…、；："")与空白
  - 汉字、英文字母、数字各计 1
约束（2026-08-16 用户定标）：
  - 改写段：|目标字数 - 原字数| ≤ 2 才 PASS
  - 原声保留段：不做字数校验（不 TTS）

用法：
  python3 scripts/count_chars.py [编排稿.md] [输出.json]
  默认: docs/verification/测试二-智能编排决策.md → docs/verification/编排稿元数据.json
"""
import json
import re
import sys
from pathlib import Path

PUNCT_RE = re.compile(r'[，。！？…、；：""\'''（）()\s—\-]')
SEG_RE = re.compile(r'【片段([A-Z])】(\S+)\s+(\S+)\s+([\d\.]+)(?:-([\d\.]+))?s?')
ORIG_RE = re.compile(r'原台词：[""]([^""]+)[""]')
TARGET_RE = re.compile(r'目标台词：[""]([^""]+)[""]')
KEEP_RE = re.compile(r'原声保留')
EMO_RE = re.compile(r'情绪语境：(\S+)\s*→')


def count_chars(line: str) -> int:
    """机器计字：剔标点空白后按字符计（汉字/字母/数字各 1）。"""
    return len(PUNCT_RE.sub('', line))


def parse(md_path: Path) -> list[dict]:
    text = md_path.read_text(encoding='utf-8')
    segs = []
    # 按【片段X】切块
    blocks = re.split(r'(?=【片段)', text)
    for b in blocks:
        m = SEG_RE.search(b)
        if not m:
            continue
        seg_id, role, emo_span, t0, t1 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        orig_m = ORIG_RE.search(b)
        tgt_m = TARGET_RE.search(b)
        keep = bool(KEEP_RE.search(b))
        emo_m = EMO_RE.search(b)
        if not orig_m:
            continue  # 非台词块（如校准说明）
        orig = orig_m.group(1)
        if keep or not tgt_m:
            action, target = 'keep_original', orig
        else:
            action, target = 'rewrite', tgt_m.group(1)
        oc, tc = count_chars(orig), count_chars(target)
        diff = tc - oc
        segs.append({
            'seg_id': seg_id,
            'role': role,
            'emotion_span': emo_span,
            'time_start': float(t0),
            'time_end': float(t1) if t1 else float(t0),
            'orig_line': orig,
            'orig_chars': oc,
            'action': action,
            'target_line': target if action == 'rewrite' else None,
            'target_chars': tc if action == 'rewrite' else None,
            'char_diff': diff if action == 'rewrite' else 0,
            'emotion': emo_m.group(1) if emo_m else None,
        })
    return segs


def validate(segs: list[dict]) -> bool:
    """校验改写段字数差 ≤2；输出报告。全过返回 True。"""
    ok = True
    print(f"{'段':<4}{'角色':<10}{'处理':<14}{'原字数':>5}{'目标字数':>6}{'差':>5}  校验")
    print('-' * 62)
    for s in segs:
        if s['action'] == 'keep_original':
            print(f"{s['seg_id']:<4}{s['role']:<10}{'保留原声':<14}{s['orig_chars']:>5}{'—':>6}{'—':>5}  跳过")
        else:
            passed = abs(s['char_diff']) <= 2
            ok = ok and passed
            mark = '✓' if passed else '❌ 超2字'
            print(f"{s['seg_id']:<4}{s['role']:<10}{'TTS改写':<14}{s['orig_chars']:>5}{s['target_chars']:>6}{s['char_diff']:>+5}  {mark}")
    print('-' * 62)
    rew = [s for s in segs if s['action'] == 'rewrite']
    bad = [s['seg_id'] for s in rew if abs(s['char_diff']) > 2]
    print(f"改写段 {len(rew)} / 原声段 {len(segs)-len(rew)}；字数约束 {'全部 PASS' if not bad else 'FAIL: ' + ','.join(bad)}")
    return ok


def main():
    root = Path(__file__).resolve().parent.parent
    md = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'docs/verification/测试二-智能编排决策.md'
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root / 'docs/verification/编排稿元数据.json'

    segs = parse(md)
    if not segs:
        print('未解析到片段，检查编排稿格式'); sys.exit(1)

    ok = validate(segs)
    meta = {
        'source': str(md.relative_to(root)),
        'char_rule': '剔标点空白，汉字/字母/数字各计1',
        'constraint': '改写段 |目标字数-原字数| <= 2',
        'all_pass': ok,
        'segments': segs,
    }
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n元数据已写入: {out} ({len(segs)} 段)')
    sys.exit(0 if ok else 2)


if __name__ == '__main__':
    main()
