# -*- coding: utf-8 -*-
"""IP课程测试 v1：参考音色构建 + 24 cue TTS 批量生成 + A段双版本
参考策略（短cue必须用角色级整块参考）：
  至尊宝 = 本段独白 4.47-20.30s 连续（15.8s 单人声）
  紫霞   = 后半段台词拼块 85-89 / 111-112 / 124-125（同片同角色）
"""
import os, sys, json, time, subprocess, shutil, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

FF = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
VOCALS = r"D:\AI-tool\vocal-sep-server\output\dahua_master_vocals.wav"
COMFY_IN = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\input"
REF_SUB = "IP课程参考"
REF_DIR = os.path.join(COMFY_IN, REF_SUB)
OUT = r"D:\AI-tool\组合包_IP课程测试_v1"
API = "http://127.0.0.1:8188"
os.makedirs(REF_DIR, exist_ok=True)
os.makedirs(os.path.join(OUT, "TTS音频"), exist_ok=True)
os.makedirs(os.path.join(OUT, "参考音色"), exist_ok=True)

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

# ══ ① 角色级参考音色 ══
print("══ ① 构建角色参考音色 ══", flush=True)
# 至尊宝：本段独白整块（4.47-20.30，含 cue 间隙）
ref_zzb = os.path.join(REF_DIR, "至尊宝_独白整块.wav")
r = run([FF, "-y", "-v", "error", "-i", VOCALS, "-ss", "4.47", "-t", "15.83",
         "-ac", "1", "-ar", "44100", ref_zzb])
print(f"  至尊宝_独白整块: {'OK %dKB' % (os.path.getsize(ref_zzb)//1024) if os.path.exists(ref_zzb) else 'FAIL:'+r.stderr[-150:]}", flush=True)

# 紫霞：三块拼接（85-89 关切 / 111-112 担忧 / 124-125 试探）
ref_zx = os.path.join(REF_DIR, "紫霞_拼块.wav")
r = run([FF, "-y", "-v", "error", "-i", VOCALS, "-filter_complex",
         "[0]atrim=84.7:89.3,asetpts=PTS-STARTPTS[a];[0]atrim=110.7:112.3,asetpts=PTS-STARTPTS[b];[0]atrim=123.7:125.3,asetpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=0:a=1[out]",
         "-map", "[out]", "-ac", "1", "-ar", "44100", ref_zx])
print(f"  紫霞_拼块: {'OK %dKB' % (os.path.getsize(ref_zx)//1024) if os.path.exists(ref_zx) else 'FAIL:'+r.stderr[-150:]}", flush=True)

# A段原声（辨角色用，给用户听）
a_raw = os.path.join(OUT, "A_原声_辨角色用.wav")
run([FF, "-y", "-v", "error", "-i", VOCALS, "-ss", "0.77", "-t", "2.10", "-ac", "1", "-ar", "44100", a_raw])
print(f"  A_原声_辨角色用.wav: {'OK' if os.path.exists(a_raw) else 'FAIL'}", flush=True)

# ══ ② 24 cue TTS（A 段双版本）══
print("\n══ ② TTS 批量生成 ══", flush=True)
CUES = [
 ("A","紫霞","疑问",  "SP里想做鱼鳞焊从何下手？"),
 ("B","至尊宝","傲然","哼，这点小事难不倒我。"),
 ("C","至尊宝","傲然","先在材质图层里新建，"),
 ("D","至尊宝","傲然","普通绘制图层便是。"),
 ("E","至尊宝","傲然","新建好了图层之后，"),
 ("F","至尊宝","傲然","再寻那鱼鳞焊笔刷。"),
 ("G","至尊宝","傲然","下方笔刷列表自带多款，"),
 ("H","至尊宝","傲然","按需挑选即可使用。"),
 ("I","至尊宝","傲然","用法也极其简单，"),
 ("J","至尊宝","傲然","选中那款笔刷，"),
 ("K","至尊宝","傲然","沿着焊缝路径描画。"),
 ("L","紫霞","质疑",  "哼，说得轻巧。"),
 ("M","紫霞","追问",  "形态不对怎么改？"),
 ("N","至尊宝","坦然","这也难不倒我。"),
 ("O","至尊宝","坦然","右侧属性栏里，"),
 ("P","至尊宝","深情","形状颜色随意调，"),
 ("Q","至尊宝","深情","疏密分布也能改。"),
 ("R","至尊宝","深情","调完多切换，"),
 ("S","至尊宝","深情","任凭各样焊缝样式，"),
 ("T","至尊宝","深情","都能调试出来。"),
 ("U","至尊宝","高潮","想要什么效果，自然都能实现。"),
 ("V","至尊宝","高潮","你若也想学会，"),
 ("W","至尊宝","高潮","那就关注我，"),
 ("X","至尊宝","高潮","解锁更多建模知识。"),
]
REFS = {"至尊宝": f"{REF_SUB}/至尊宝_独白整块.wav", "紫霞": f"{REF_SUB}/紫霞_拼块.wav"}

def submit(text, ref, tag):
    wf = {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": ref}},
        "2": {"class_type": "IndexTTS25BaseNode", "inputs": {
            "text": text, "reference_audio": ["1", 0], "lang": "ZH",
            "duration_factor": 1.0, "do_sample_mode": "on", "temperature": 0.8,
            "top_p": 0.8, "top_k": 30, "num_beams": 3, "repetition_penalty": 10.0,
            "length_penalty": 0.0, "max_mel_tokens": 1500, "max_tokens_per_sentence": 120,
            "interval_silence_ms": 200, "text_normalization": True, "seed": 6000 + idx}},
        "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": f"ip_v1/{tag}"}},
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
                            return "err:" + str(m[1].get("exception_message"))[:120]
                    return "err:unknown"
        except Exception:
            pass
        time.sleep(4)
    return "timeout"

jobs = []
for i, (seg, role, emo, text) in enumerate(CUES):
    jobs.append((seg, role, emo, text))
jobs.append(("A", "至尊宝", "疑问_备选", CUES[0][3]))  # A 双版本

idx = 0
status = {}
for seg, role, emo, text in jobs:
    tag = f"{seg}_{role}_{emo}"
    pid = submit(text, REFS[role], tag)
    print(f"  [{tag}] {pid[:8]}", end="", flush=True)
    st = wait(pid)
    status[tag] = st
    print(f" -> {st}", flush=True)
    idx += 1
    time.sleep(1)

# ══ ③ 收集打包 ══
print("\n══ ③ 收集打包 ══", flush=True)
COMFY_OUT = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\output\ip_v1"
ok = fail = 0
for seg, role, emo, text in jobs:
    tag = f"{seg}_{role}_{emo}"
    hits = [f for f in os.listdir(COMFY_OUT) if f.startswith(tag) and f.endswith(".flac")]
    if hits:
        shutil.copy2(os.path.join(COMFY_OUT, hits[0]), os.path.join(OUT, "TTS音频", f"{tag}.flac"))
        ok += 1
    else:
        print(f"  缺失: {tag}", flush=True)
        fail += 1
shutil.copy2(ref_zzb, os.path.join(OUT, "参考音色"))
shutil.copy2(ref_zx, os.path.join(OUT, "参考音色"))

print(f"\nTTS 完成 {ok}/{len(jobs)}（fail={fail}）")
print("\n══ 交付清单 ══")
for root, dirs, files in os.walk(OUT):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"  {os.path.relpath(p, OUT)}  ({os.path.getsize(p)//1024}KB)")
print("\nALL_DONE")
