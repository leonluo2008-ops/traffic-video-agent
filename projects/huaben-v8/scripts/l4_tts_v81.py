# -*- coding: utf-8 -*-
"""dahua V8.1 L4: 逐槽参考 = 原片该槽时间轴干声 (用户铁律, 修正 v8 全局参考的错误)
每槽 ref = research/vocals.wav 在该槽 [start,end] 的切片;
  短槽(<2.5s)并入同说话人连续段(间隔<0.5s)取窗口, 上限 10s。
manifest 记录每槽 ref 实际秒数——审计留痕。
"""
import json, os, re, subprocess, sys, time

BASE = next(os.path.join(p, d) for p in ['/home/luo/projects/traffic-video-agent/projects']
           for d in sorted(os.listdir(p), reverse=True)
           if re.match(r'^hu[ai]ben-v8$', d) and 'build' not in d
           and os.path.exists(os.path.join(p, d, 'research', 'slots_v8_filled.json')))
TMP = '/tmp/' + os.path.basename(BASE)
SLOTS = f'{BASE}/research/slots_v8_filled.json'
VOCALS = f'{BASE}/research/vocals.wav'
REF_DIR = TMP + '/refs81'
OUT_DIR = TMP + '/tts_out81'
PC_JOBS = 'D:/AI-tool/whisperx/jobs/dahua'
PC_INPUT = 'D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/input'
PC_OUTDIR_SSH = 'D:/AI-tool/ComfyUI-aki-v1.6/ComfyUI/output'
SSH = ['ssh', '-i', '/home/luo/.ssh/pc_luo1_ed25519', '-o', 'ConnectTimeout=8', '-o', 'BatchMode=yes',
       'leon3@100.109.238.27']
SCP = ['scp', '-i', '/home/luo/.ssh/pc_luo1_ed25519']
HOST = 'leon3@100.109.238.27'
COMFY = 'http://127.0.0.1:8188'
CLIENT = 'hermes-l4-v81'


def sh(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode('utf-8', errors='replace'), r.stderr.decode('utf-8', errors='replace')


def build_groups(tts):
    """同说话人且间隔<0.5s 的连续槽归组"""
    groups, cur = [], []
    for s in tts:
        if cur and (s['spk'] == cur[-1]['spk'] and s['start'] - cur[-1]['end'] < 0.5):
            cur.append(s)
        else:
            if cur:
                groups.append(cur)
            cur = [s]
    if cur:
        groups.append(cur)
    return groups


def ref_span(slot, group):
    """槽自身span; 不足2.5s向组内扩, 上限10s"""
    st, en = slot['start'], slot['end']
    if en - st >= 2.5:
        return st, en
    gs, ge = group[0]['start'], group[-1]['end']
    c = (st + en) / 2
    lo = max(gs, min(st, c - 5))
    hi = min(ge, max(en, lo + 2.5))
    lo = max(gs, hi - 10)
    return lo, hi


def cut_refs(tts):
    os.makedirs(REF_DIR, exist_ok=True)
    groups = build_groups(tts)
    plan = {}
    for g in groups:
        for s in g:
            lo, hi = ref_span(s, g)
            dst = f"{REF_DIR}/ref_{s['id']}.wav"
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{lo:.3f}', '-to', f'{hi:.3f}',
                            '-i', VOCALS, '-ac', '1', '-ar', '44100', dst], check=True, timeout=60)
            plan[s['id']] = {'ref_start': round(lo, 2), 'ref_end': round(hi, 2),
                             'ref_dur': round(hi - lo, 2), 'src': 'research/vocals.wav(原片干声)'}
    return plan


def push_refs():
    rc, out, err = sh(SCP + ['-r', REF_DIR, f'{HOST}:{PC_INPUT}/'], 600)
    print(f"[push] scp rc={rc} {'OK' if rc == 0 else err[-150:]}", flush=True)
    return rc == 0


def submit_slot(s, idx, df=1.0):
    payload = {"prompt": {
        "n_load": {"class_type": "LoadAudio", "inputs": {"audio": f"refs81/ref_{s['id']}.wav"}},
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
    rc, out, err = sh(SSH + [f'curl -s -m 30 -X POST {COMFY}/prompt -H "Content-Type: application/json" -d @{PC_JOBS}/payload_{s["id"]}.json'], 60)
    try:
        resp = json.loads(out)
    except Exception:
        return None, f'post fail: {out[:150]}'
    pid = resp.get('prompt_id')
    return (pid, '') if pid else (None, json.dumps(resp)[:150])


def wait_pid(pid, max_wait=180):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        rc, out, _ = sh(SSH + [f'curl -s -m 10 {COMFY}/history/{pid}'], 40)
        try:
            h = json.loads(out)
        except Exception:
            h = {}
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
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', path], capture_output=True, text=True, timeout=30)
    try:
        return float(r.stdout.strip())
    except Exception:
        return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    slots = json.load(open(SLOTS, encoding='utf-8'))
    tts = [s for s in slots if s['mode'] == 'tts']
    plan = cut_refs(tts)
    print(f"[refs] {len(plan)} 条逐槽参考切好 (源=原片干声)", flush=True)
    if not push_refs():
        sys.exit(1)

    manifest, errs = [], []
    t0 = time.time()
    for idx, s in enumerate(tts):
        sid = s['id']
        final = f'{OUT_DIR}/tts_{sid}.flac'
        if os.path.exists(final):
            gd = probe_dur(final)
            ratio = (gd / s['dur']) if (gd and s['dur']) else None
            manifest.append({'id': sid, 'status': 'cached', 'gen_dur': gd, 'slot_dur': s['dur'],
                             'ratio': round(ratio, 3) if ratio else None, **plan[sid]})
            continue
        for attempt in range(2):
            df = 1.0
            if attempt == 1:
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
                   'slot_dur': s['dur'], 'ratio': round(ratio, 3) if ratio else None,
                   'df': df, **plan[sid]}
            if attempt == 0:
                manifest.append(rec)
            else:
                manifest = [m if m['id'] != sid else rec for m in manifest]
            flag = '' if (ratio and 0.92 <= ratio <= 1.08) else ' ⚠️dur'
            print(f"[{idx+1}/{len(tts)}] {sid} OK {gd:.2f}s/{s['dur']:.2f}s r={ratio:.2f} df={df} "
                  f"ref={plan[sid]['ref_start']}-{plan[sid]['ref_end']}{flag}", flush=True)

    json.dump({'manifest': manifest, 'errors': errs},
              open(f'{OUT_DIR}/l4_manifest_v81.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_ok = sum(1 for m in manifest if m['status'] == 'ok')
    in_band = sum(1 for m in manifest if m.get('ratio') and 0.92 <= m['ratio'] <= 1.08)
    print(f"=== L4-V8.1 done: {n_ok} ok / {len(errs)} err, 带内 {in_band}/{n_ok}, {time.time()-t0:.0f}s ===", flush=True)


if __name__ == '__main__':
    main()
