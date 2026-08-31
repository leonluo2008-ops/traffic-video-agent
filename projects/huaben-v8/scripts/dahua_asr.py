# -*- coding: utf-8 -*-
"""dahua V8 L1: WhisperX 双模式转写 (v7 验证跑法)
mode A: VAD transcribe (batch_size=None) 带标点 -> transcribe_dump.json
mode B: batch transcribe + w2v2-zh 字级对齐 -> align_dump.json
两 dump 后续由 surface 端 l2 fusion difflib 融合切槽。
"""
import os, json, time

JOBS = r"D:\AI-tool\whisperx\jobs"
BASE = os.path.join(JOBS, "dahua")
WAV = os.path.join(JOBS, "dahua_16k.wav")
W2V2 = r"D:\AI-tool\whisperx\models\w2v2-zh"

import warnings
warnings.filterwarnings("ignore")

t0 = time.time()
import whisperx
print(f"[1] whisperx imported ({time.time()-t0:.1f}s)", flush=True)

device = "cuda"

# ---- mode A: VAD 带标点 ----
t0 = time.time()
model = whisperx.load_model("large-v3", device, compute_type="float16", language="zh")
print(f"[2] large-v3 loaded ({time.time()-t0:.1f}s)", flush=True)
audio = whisperx.load_audio(WAV)
t0 = time.time()
res_a = model.transcribe(audio, batch_size=None, language="zh")
n_segs = len(res_a["segments"])
json.dump(res_a, open(os.path.join(BASE, "transcribe_dump.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
chars_a = sum(len(s["text"]) for s in res_a["segments"])
print(f"[3] mode A VAD transcribe: {n_segs} segs, {chars_a} chars ({time.time()-t0:.0f}s)", flush=True)

# ---- mode B: batch + 字级对齐 ----
t0 = time.time()
res_b = model.transcribe(audio, batch_size=8, language="zh")
model_a, metadata = whisperx.load_align_model(language_code="zh", device=device, model_dir=W2V2)
res_b = whisperx.align(res_b["segments"], model_a, metadata, audio, device,
                       return_char_alignments=False)
n_words = sum(len(s.get("words", [])) for s in res_b["segments"])
json.dump(res_b, open(os.path.join(BASE, "align_dump.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[4] mode B batch+align: {n_words} words ({time.time()-t0:.0f}s)", flush=True)

# 质量速报
scores = [w.get("score", 0) for s in res_b["segments"] for w in s.get("words", [])]
if scores:
    scores.sort()
    n = len(scores)
    print(f"[5] word score: min={scores[0]:.3f} p25={scores[n//4]:.3f} med={scores[n//2]:.3f}", flush=True)
print("DONE-V8-L1", flush=True)
