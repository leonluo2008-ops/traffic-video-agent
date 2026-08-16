# -*- coding: utf-8 -*-
"""v4.1 重切原声音频（E/G/H/I/J wav）：与视频同样的中点平分逻辑，切点对齐"""
import os, sys, subprocess
sys.stdout.reconfigure(encoding='utf-8')

FF = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
VOCALS = r"D:\AI-tool\vocal-sep-server\output\dahua_master_vocals.wav"
KEEP_DIR = r"D:\AI-tool\组合包_大话西游测试_v4\原声音频片段"

# 与视频重切完全相同的切点（recut_v41.py 输出）
CUTS = [
 ("E","紫霞","担忧",110.50,112.50),
 ("G","紫霞","心疼",119.50,120.50),
 ("H","至尊宝","推脱",120.50,123.50),
 ("I","紫霞","试探",123.50,125.50),
 ("J","至尊宝","坚定",125.50,129.50),
]

for seg, role, emo, cs, ce in CUTS:
    out = os.path.join(KEEP_DIR, f"{seg}_{role}_{emo}_原声.wav")
    r = subprocess.run([FF, "-y", "-v", "error", "-ss", f"{cs:.2f}", "-t", f"{ce-cs:.2f}",
                        "-i", VOCALS, "-ac", "1", "-ar", "44100", out],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = r.returncode == 0 and os.path.exists(out)
    print(f"  {seg} [{cs:.2f}-{ce:.2f}] {'OK' if ok else 'FAIL:'+r.stderr[-150:]}", flush=True)
print("DONE")
