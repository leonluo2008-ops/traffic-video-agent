# -*- coding: utf-8 -*-
"""读源码: SaveAudio 在本插件的期望输入类型（找 tuple indices 错因）"""
import re
base = r"D:\AI-tool\ComfyUI-aki-v1.6\ComfyUI\custom_nodes\ComfyUI-Index-TTS"
import io, os
for fname in ("index_tts2_5_nodes.py", "nodes.py"):
    p = os.path.join(base, fname)
    if not os.path.exists(p): continue
    src = io.open(p, encoding="utf-8", errors="replace").read()
    # 找 SaveAudio / RETURN_TYPES / audiobook 之类音频输出节点
    for m in re.finditer(r"class (\w*Audio\w*|\w*Save\w*|\w*Preview\w*)\w*[^\n]*", src):
        cls = m.group(0).strip()
        # 打印类定义后 40 行内的 INPUT_TYPES/RETURN
        seg = src[m.start():m.start()+1500]
        ret = re.search(r"RETURN_TYPES\s*=\s*(\([^\n]*\))", seg)
        inp = re.search(r"def INPUT_TYPES.*?return\s*(\{.{0,400})", seg, re.S)
        if ret or inp:
            print("==", fname, "::", cls)
            if ret: print("   RETURN:", ret.group(1))
            if inp: print("   INPUT :", re.sub(r"\s+", " ", inp.group(1))[:300])
    print("----", fname, "classes scanned")
