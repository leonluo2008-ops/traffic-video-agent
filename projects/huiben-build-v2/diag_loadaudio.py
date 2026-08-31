# -*- coding: utf-8 -*-
"""dump LoadAudio 完整 input 结构 + IndexTTS 枚举值"""
import json, urllib.request
d = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info/LoadAudio", timeout=30).read())
inp = d["LoadAudio"]["input"]["required"]["audio"]
print("LoadAudio.audio 结构类型:", type(inp), "长度:", len(inp) if isinstance(inp, list) else "-")
if isinstance(inp, list):
    for i, el in enumerate(inp):
        if isinstance(el, list):
            print(f"[{i}] list({len(el)}):", el[:8], "..." if len(el) > 8 else "")
        else:
            print(f"[{i}]:", repr(el)[:200])
n = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info/IndexTTS25BaseNode", timeout=30).read())["IndexTTS25BaseNode"]["input"]["required"]
for k in ("lang", "duration_factor"):
    print(k, "=", n.get(k))
