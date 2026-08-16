# -*- coding: utf-8 -*-
"""v4.1 重切原声视频：消除相邻段重叠
裁切规则（通用，非硬编码）：
  - 相邻段间隙 >= 2×冗余量(3s) → 各自 ±1.5s 冗余（宁多勿少）
  - 相邻段间隙 < 3s（连续对话链）→ 以间隙中点平分，零重复
  - 首段起点/末段终点照常外扩 1.5s
"""
import os, sys, subprocess
sys.stdout.reconfigure(encoding='utf-8')

FF = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
SRC = r"E:\tmp\大话西游素材_raw.mp4"
OUT = r"D:\AI-tool\组合包_大话西游测试_v4"
R = 1.5  # 冗余量

SEGS = [
 ("A","至尊宝","深情",54,63), ("B","紫霞","关切",85,89), ("C","至尊宝","坚定",90,99),
 ("D","至尊宝","决然",100,110), ("E","紫霞","担忧",111,112), ("F","至尊宝","自责",113,119),
 ("G","紫霞","心疼",120,120), ("H","至尊宝","推脱",121,123), ("I","紫霞","试探",124,125),
 ("J","至尊宝","坚定",126,128),
]

# ── 计算切点：间隙中点平分 or ±冗余 ──
cuts = []
n = len(SEGS)
for i, (seg, role, emo, t0, t1) in enumerate(SEGS):
    # 起点边界
    if i == 0:
        cs = max(0, t0 - R)
    else:
        prev_end = SEGS[i-1][4]
        gap = t0 - prev_end
        cs = (prev_end + t0) / 2 if gap < 2*R else t0 - R   # 间隙中点 or 冗余
    # 终点边界
    if i == n-1:
        ce = t1 + R
    else:
        next_start = SEGS[i+1][3]
        gap = next_start - t1
        ce = (t1 + next_start) / 2 if gap < 2*R else t1 + R
    cuts.append((seg, role, emo, cs, ce))

# 报告新切点 + 验证零重叠
print("新切点（间隙<3s 平分 / 间隙>=3s ±1.5s）:")
prev_ce = None
for seg, role, emo, cs, ce in cuts:
    ov = max(0, (prev_ce - cs)) if prev_ce is not None else 0
    warn = f"  ←与上一段重叠{ov:.2f}s!" if ov > 0.001 else ""
    print(f"  {seg} {role}/{emo}: [{cs:.2f} - {ce:.2f}]{warn}")
    prev_ce = ce

# 切分（重编码保证切点精确；-c copy 关键帧对齐会漂移）
print("\n切分执行:")
for seg, role, emo, cs, ce in cuts:
    out = os.path.join(OUT, f"{seg}_{role}_{emo}_原声.mp4")
    r = subprocess.run([FF, "-y", "-v", "error", "-ss", f"{cs:.2f}", "-t", f"{ce-cs:.2f}",
                        "-i", SRC, "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", out],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = r.returncode == 0 and os.path.exists(out)
    print(f"  {seg} [{cs:.2f}-{ce:.2f}] {'OK' if ok else 'FAIL:'+r.stderr[-150:]}", flush=True)

print("\nDONE")
