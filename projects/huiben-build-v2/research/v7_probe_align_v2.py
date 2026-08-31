# -*- coding: utf-8 -*-
"""
v7 probe v2: Demucs vocals 版字级对齐 (方案B对比实验)
单变量原则: 转写文本沿用原声版 align_dump.json 的 segments (A 流不动),
仅将对齐音频换成 Demucs 分离的 vocals.wav (VideoLingo 同构: 原声ASR+净音对齐).
输出: align_dump_v2.json (不覆盖基线 align_dump.json)
"""
import os, json, time

BASE = r"D:\AI-tool\whisperx\jobs\huaben"
W2V2_MODEL = r"D:\AI-tool\whisperx\models\w2v2-zh"
OLD_DUMP = os.path.join(BASE, "align_dump.json")       # 原声版基线 (转写文本来源)
VOCALS = os.path.join(BASE, "tangbohu_vocals.wav")     # Demucs 分离人声
OUT = os.path.join(BASE, "align_dump_v2.json")

import warnings
warnings.filterwarnings("ignore")

t0 = time.time()
import whisperx
print(f"[1] whisperx imported ({time.time()-t0:.1f}s)", flush=True)

device = "cuda"

# 1) 载入原声版转写 segments (单变量: 文本不换)
with open(OLD_DUMP, encoding="utf-8") as f:
    old = json.load(f)
segments = [{"text": s["text"], "start": s["start"], "end": s["end"]}
            for s in old["segments"]]
print(f"[2] loaded {len(segments)} baseline segments (from original-audio ASR)", flush=True)

# 2) 对齐音频 = vocals (唯一变量)
t0 = time.time()
audio = whisperx.load_audio(VOCALS)
model_a, metadata = whisperx.load_align_model(language_code="zh", device=device, model_dir=W2V2_MODEL)
result = whisperx.align(segments, model_a, metadata, audio, device, return_char_alignments=False)
n_words = sum(len(s.get("words", [])) for s in result["segments"])
print(f"[3] align on VOCALS done: {n_words} word-level stamps ({time.time()-t0:.1f}s)", flush=True)

# 3) dump
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print(f"[4] dumped -> {OUT} ({os.path.getsize(OUT)} bytes)", flush=True)

# 5) 质量速报 (与基线同口径)
scores = [w.get("score", 0) for s in result["segments"] for w in s.get("words", [])]
if scores:
    scores.sort()
    n = len(scores)
    print(f"[5] word score: min={scores[0]:.3f} p25={scores[n//4]:.3f} median={scores[n//2]:.3f} p75={scores[3*n//4]:.3f} max={scores[-1]:.3f}", flush=True)
    low = sum(1 for x in scores if x < 0.5)
    print(f"    low(<0.5): {low}/{n} ({100*low/n:.1f}%)", flush=True)

# 6) 混战区样本 (119-166s)
print("\n=== 样本: 119-166s 对联混战区字级 (vocals 版) ===", flush=True)
for s in result["segments"]:
    if s["start"] >= 118 and s["start"] <= 166:
        ws = s.get("words", [])
        print(f"seg {s['start']:.2f}-{s['end']:.2f}: '{s['text'][:40]}'")
        line = " ".join(f"{w['word']}@{w['start']:.2f}" for w in ws[:14])
        if line:
            print("   " + line)
