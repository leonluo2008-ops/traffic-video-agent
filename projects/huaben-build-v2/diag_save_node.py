# -*- coding: utf-8 -*-
"""定位 SaveAudio: ComfyUI 内核 SaveAudio 的 audio 输入期望 AUDIOS？还是插件覆写？
   并测试用 PreviewAudio 系节点替代。"""
import json, urllib.request, urllib.error

COMFY = "http://127.0.0.1:8188"

def try_prompt(wf, tag):
    data = json.dumps({"prompt": wf, "client_id": "diag"}).encode()
    req = urllib.request.Request(COMFY + "/prompt", data=data, headers={"Content-Type": "application/json"})
    try:
        body = json.loads(urllib.request.urlopen(req, timeout=30).read())
        print(f"[{tag}] OK ->", body.get("prompt_id", "")[:16])
        return body.get("prompt_id")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:400]
        print(f"[{tag}] {e.code}: {err}")
        return None

base = {
  "1": {"class_type": "LoadAudio", "inputs": {"audio": "ref_N23.wav"}},
  "2": {"class_type": "IndexTTS25BaseNode", "inputs": {
      "text": "久闻车评卧虎藏龙", "reference_audio": ["1", 0],
      "lang": "ZH", "duration_factor": 1.0}},
}

# 候选保存节点
for cls in ("SaveAudio",):
    wf = dict(base)
    wf["3"] = {"class_type": cls.split("|")[0], "inputs": {"audio": ["2", 0]}}
    pid = try_prompt(wf, cls)
    if pid:
        print(">>> 用", cls, "成功，break")
        break
