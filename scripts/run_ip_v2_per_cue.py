# -*- coding: utf-8 -*-
"""IP课程测试 v2：逐cue参考音频（用视频精确转写整句裁，不中断）
参考策略：
  1. 视频精确转写（Gemini 分析产出）= 整句级别时间轴，情绪准确
  2. SRT cue → 映射到所属整句 → 裁整句±0.3s 作为参考
  3. 每段参考 = 完整语句，不截断不中断
  4. temperature = 0.5
"""
import os, sys, json, time, subprocess, shutil, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

FF = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
VOCALS = r"D:\AI-tool\vocal-sep-server\output\dahua_master_vocals.wav"
COMFY_IN = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\input"
REF_DIR = os.path.join(COMFY_IN, "IPv2参考")
OUT = r"D:\AI-tool\组合包_IP课程测试_v2"
API = "http://127.0.0.1:8188"
os.makedirs(REF_DIR, exist_ok=True)
os.makedirs(os.path.join(OUT, "TTS音频"), exist_ok=True)
os.makedirs(os.path.join(OUT, "参考音频"), exist_ok=True)

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

# 视频精确转写整句（来源：Gemini视频分析，全片127s，0-51s部分）
# 格式: (整句起s, 止s, 台词摘要)
# A-X cue -> 映射到所属整句的引用
TRANSCRIPT = {
  "P1": (0.0,   2.0,  "哎呀你怎么躲在这里啊"),        # A
  "P2": (3.0,   8.0,  "当时那把剑离我的喉咙只有0.01公分"),  # B,C,D
  "P3": (8.0,  14.0,  "但是四分之一柱香之后那把剑的女主人将会彻底的爱上我"),  # E,F,G
  "P4": (14.0, 17.0,  "因为我决定说一个谎话"),           # H
  "P5": (17.0, 22.0,  "虽然本人平生说了无数的谎话但是这一个我认为是最完美的"),  # I,J,K
  "P6": (23.0, 25.0,  "你再往前半步我就把你给杀了"),      # L,M
  "P7": (26.0, 31.0,  "你应该这么做我也应该死"),          # N,O
  "P8": (32.0, 39.0,  "曾经有一份真诚的爱情放在我面前我没有珍惜"),  # P,Q,R
  "P9": (39.0, 46.0,  "等我失去的时候我才后悔莫及人世间最痛苦的事莫过于此"),  # S,T,U
  "P10": (47.0, 53.0, "你的剑在我的咽喉上割下去吧不用再犹豫了"),  # V,W,X
}

# 24 cue -> 所属整句映射 + 目标台词
CUES = [
 ("A","至尊宝","P1", "紫霞！SP里鱼鳞焊，我悟了。"),
 ("B","至尊宝","P2", "哼，这点小事难不倒我。"),
 ("C","至尊宝","P2", "先在材质图层里新建，"),
 ("D","至尊宝","P2", "普通绘制图层便是。"),
 ("E","至尊宝","P3", "新建好了图层之后，"),
 ("F","至尊宝","P3", "再寻那鱼鳞焊笔刷。"),
 ("G","至尊宝","P3", "下方笔刷列表自带多款，"),
 ("H","至尊宝","P4", "按需挑选即可使用。"),
 ("I","至尊宝","P5", "用法也极其简单，"),
 ("J","至尊宝","P5", "选中那款笔刷，"),
 ("K","至尊宝","P5", "沿着焊缝路径描画。"),
 ("L","紫霞",  "P6", "哼，说得轻巧。"),
 ("M","紫霞",  "P6", "形态不对怎么改？"),
 ("N","至尊宝","P7", "这也难不倒我。"),
 ("O","至尊宝","P7", "右侧属性栏里，"),
 ("P","至尊宝","P8", "形状颜色随意调，"),
 ("Q","至尊宝","P8", "疏密分布也能改。"),
 ("R","至尊宝","P8", "调完多切换，"),
 ("S","至尊宝","P9", "任凭各样焊缝样式，"),
 ("T","至尊宝","P9", "都能调试出来。"),
 ("U","至尊宝","P9", "想要什么效果，自然都能实现。"),
 ("V","至尊宝","P10","你若也想学会，"),
 ("W","至尊宝","P10","那就关注我，"),
 ("X","至尊宝","P10","解锁更多建模知识。"),
]

# ══ ① 裁整句级参考音频（每句只裁一次，同句多cue复用）══
print("══ ① 裁整句级参考音频（视频精确转写时间轴）══", flush=True)
for pid, (t0, t1, _) in TRANSCRIPT.items():
    s = max(0, t0 - 0.3)
    d = (t1 - t0) + 0.6
    ref = os.path.join(REF_DIR, f"{pid}.wav")
    r = run([FF, "-y", "-v", "error", "-i", VOCALS, "-ss", f"{s:.2f}", "-t", f"{d:.2f}",
             "-ac", "1", "-ar", "44100", ref])
    ok = r.returncode == 0 and os.path.exists(ref)
    print(f"  {pid} [{t0:.0f}-{t1:.0f}s] {TRANSCRIPT[pid][2][:15]}... {'OK %dKB' % (os.path.getsize(ref)//1024) if ok else 'FAIL'}", flush=True)

# ══ ② TTS 逐cue生成（temp=0.5，参考=所属整句）══
print("\n══ ② TTS 逐cue生成（temp=0.5）══", flush=True)
def submit(text, ref_name, seed):
    wf = {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": f"IPv2参考/{ref_name}.wav"}},
        "2": {"class_type": "IndexTTS25BaseNode", "inputs": {
            "text": text, "reference_audio": ["1", 0], "lang": "ZH",
            "duration_factor": 1.0, "do_sample_mode": "on", "temperature": 0.5,
            "top_p": 0.8, "top_k": 30, "num_beams": 3, "repetition_penalty": 10.0,
            "length_penalty": 0.0, "max_mel_tokens": 1500, "max_tokens_per_sentence": 120,
            "interval_silence_ms": 200, "text_normalization": True, "seed": seed}},
        "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": f"ip_v2/{seed}_{text[:4]}"}},
    }
    payload = json.dumps({"prompt": wf}).encode()
    req = urllib.request.Request(API + "/prompt", data=payload, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30)).get("prompt_id")

def wait(pid, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            h = json.load(urllib.request.urlopen(API + f"/history/{pid}", timeout=15))
            e = h.get(pid)
            if e:
                st = e.get("status", {})
                if st.get("completed"):
                    return "done"
                if st.get("status_str") == "error":
                    for m in st.get("messages", []):
                        if m[0] == "execution_error":
                            return "err:" + str(m[1].get("exception_message"))[:150]
                    return "err:unknown"
        except Exception:
            pass
        time.sleep(4)
    return "timeout"

idx = 0
results = []
for seg, role, phrase_id, text in CUES:
    pid = submit(text, phrase_id, 8000 + idx)
    print(f"  [{seg}] ref={phrase_id} {pid[:8]}", end="", flush=True)
    st = wait(pid)
    results.append((seg, st))
    print(f" -> {st}", flush=True)
    idx += 1
    time.sleep(1)

# ══ ③ 收集打包 ══
print("\n══ ③ 收集打包 ══", flush=True)
COMFY_OUT = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\output\ip_v2"
ok = fail = 0
for i, (seg, role, phrase_id, text) in enumerate(CUES):
    seed = 8000 + i
    hits = [f for f in os.listdir(COMFY_OUT) if f.startswith(f"{seed}_") and f.endswith(".flac")]
    if hits:
        dst = os.path.join(OUT, "TTS音频", f"{seg}_{role}.flac")
        shutil.copy2(os.path.join(COMFY_OUT, hits[0]), dst)
        ok += 1
    else:
        print(f"  缺失: {seg}", flush=True)
        fail += 1

# 参考音频入包
for pid, (t0, t1, txt) in TRANSCRIPT.items():
    shutil.copy2(os.path.join(REF_DIR, f"{pid}.wav"), os.path.join(OUT, "参考音频", f"{pid}_{txt[:10]}s.wav"))

print(f"\nTTS {ok}/24（fail={fail}）")
print("\n══ 交付清单 ══")
for root, dirs, files in os.walk(OUT):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"  {os.path.relpath(p, OUT)}  ({os.path.getsize(p)//1024}KB)")
print("\nALL_DONE")
