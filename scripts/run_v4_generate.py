# -*- coding: utf-8 -*-
"""v4 执行全流程：①裁参考音频 → ②切原声视频 → ③TTS 5段 → ④打包配对
编排稿 v4（5 改写 + 5 原声保留），参考音频重裁（用户已删旧目录）
"""
import os, sys, json, time, subprocess, shutil, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

FF = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
VOCALS = r"D:\AI-tool\vocal-sep-server\output\dahua_master_vocals.wav"   # 纯人声母带（127s 全片）
SRC = r"E:\tmp\大话西游素材_raw.mp4"                                      # 源视频
REF_DIR = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\input\参考音频"
OUT = r"D:\AI-tool\组合包_大话西游测试_v4"
API = "http://127.0.0.1:8188"
os.makedirs(REF_DIR, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# v4 编排稿（时间轴=音频转写校准，字数=机器校验全PASS）
# action: rewrite=TTS改写 / keep=原声保留
SEGS = {
 "A": {"role":"至尊宝","emo":"深情","t":[54,63],  "tgt":"紫霞，想在SP里做出鱼鳞焊，该从何处下手？","action":"rewrite"},
 "B": {"role":"紫霞","emo":"关切","t":[85,89],  "tgt":"这个我不懂，你可要仔细教我","action":"rewrite"},
 "C": {"role":"至尊宝","emo":"坚定","t":[90,99],  "tgt":"先新建个材质图层，再添一个绘制图层便是。","action":"rewrite"},
 "D": {"role":"至尊宝","emo":"决然","t":[100,110],"tgt":"再寻那鱼鳞焊的笔刷，沿焊缝路径勾勒描画。","action":"rewrite"},
 "E": {"role":"紫霞","emo":"担忧","t":[111,112],"tgt":None,"action":"keep"},
 "F": {"role":"至尊宝","emo":"自责","t":[113,119],"tgt":"我很是悔恨没能早些把形状颜色调对，白费了功夫","action":"rewrite"},
 "G": {"role":"紫霞","emo":"心疼","t":[120,120],"tgt":None,"action":"keep"},
 "H": {"role":"至尊宝","emo":"推脱","t":[121,123],"tgt":None,"action":"keep"},
 "I": {"role":"紫霞","emo":"试探","t":[124,125],"tgt":None,"action":"keep"},
 "J": {"role":"至尊宝","emo":"坚定","t":[126,128],"tgt":None,"action":"keep"},
}

# ══ ① 重裁参考音频（改写段 A-F 的音色+情绪参考，±0.3s 余量）══
print("══ ① 重裁参考音频（5 段改写段）══", flush=True)
for seg, m in SEGS.items():
    if m["action"] != "rewrite":
        continue
    t0, t1 = m["t"]
    s = max(0, t0 - 0.3)
    d = (t1 - t0) + 0.6
    out = os.path.join(REF_DIR, f"{seg}_{m['role']}{m['emo']}.wav")
    r = subprocess.run([FF, "-y", "-v", "error", "-i", VOCALS,
                        "-ss", str(s), "-t", str(d), "-ac", "1", "-ar", "44100", out],
                       capture_output=True, text=True)
    print(f"  {seg}_{m['role']}{m['emo']}.wav [{t0}-{t1}s] {'OK' if os.path.exists(out) else 'FAIL:'+r.stderr[-150:]}", flush=True)

# ══ ② 切原声视频片段（全部 10 段，±1.5s 冗余）══
print("\n══ ② 切原声视频片段（10 段全部，±1.5s）══", flush=True)
for seg, m in SEGS.items():
    t0, t1 = m["t"]
    cs, ce = max(0, t0 - 1.5), t1 + 1.5
    out = os.path.join(OUT, f"{seg}_{m['role']}_{m['emo']}_原声.mp4")
    r = subprocess.run([FF, "-y", "-v", "error", "-ss", str(cs), "-t", str(ce - cs),
                        "-i", SRC, "-c", "copy", out],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f"  {seg} [{cs}-{ce}s] {'OK' if os.path.exists(out) else 'FAIL:'+r.stderr[-150:]}", flush=True)

# ══ ③ TTS 生成（5 段改写）══
print("\n══ ③ TTS 生成（5 段）══", flush=True)
def build_wf(seg, text, ref, idx):
    return {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": f"参考音频/{ref}"}},
        "2": {"class_type": "IndexTTS25BaseNode", "inputs": {
            "text": text, "reference_audio": ["1", 0], "lang": "ZH",
            "duration_factor": 1.0, "do_sample_mode": "on", "temperature": 0.8,
            "top_p": 0.8, "top_k": 30, "num_beams": 3, "repetition_penalty": 10.0,
            "length_penalty": 0.0, "max_mel_tokens": 1500, "max_tokens_per_sentence": 120,
            "interval_silence_ms": 200, "text_normalization": True, "seed": 5000 + idx}},
        "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": f"test3_v4/{seg}_"}},
    }

tts_status = {}
idx = 0
for seg, m in SEGS.items():
    if m["action"] != "rewrite":
        continue
    ref = f"{seg}_{m['role']}{m['emo']}.wav"
    wf = build_wf(seg, m["tgt"], ref, idx)
    payload = json.dumps({"prompt": wf}).encode()
    req = urllib.request.Request(API + "/prompt", data=payload, headers={"Content-Type": "application/json"})
    pid = json.load(urllib.request.urlopen(req, timeout=30)).get("prompt_id")
    print(f"  [{seg}] submitted: {pid}", flush=True)
    deadline = time.time() + 300
    st = "timeout"
    while time.time() < deadline:
        try:
            h = json.load(urllib.request.urlopen(API + f"/history/{pid}", timeout=15))
            entry = h.get(pid)
            if entry:
                stt = entry.get("status", {})
                if stt.get("completed"):
                    st = "done"; break
                if stt.get("status_str") == "error":
                    for mm in stt.get("messages", []):
                        if mm[0] == "execution_error":
                            st = "error:" + str(mm[1].get("exception_message"))[:150]; break
                    break
        except Exception:
            pass
        time.sleep(5)
    tts_status[seg] = st
    print(f"    -> {seg}: {st}", flush=True)
    idx += 1
    time.sleep(2)

# ══ ④ 打包配对（视频=TTS 段也用原声视频画面，音频分开放）══
print("\n══ ④ 打包 ══", flush=True)
COMFY_OUT = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\output\test3_v4"
AUD_DIR = os.path.join(OUT, "TTS音频")
KEEP_DIR = os.path.join(OUT, "原声音频片段")
os.makedirs(AUD_DIR, exist_ok=True)
os.makedirs(KEEP_DIR, exist_ok=True)

# TTS 音频从 ComfyUI output 收集（flac，按提交顺序 0-4 = A/B/C/D/F）
order = [s for s, m in SEGS.items() if m["action"] == "rewrite"]
tts_files = sorted([f for f in os.listdir(COMFY_OUT) if f.endswith('.flac')])
for i, seg in enumerate(order):
    matched = [f for f in tts_files if f.startswith(f"{i:02d}_") or f.startswith(f"{seg}_")]
    if matched:
        src = os.path.join(COMFY_OUT, matched[0])
        dst = os.path.join(AUD_DIR, f"{seg}_{SEGS[seg]['role']}_TTS.flac")
        shutil.copy2(src, dst)
        print(f"  TTS {seg}: {matched[0]} -> {os.path.basename(dst)}", flush=True)
    else:
        print(f"  TTS {seg}: 未找到输出文件!", flush=True)

# 原声保留段：从纯人声母带裁对应音频（带情绪原声，供组合/备份）
for seg, m in SEGS.items():
    if m["action"] != "keep":
        continue
    t0, t1 = m["t"]
    s = max(0, t0 - 1.0)
    d = (t1 - t0) + 2.0
    out = os.path.join(KEEP_DIR, f"{seg}_{m['role']}_{m['emo']}_原声.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", VOCALS, "-ss", str(s), "-t", str(d),
                    "-ac", "1", "-ar", "44100", out], capture_output=True)
    print(f"  原声 {seg}: {os.path.basename(out)} {'OK' if os.path.exists(out) else 'FAIL'}", flush=True)

# 清单
print("\n══ 交付清单 ══")
for root, dirs, files in os.walk(OUT):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"  {os.path.relpath(p, OUT)}  ({os.path.getsize(p)//1024}KB)")
print("\nDONE")
