# -*- coding: utf-8 -*-

# ⚠️⚠️⚠️ 本脚本路线已被用户终审判死刑（2026-08-31）⚠️⚠️⚠️
# 「全局角色参考段」已被证伪并禁用：V8 用本路线被驳回，V8.1 回正「每槽参考=原片
# 该槽时间轴干声切片」后听审通过（音色匹配「有质的区别」）。
# 唯一有效路线见 l4_tts_v81.py（保留本文件仅作事故复盘存档，禁止再跑）。
# ====================================================================
"""dahua V8 L4: IndexTTS 角色参考段批量生成 (v8 核心改进)
与 v7 l4_tts_batch.py 差异:
  1. 参考音不再是逐槽切原声(混战区脏), 改用素材库全局角色参考:
     - 至尊宝(男): 素材/zhizunbao.mp3 49.3s → 取平缓清晰 6-8s 段
     - 紫霞(女):   素材/zixia.mp3     10.0s → 取中间 6-8s 段
  2. 时长闭环: 生成后 ffprobe 实测 vs 槽 dur, 超±8% 用 duration_factor 二轮补偿
  3. 产物拉回 surface /tmp/huaben-v8/tts_out/
"""
import json, os, subprocess, sys, time

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-v8'
SLOTS = f'{BASE}/research/slots_v8_filled.json'
REF_DIR = '/tmp/huaben-v8/refs'
OUT_DIR = '/tmp/huaben-v8/tts_out'
PC_JOBS = 'D:/AI-tool/whisperx/jobs/dahua'
PC_INPUT = 'D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/input'
PC_OUTDIR_SSH = 'D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/output'
SSH = ['ssh', '-i', '/home/luo/.ssh/pc_luo1_ed25519', '-o', 'ConnectTimeout=8', '-o', 'BatchMode=yes',
       'leon3@100.109.238.27']
SCP = ['scp', '-i', '/home/luo/.ssh/pc_luo1_ed25519']
HOST = 'leon3@100.109.238.27'
COMFY = 'http://127.0.0.1:8188'
CLIENT = 'hermes-l4-v8'


def sh(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode('utf-8', errors='replace'), r.stderr.decode('utf-8', errors='replace')


def comfy_post(payload_path):
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


def cut_role_refs():
    """角色全局参考段: 平缓清晰优先 (用户 08-31 拍板选段标准)"""
    os.makedirs(REF_DIR, exist_ok=True)
    plan = [
        # (src, ss, to, dst) — 至尊宝取中段平缓区, 紫霞取中段
        (f'{BASE}/素材/zhizunbao.mp3', 20.0, 28.0, f'{REF_DIR}/ref_zhizunbao.wav'),
        (f'{BASE}/素材/zixia.mp3', 1.5, 9.5, f'{REF_DIR}/ref_zixia.wav'),
    ]
    for src, ss, to, dst in plan:
        if os.path.exists(dst):
            continue
        subprocess.run(['ffmpeg', '-y', '-v', 'quiet', '-ss', str(ss), '-to', str(to),
                        '-i', src, '-ac', '1', '-ar', '44100', dst], check=True, timeout=60)
    print(f"[refs] 角色参考段切好 -> {REF_DIR}")


def push_refs():
    rc, out, err = sh(SCP + ['-r', REF_DIR, f'{HOST}:{PC_INPUT}/'], 600)
    print(f"[push] scp rc={rc} {'OK' if rc == 0 else err[-150:]}")
    return rc == 0


def ref_for(spk):
    return 'refs/ref_zhizunbao.wav' if spk != '紫霞' else 'refs/ref_zixia.wav'


def submit_slot(s, idx, df=1.0):
    payload = {"prompt": {
        "n_load": {"class_type": "LoadAudio", "inputs": {"audio": ref_for(s.get('spk', ''))}},
        "n_tts": {"class_type": "IndexTTS25BaseNode", "inputs": {
            "text": s['new_text'], "reference_audio": ["n_load", 0],
            "lang": "ZH", "duration_factor": round(df, 3), "seed": idx}},
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


def wait_pid(pid, max_wait=180):
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
    slots = json.load(open(SLOTS, encoding='utf-8'))
    tts = [s for s in slots if s['mode'] == 'tts']
    cut_role_refs()
    if not push_refs():
        sys.exit(1)

    manifest = []
    errs = []
    t0 = time.time()
    for idx, s in enumerate(tts):
        sid = s['id']
        final = f'{OUT_DIR}/tts_{sid}.flac'
        if os.path.exists(final):
            gd = probe_dur(final)
            ratio = (gd / s['dur']) if (gd and s['dur']) else None
            manifest.append({'id': sid, 'status': 'cached', 'gen_dur': gd, 'slot_dur': s['dur'],
                             'ratio': round(ratio, 3) if ratio else None})
            continue
        # 一轮生成 + 二轮 df 补偿 (v7 实证: ratio 0.92-1.08 带内即收)
        for attempt in range(2):
            df = 1.0
            if attempt == 1:
                # 二轮: 按首轮 ratio 反推 (太长→df<1 缩短; 太短→df>1 拉长)
                first = next((m for m in manifest if m['id'] == sid), None)
                if not first or first.get('ratio') is None:
                    break
                if 0.92 <= first['ratio'] <= 1.08:
                    break
                df = max(0.5, min(2.0, 1.0 / first['ratio']))
            pid, err = submit_slot(s, idx, df=df)
            if not pid:
                errs.append({'id': sid, 'stage': 'submit', 'err': err})
                print(f"[{idx+1}/{len(tts)}] {sid} SUBMIT-FAIL {err[:80]}", flush=True)
                break
            status, info = wait_pid(pid)
            if status != 'done':
                errs.append({'id': sid, 'stage': status, 'err': info})
                print(f"[{idx+1}/{len(tts)}] {sid} {status.upper()} {str(info)[:80]}", flush=True)
                break
            ok, err = collect(info, s)
            if not ok:
                errs.append({'id': sid, 'stage': 'collect', 'err': err})
                print(f"[{idx+1}/{len(tts)}] {sid} COLLECT-FAIL", flush=True)
                break
            gd = probe_dur(final)
            ratio = (gd / s['dur']) if (gd and s['dur']) else None
            rec = {'id': sid, 'status': 'ok', 'gen_dur': round(gd, 3) if gd else None,
                   'slot_dur': s['dur'], 'ratio': round(ratio, 3) if ratio else None, 'df': df}
            if attempt == 0:
                manifest.append(rec)
            else:
                manifest = [m if m['id'] != sid else rec for m in manifest]
            flag = '' if (ratio and 0.92 <= ratio <= 1.08) else ' ⚠️dur'
            print(f"[{idx+1}/{len(tts)}] {sid} OK {gd:.2f}s/{s['dur']:.2f}s r={ratio:.2f} df={df}{flag}", flush=True)

    json.dump({'manifest': manifest, 'errors': errs}, open(f'{OUT_DIR}/l4_manifest.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    n_ok = sum(1 for m in manifest if m['status'] == 'ok')
    in_band = sum(1 for m in manifest if m.get('ratio') and 0.92 <= m['ratio'] <= 1.08)
    print(f"=== L4 done: {n_ok} ok / {len(errs)} err, 带内 {in_band}/{n_ok}, {time.time()-t0:.0f}s ===", flush=True)


if __name__ == '__main__':
    main()
