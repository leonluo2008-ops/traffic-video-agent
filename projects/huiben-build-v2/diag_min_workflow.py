# -*- coding: utf-8 -*-
"""最小工作流 400 定位: 逐字段加回参数"""
import json, urllib.request, urllib.error

COMFY = "http://127.0.0.1:8188"

def try_prompt(wf, tag):
    data = json.dumps({"prompt": wf, "client_id": "diag"}).encode()
    req = urllib.request.Request(COMFY + "/prompt", data=data, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read())
        print(f"[{tag}] OK ->", body.get("prompt_id", "")[:8])
        return body.get("prompt_id")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:600]
        print(f"[{tag}] {e.code}: {err}")
        return None

# 步0: 纯最小 (LoadAudio -> Base 默认 -> Save)
wf_min = {
  "1": {"class_type": "LoadAudio", "inputs": {"audio": "ref_N23.wav"}},
  "2": {"class_type": "IndexTTS25BaseNode", "inputs": {"text": "久闻车评卧虎藏龙", "reference_audio": ["1", "audio"]}},
  "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", "audio"]}},
}
pid = try_prompt(wf_min, "min-default")

# 步1: +lang
if pid:
    wf = json.loads(json.dumps(wf_min)); wf["2"]["inputs"]["lang"] = "ZH"
    pid = try_prompt(wf, "min+lang")

# 步2: +duration_factor
if pid:
    wf = json.loads(json.dumps(wf_min)); wf["2"]["inputs"]["lang"] = "ZH"; wf["2"]["inputs"]["duration_factor"] = 1.0
    pid = try_prompt(wf, "min+lang+df")

# 步3: SaveAudio 结构探测（object_info）
n = json.loads(urllib.request.urlopen(COMFY + "/object_info/SaveAudio", timeout=30).read())
print("SaveAudio input:", n["SaveAudio"]["input"])
