# -*- coding: utf-8 -*-
"""冒烟产物验证: flac 时长 + 编排器收尾（fit_N23 + 回放校验）"""
import shutil, subprocess, os, json

BASE = r"D:\AI-tool\huaben-build-v2"
flac = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\output\huaben\tts_00001.flac"
gen = os.path.join(BASE, "tts_out", "gen_N23.wav")

# flac -> wav via ffmpeg (PC 上 ffmpeg 在 ComfyUI 包内)
ff = r"C:\Users\leon3\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
if not os.path.exists(ff):
    # 常见落点
    for c in (r"D:\AI-tool\ffmpeg\bin\ffmpeg.exe", r"C:\ffmpeg\bin\ffmpeg.exe"):
        if os.path.exists(c): ff = c; break
print("ffmpeg:", ff, os.path.exists(ff))

if os.path.exists(flac):
    r = subprocess.run([ff, "-y", "-i", flac, gen], capture_output=True, text=True)
    print("flac->wav:", r.returncode)
    if os.path.exists(gen):
        import wave
        w = wave.open(gen)
        print(f"gen_N23.wav dur={w.getnframes()/w.getframerate():.2f}s sr={w.getframerate()}")
        w.close()
        # 槽 N23 目标时长（画本: N23 70.6-71.9 ≈1.3s，文本 8 字）
        print("N23 目标 ≈1.3s | 文本 8 字")
else:
    print("flac 不存在")
