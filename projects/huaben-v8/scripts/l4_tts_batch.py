# -*- coding: utf-8 -*-
"""L4 批量生产: 70 个 tts 槽的参考段切分 + 推 PC ComfyUI IndexTTS-2.5 生成 + 回收

链路 (2026-08-31 冒烟已验证):
  surface: tangbohu_16k.wav 按槽切 ref_<id>.wav (16k mono)
  scp -> PC D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/input/
  逐槽 POST /prompt (UTF-8 payload 文件 + curl -d @file, 防码点转义坑)
  轮询 /history/<pid> 收 SaveAudio 产物
  scp 回 surface /tmp/huaben-v7/tts_out/
产物命名: tts_<slotid>.flac

时长控制: duration_factor 0.5-2.0 (节点限制)。生成后 surface 端 ffprobe 实测,
与槽 dur 比对; 超 8% 的槽记录到 duration_mismatch.json 待 L5 决策(atempo 微调)。
"""
import json, os, subprocess, sys, time, shutil

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2'
SLOTS = f'{BASE}/research/slots_v7_filled.json'
SRC_WAV = f'{BASE}/research/tangbohu_16k.wav'
REF_DIR = '/tmp/huaben-v7/refs'
OUT_DIR = '/tmp/huaben-v7/tts_out'
PC_JOBS = 'D:/AI-tool/whisperx/jobs/huaben'          # payload 中转
PC_INPUT = 'D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/input'
PC_OUTDIR_SSH = 'D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/output'
SSH = ['ssh', '-i', '/home/luo/.ssh/pc_luo1_ed25519', '-o', 'ConnectTimeout=8', '-o', 'BatchMode=yes',
       'leon3@100.109.238.27']
SCP = ['scp', '-i', '/home/luo/.ssh/pc_luo1_ed25519']
HOST = 'leon3@100.109.238.27'
COMFY = 'http://127.0.0.1:8188'
CLIENT = 'hermes-l4'

def sh(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    out = r.stdout.decode('utf-8', errors='replace')
    err = r.stderr.decode('utf-8', errors='replace')
    return r.returncode, out, err

def comfy_post(payload_path):
    """payload 已 scp 到 PC, 用 curl -d @file 提交 (绝对路径用正斜杠)"""
    pf = payload_path.replace('\\', '/')
    rc, out, err = sh(SSH + [f'curl -s -m 30 -X POST {COMFY}/prompt -H "Content-Type: application/json" -d @{pf}'], 60)
    try:
        return json.loads(out)
    except Exception:
        return {'error_raw': out[:200], 'stderr': err[:200]}

def comfy_history(pid):
    rc, out, _ = sh(SSH + [f'curl -s -m 10 {COMFY}/history/{pid}'], 40)
    try:
        return json.loads(out)
    except Exception:
        return {}

def cut_refs():
    os.makedirs(REF_DIR, exist_ok=True)
    slots = json.load(open(SLOTS, encoding='utf-8'))
    tts = [s for s in slots if s['mode'] == 'tts']
    for s in tts:
        dst = f"{REF_DIR}/ref_{s['id']}.wav"
        if os.path.exists(dst):
            continue
        subprocess.run(['ffmpeg', '-y', '-v', 'quiet', '-ss', str(s['start']), '-to', str(s['end']),
                        '-i', SRC_WAV, '-ac', '1', dst], check=True, timeout=30)
    print(f"[refs] {len(tts)} 段切好 -> {REF_DIR}")
    return slots, tts

def push_refs(tts):
    # scp -r 目录本体 (OpenSSH Windows 端不支持 /. 尾缀写法)
    rc, out, err = sh(SCP + ['-r', REF_DIR, f'{HOST}:{PC_INPUT}/'], 600)
    ok = rc == 0
    print(f"[push] scp rc={rc} {'OK' if ok else err[-150:]}")
    return ok

def submit_slot(s, idx):
    payload = {"prompt": {
        "n_load": {"class_type": "LoadAudio", "inputs": {"audio": f"refs/ref_{s['id']}.wav"}},
        "n_tts": {"class_type": "IndexTTS25BaseNode", "inputs": {
            "text": s['new_text'], "reference_audio": ["n_load", 0],
            "lang": "ZH", "duration_factor": 1.0, "seed": idx}},
        "n_save": {"class_type": "SaveAudio", "inputs": {"audio": ["n_tts", 0],
            "filename_prefix": f"tts_{s['id']}"}},
    }, "client_id": CLIENT}
    pf_local = f"{REF_DIR}/payload_{s['id']}.json"
    open(pf_local, 'w', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False))
    rc, _, err = sh(SCP + [pf_local, f'{HOST}:{PC_JOBS}/'], 60)
    if rc != 0:
        return None, f'scp payload fail: {err[-100:]}'
    resp = comfy_post(f'{PC_JOBS}/payload_{s["id"]}.json')
    pid = resp.get('prompt_id')
    if not pid:
        return None, f'post fail: {json.dumps(resp)[:150]}'
    return pid, ''

def wait_pid(pid, s, max_wait=180):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        h = comfy_history(pid)
        info = h.get(pid)
        if info:
            st = info.get('status', {})
            if st.get('status_str') == 'error':
                msg = ''
                for m in st.get('messages', []):
                    if m[0] == 'execution_error':
                        msg = m[1].get('exception_message', '')[:150]
                return 'error', msg
            if st.get('completed'):
                fn = None
                for node in info.get('outputs', {}).values():
                    for a in node.get('audio', []):
                        fn = a.get('filename')
                return 'done', fn
        time.sleep(3)
    return 'timeout', ''

def collect(fn, s):
    rc, out, err = sh(SCP + [f'{HOST}:{PC_OUTDIR_SSH}/{fn}', f'{OUT_DIR}/'], 120)
    if rc != 0:
        return False, err[-100:]
    # ComfyUI SaveAudio 对同名前缀会 _00001 递增; 每槽唯一前缀 -> 固定 _00001
    src = f"{OUT_DIR}/{fn}"
    dst = f"{OUT_DIR}/tts_{s['id']}.flac"
    if fn != f"tts_{s['id']}.flac":
        os.rename(src, dst)
    return True, ''

def probe_dur(path):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       capture_output=True, text=True, timeout=30)
    try:
        return float(r.stdout.strip())
    except Exception:
        return None

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    slots, tts = cut_refs()
    if not push_refs(tts):
        sys.exit(1)

    manifest = []
    errs = []
    t0 = time.time()
    for idx, s in enumerate(tts):
        sid = s['id']
        final = f'{OUT_DIR}/tts_{sid}.flac'
        if os.path.exists(final):
            manifest.append({'id': sid, 'status': 'cached'})
            continue
        pid, err = submit_slot(s, idx)
        if not pid:
            errs.append({'id': sid, 'stage': 'submit', 'err': err})
            print(f"[{idx+1}/{len(tts)}] {sid} SUBMIT-FAIL {err[:80]}", flush=True)
            continue
        status, info = wait_pid(pid, s)
        if status != 'done':
            errs.append({'id': sid, 'stage': status, 'err': info})
            print(f"[{idx+1}/{len(tts)}] {sid} {status.upper()} {str(info)[:80]}", flush=True)
            continue
        ok, err = collect(info, s)
        if not ok:
            errs.append({'id': sid, 'stage': 'collect', 'err': err})
            print(f"[{idx+1}/{len(tts)}] {sid} COLLECT-FAIL", flush=True)
            continue
        gdur = probe_dur(final)
        ratio = (gdur / s['dur']) if (gdur and s['dur']) else None
        manifest.append({'id': sid, 'status': 'ok', 'gen_dur': round(gdur, 3) if gdur else None,
                         'slot_dur': s['dur'], 'ratio': round(ratio, 3) if ratio else None})
        flag = '' if (ratio and 0.92 <= ratio <= 1.08) else ' ⚠️dur'
        print(f"[{idx+1}/{len(tts)}] {sid} OK {gdur:.2f}s/{s['dur']:.2f}s r={ratio:.2f}{flag}", flush=True)

    json.dump({'manifest': manifest, 'errors': errs}, open(f'{OUT_DIR}/l4_manifest.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    n_ok = sum(1 for m in manifest if m['status'] == 'ok')
    print(f"=== L4 done: {n_ok} ok / {len(errs)} err, {time.time()-t0:.0f}s ===", flush=True)
    json.dump(manifest, open(f'{BASE}/research/l4_manifest.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
