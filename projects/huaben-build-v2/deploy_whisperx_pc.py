# -*- coding: utf-8 -*-
"""PC 端部署 WhisperX v2 (干净 PATH 避开 WinError 448; 不装 torch, 回退 ComfyUI cu128)"""
import subprocess, os, sys

VPY = r"D:\AI-tool\whisperx\venv\Scripts\python.exe"
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

# 干净 PATH: 只要系统目录, 避开 cua-driver 不受信任装入点 (WinError 448)
CLEAN_ENV = dict(os.environ)
CLEAN_ENV["PATH"] = r"C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0"

def pip(*args):
    idx = ["-i", MIRROR] if args[0] == "install" else []
    cmd = [VPY, "-X", "utf8", "-m", "pip", args[0], *idx, *args[1:]]
    r = subprocess.run(cmd,
                       env=CLEAN_ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit(f"pip failed: {args}")
    print(f"OK: {args}", flush=True)

# 1) 卸掉 venv 里 pip 拉进来的 CPU torch 三件套 (回退到 system 的 2.11.0+cu128)
pip("uninstall", "-y", "torch", "torchvision", "torchaudio", "torchcodec")

# 2) whisperx 本体 no-deps + 非 torch 依赖显式装
pip("install", "--no-deps", "whisperx")
pip("install",
    "ctranslate2>=4.5.0", "faster-whisper>=1.2.0",
    "pyannote-audio>=4.0.0",
    "asteroid-filterbanks", "einops", "lightning", "optuna",
    "sortedcontainers", "torch-audiomentations", "torch-pitch-shift", "primePy",
    "opentelemetry-api", "opentelemetry-sdk", "opentelemetry-exporter-otlp",
    "opentelemetry-proto", "opentelemetry-semantic-conventions",
    "googleapis-common-protos", "numpy", "protobuf", "torchcodec")

# 3) 验证: torch 回退 system cu128 + whisperx 导入
r = subprocess.run([VPY, "-X", "utf8", "-c",
                    "import torch; print('torch', torch.__version__, 'cuda_ok', torch.cuda.is_available());"
                    "import whisperx, ctranslate2; print('whisperx+ctranslate2 OK', ctranslate2.__version__)"],
                   env=CLEAN_ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout, r.stderr[-800:] if r.stderr else "")
if "cuda_ok True" not in r.stdout:
    raise SystemExit("torch cuda fallback failed")
print("DEPLOY OK")