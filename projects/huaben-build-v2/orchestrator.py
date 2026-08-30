# -*- coding: utf-8 -*-
"""画本 v2.1 克隆合成编排器（PC 端，Windows + ComfyUI IndexTTS 2.5）
用法（ComfyUI 秋叶版 python，UTF-8 模式）:
  python -X utf8 orchestrator.py stage1   # 抽音频→demucs→裁参考件
  python -X utf8 orchestrator.py smoke    # 冒烟: 1 槽 TTS 验证节点链
  python -X utf8 orchestrator.py tts      # 全量 TTS + atempo 收口
  python -X utf8 orchestrator.py mix      # 三层混音 + 合回画面
  python -X utf8 orchestrator.py status   # 各阶段产物盘点
"""
import json, os, re, subprocess, sys, time, urllib.request, urllib.error

BASE   = r"D:\AI-tool\huaben-build-v2"
SRC    = os.path.join(BASE, "tangbohu_duichang_original.mp4")
FF     = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
FFPROBE= FF.replace("ffmpeg.exe", "ffprobe.exe")
PYC    = r"D:\AI-tool\ComfyUI-aki-v1.6\python\python.exe"   # demucs 宿主
COMFY  = "http://127.0.0.1:8188"
INPUT  = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\input"        # LoadAudio COMBO 根
# LoadAudio 的 input 参数也接受子目录相对路径（"huaben/ref_N01.wav"）——冒烟阶段验证
REF_SUB = ""  # LoadAudio 只认 input 根目录平铺文件名（子目录不在 COMBO options）
OUT_TTS = os.path.join(BASE, "tts_out")       # TTS 原始产物
OUT_FIT = os.path.join(BASE, "tts_fit")       # atempo 收口产物
OUT_MIX = os.path.join(BASE, "mix")
COMFY_PY= r"D:\AI-tool\ComfyUI-aki-v1.6\python\python.exe"
DEMUCS_ENV = dict(os.environ, HF_HOME=r"D:\AI-tool\vocal-sep-server\hf-cache")

slots = json.load(open(os.path.join(BASE, "slots.json"), encoding="utf-8"))["slots"]
TTS   = [s for s in slots if not s["keep"]]
KEEP  = [s for s in slots if s["keep"]]
runs  = json.load(open(os.path.join(BASE, "slots.json"), encoding="utf-8"))["original_track_runs"]

def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        print("CMD FAIL:", cmd, "\n", r.stdout[-500:], r.stderr[-800:]); sys.exit(1)
    return r.stdout

def probe_dur(p):
    o = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    return float(o.stdout.strip())

# ───────────────────────── stage1: 音频准备 ─────────────────────────
def stage1():
    for d in (os.path.join(BASE, "audio"), os.path.join(BASE, "refs"), OUT_TTS, OUT_FIT, OUT_MIX):
        os.makedirs(d, exist_ok=True)
    full = os.path.join(BASE, "audio", "full_audio.wav")
    if not os.path.exists(full):
        sh([FF, "-y", "-i", SRC, "-vn", "-ac", "2", "-ar", "44100", full])
    # demucs（只在缺产物时跑，GPU 2-4min）
    voc = os.path.join(BASE, "audio", "htdemucs", "full_audio", "vocals.wav")
    acc = os.path.join(BASE, "audio", "htdemucs", "full_audio", "no_vocals.wav")
    if not (os.path.exists(voc) and os.path.exists(acc)):
        sh([PYC, "-m", "demucs", "-n", "htdemucs", "--two-stems=vocals", "-o", os.path.join(BASE, "audio"), full], env=DEMUCS_ENV)
    # 裁参考件: TTS 槽自参考（±0.3s 余量，边界 clamp，短槽回退邻域）
    man = []
    for s in TTS:
        a = max(0.0, s["start"] - 0.3); b = min(181.70, s["end"] + 0.3)
        if s["dur"] < 1.5:
            a = max(0.0, s["start"] - 0.8); b = min(181.70, s["end"] + 0.8)
        name = f'ref_{s["id"]}.wav'
        sh([FF, "-y", "-i", voc, "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-ac", "1", "-ar", "44100", os.path.join(BASE, "refs", name)])
        man.append(dict(id=s["id"], role=s["role"], ref=name, start=a, end=b, ref_dur=round(b-a, 2)))
    json.dump(man, open(os.path.join(BASE, "refs_manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 原声直用区段（连音轨）+ 孤立 KEEP 槽干声
    for i, r in enumerate(runs):
        sh([FF, "-y", "-i", SRC, "-ss", f'{r["start"]-0.15:.2f}', "-to", f'{r["end"]+0.15:.2f}', "-vn", "-ac", "2", "-ar", "44100",
            os.path.join(BASE, "audio", f"orig_run_{i}_{r['first']}-{r['last']}.wav")])
    for s in KEEP:
        if not s.get("use_original_track"):
            a = max(0.0, s["start"] - 0.25); b = min(181.70, s["end"] + 0.25)
            sh([FF, "-y", "-i", voc, "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-ac", "1", "-ar", "44100",
                os.path.join(BASE, "audio", f'keep_{s["id"]}.wav')])
    print("stage1 OK: refs", len(man), "| runs", len(runs), "| keep-slices", sum(1 for s in KEEP if not s.get("use_original_track")))

# ───────────────────────── ComfyUI TTS 提交 ─────────────────────────
WF = {
  "1": {"class_type": "LoadAudio", "inputs": {"audio": ""}},
  "2": {"class_type": "IndexTTS25BaseNode", "inputs": {"text": "", "reference_audio": ["1", 0], "lang": "ZH", "duration_factor": 1.0}},
  "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": "huaben/tts"}},
}

def submit(text, ref_rel, df=1.0):
    wf = json.loads(json.dumps(WF))
    wf["1"]["inputs"]["audio"] = ref_rel  # 平铺文件名, 如 ref_N23.wav
    wf["2"]["inputs"]["text"] = text
    wf["2"]["inputs"]["duration_factor"] = df
    # 长句 max_mel_tokens 放宽（v3 实测上限 1815）
    n = len(re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text))
    if n > 40:
        wf["2"]["inputs"]["max_mel_tokens"] = 1800
    data = json.dumps({"prompt": wf, "client_id": "huaben"}).encode()
    req = urllib.request.Request(COMFY + "/prompt", data=data, headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]
    while True:
        time.sleep(2)
        h = json.loads(urllib.request.urlopen(COMFY + f"/history/{pid}", timeout=30).read())
        if pid not in h: continue
        outputs = h[pid].get("outputs", {})
        if outputs:
            for node_out in outputs.values():
                for g in node_out.get("gifs", []):   # SaveAudio 产物在 gifs 槽（实测惯例）
                    fname = g.get("filename"); sub = g.get("subfolder", ""); t = g.get("type")
                    if t == "output": return os.path.join(r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\output", sub, fname)
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            raise RuntimeError(f"prompt failed: {st}")

def gen_one(s):
    text = s["text"]
    ref_rel = f"ref_{s['id']}.wav"
    out = submit(text, ref_rel, df=s.get("df", 1.0))
    dst = os.path.join(OUT_TTS, f'gen_{s["id"]}.wav')
    sh([FF, "-y", "-i", out, "-ac", "1", "-ar", "44100", dst])
    return dst

def smoke():
    s = next(x for x in TTS if x["id"] == "N23")
    p = gen_one(s)
    print("SMOKE OK:", s["id"], text_repr(s["text"]), "->", p, round(probe_dur(p), 2), "s (slot", s["dur"], "s)")

def text_repr(t): return t if len(t) < 25 else t[:22] + "..."

def tts_all():
    man = {m["id"]: m for m in json.load(open(os.path.join(BASE, "refs_manifest.json"), encoding="utf-8"))}
    todo = [s for s in TTS if not os.path.exists(os.path.join(OUT_FIT, f'fit_{s["id"]}.wav'))]
    print("TTS todo:", len(todo))
    for k, s in enumerate(todo):
        try:
            p = gen_one(s)
        except Exception as e:
            print("FAIL", s["id"], repr(e)[:200]); continue
        d = probe_dur(p)
        tgt = s["dur"] + 0.05
        if d > tgt * 1.6 and s.get("df", 1.0) == 1.0:
            # 语速差太大: 用 duration_factor=0.5 重生(模型原生快语速, 比纯 atempo 压自然)
            print(f'  {s["id"]} ratio={d/tgt:.2f} > 1.6, regen with df=0.5')
            try:
                s2 = dict(s, df=0.5)
                p = gen_one(s2)
                d2 = probe_dur(p)
                if d2 < d: d = d2
                else: p = gen_one(s)  # 回退重生成原版
                d = probe_dur(p)
            except Exception as e:
                print("  regen fail", s["id"], repr(e)[:120]); p = gen_one(s); d = probe_dur(p)
        fit = os.path.join(OUT_FIT, f'fit_{s["id"]}.wav')
        if d > tgt * 1.02:
            tempo = d / tgt
            if tempo > 2.0:
                t1 = 2.0; t2 = tempo / 2.0
                sh([FF, "-y", "-i", p, "-filter:a", f"atempo={t1:.4f},atempo={t2:.4f}", "-ac", "1", "-ar", "44100", fit])
            else:
                sh([FF, "-y", "-i", p, "-filter:a", f"atempo={tempo:.4f}", "-ac", "1", "-ar", "44100", fit])
        else:
            sh([FF, "-y", "-i", p, "-ac", "1", "-ar", "44100", fit])
        print(f'[{k+1}/{len(todo)}] {s["id"]} gen={d:.2f}s slot={s["dur"]}s -> fit={probe_dur(fit):.2f}s')

# ───────────────────────── 混音 ─────────────────────────
def mix():
    # 三层: 伴奏 no_vocals (底) + TTS fit (REPLAN 摆位) + KEEP 干声切片
    # 蒙太奇直用区(N29a-N31,N32-N33)不遮罩原片——直接切原片音轨段贴回
    parts = [f'[0:a]volume=1.0[bgm]']
    idx = 1
    inputs = [os.path.join(BASE, "audio", "htdemucs", "full_audio", "no_vocals.wav")]
    # TTS 槽摆位
    for s in TTS:
        p = os.path.join(OUT_FIT, f'fit_{s["id"]}.wav')
        if not os.path.exists(p):
            print("MISSING TTS:", s["id"]); continue
        ms = int(s["start"] * 1000)
        parts.append(f'[{idx}:a]adelay={ms}[t{idx}]')
        inputs.append(p)
        idx += 1
    # 孤立 KEEP 切片
    for s in KEEP:
        if s.get("use_original_track"): continue
        p = os.path.join(BASE, "audio", f'keep_{s["id"]}.wav')
        ms = int(max(0.0, s["start"] - 0.25) * 1000)
        parts.append(f'[{idx}:a]adelay={ms}[t{idx}]')
        inputs.append(p)
        idx += 1
    n = idx  # amix inputs = 1(bgm) + N 轨
    parts.append(f'[bgm]' + "".join(f'[t{i}]' for i in range(1, idx)) + f'amix=inputs={n}:duration=first:normalize=0,alimiter=limit=0.95[aout]')
    script = os.path.join(BASE, "mix_filter.txt")
    open(script, "w", encoding="utf-8").write(";".join(parts))
    cmd = [FF, "-y"]
    for p in inputs: cmd += ["-i", p]
    mixed = os.path.join(OUT_MIX, "mixed.wav")
    cmd += ["-filter_complex_script", script, "-map", "[aout]", "-ar", "44100", mixed]
    sh(cmd)
    # 蒙太奇/直用区: 用原片音轨覆盖 mixed（切原片音轨段，贴回对应时段）
    # 分段拼接: [0,mixed] 与 run 段来源切换 → 用 ffmpeg concat 按时间窗交换轨
    final = os.path.join(OUT_MIX, "final_audio.wav")
    # 生成逐 run 的拼接: 以 mixed 为底，run 区间用原片轨替换
    parts2 = ['[0:a]volume=1.0[m0]']
    idx2 = 1
    inputs2 = [mixed]
    bounds = []
    for i, r in enumerate(runs):
        bounds.append((r["start"]-0.15, r["end"]+0.15, os.path.join(BASE, "audio", f"orig_run_{i}_{r['first']}-{r['last']}.wav")))
    # asplit mixed into segments around bounds; replace with orig
    segs = []   # (label, start, end, kind, input_idx)
    prev_end = 0.0
    for bi, (a, b, p) in enumerate(bounds):
        if a > prev_end + 0.01:
            segs.append((f"cut{bi}", prev_end, a, "mix", 0))
        segs.append((f"orig{bi}", a, b, "orig", len(inputs2)))
        inputs2.append(p)
        prev_end = b
    if prev_end < 181.70 - 0.01:
        segs.append(("cutend", prev_end, 181.70, "mix", 0))
    fl = []
    for name, a, b, kind, ii in segs:
        if kind == "mix":
            fl.append(f"[0:a]atrim=start={a:.2f}:end={b:.2f},asetpts=PTS-STARTPTS[{name}]")
        else:
            fl.append(f"[{ii}:a]asetpts=PTS-STARTPTS[{name}]")
    fl.append("".join(f"[{s[0]}]" for s in segs) + f"concat=n={len(segs)}:v=0:a=1[aout2]")
    script2 = os.path.join(BASE, "mix_filter2.txt")
    open(script2, "w", encoding="utf-8").write(";".join(fl))
    cmd2 = [FF, "-y"]
    for p in inputs2: cmd2 += ["-i", p]
    cmd2 += ["-filter_complex_script", script2, "-map", "[aout2]", "-ar", "44100", final]
    sh(cmd2)
    # 合回画面
    outv = os.path.join(BASE, "填词版_完整成片_v5.mp4")
    sh([FF, "-y", "-i", SRC, "-i", final, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", outv])
    print("MIX OK ->", outv, "| duration", probe_dur(outv))

def status():
    for d, pat, label in [("refs", "ref_*.wav", "参考件"), ("tts_out", "gen_*.wav", "TTS原始"), ("tts_fit", "fit_*.wav", "收口")]:
        p = os.path.join(BASE, d)
        import glob as _g
        n = len(_g.glob(os.path.join(p, pat))) if os.path.exists(p) else 0
        print(f"{label}: {n}")
    print("mixed:", os.path.exists(os.path.join(OUT_MIX, "mixed.wav")), "| final:", os.path.exists(os.path.join(OUT_MIX, "final_audio.wav")))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    dict(stage1=stage1, smoke=smoke, tts=tts_all, mix=mix, status=status)[cmd]()
