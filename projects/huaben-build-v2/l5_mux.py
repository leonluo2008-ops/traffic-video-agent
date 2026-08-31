# -*- coding: utf-8 -*-
"""L5 贴回成片 v7: 原画面 + (no_vocals 伴奏底 ∥ 槽区对白轨) 混音

分层:
  [0] no_vocals.wav (44.1k 立体声, 181.63s)  伴奏底, volume=1.0
  [1..70] tts_<id>.flac  每槽 adelay=start_ms, atempo 精确收口到槽 dur
  keep 槽: 原声干声 vocals.wav 切片贴回(原句直接保留)

时长收口策略:
  gen_dur -> slot_dur 精确 atempo (0.9-1.1 内音质无损); 槽内尾部 apad 补齐
  amix duration=first normalize=0 + alimiter
"""
import json, os, subprocess, sys

BASE = '/home/luo/projects/traffic-video-agent/projects/huaben-build-v2'
SLOTS = f'{BASE}/research/slots_v7_filled.json'
MANIFEST = f'{BASE}/research/l4_manifest.json'
TTS_DIR = '/tmp/huaben-v7/tts_out'
NO_VOCALS = '/tmp/huaben-v7/no_vocals.wav'
VOCALS = '/tmp/huaben-v7/vocals.wav'      # keep 槽干声源(需从 PC 拉)
SRC_VIDEO = f'{BASE}/填词版_完整成片_v5.mp4'   # 仅用视频流 (c:v copy)
OUT = f'{BASE}/deliveries/填词版_v7.mp4'
FF = 'ffmpeg'

def sh(cmd, timeout=600):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        print('CMD FAIL:', ' '.join(cmd[:6]), '...')
        print(r.stderr.decode('utf-8', errors='replace')[-500:])
    return r.returncode

def probe_dur(p):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return None

def main():
    slots = json.load(open(SLOTS, encoding='utf-8'))
    man = {m['id']: m for m in json.load(open(MANIFEST, encoding='utf-8'))}
    os.makedirs(f'{BASE}/deliveries', exist_ok=True)
    os.makedirs('/tmp/huaben-v7/l5_fit', exist_ok=True)

    # 1) keep 槽切干声 (vocals.wav 时间轴 = 原声时间轴)
    if not os.path.exists(VOCALS):
        print('拉取 vocals.wav ...')
        r = subprocess.run(['scp', '-i', '/home/luo/.ssh/pc_luo1_ed25519',
                            'leon3@100.109.238.27:D:/AI-tool/vocal-sep-server/output/htdemucs/tangbohu_16k/vocals.wav',
                            '/tmp/huaben-v7/'], capture_output=True, timeout=300)
        if r.returncode != 0:
            print('vocals 拉取失败, keep 槽回退用原声 tangbohu_16k.wav 切片')
            globals()['VOCALS'] = f'{BASE}/research/tangbohu_16k.wav'

    parts = ['[0:a]volume=1.0[bgm]']
    inputs = [NO_VOCALS]
    idx = 1
    for s in slots:
        sid = s['id']
        if s['mode'] == 'keep_original':
            src = VOCALS
            seg = f'/tmp/huaben-v7/l5_fit/keep_{sid}.wav'
            sh([FF, '-y', '-v', 'quiet', '-ss', f"{s['start']:.3f}", '-to', f"{s['end']:.3f}",
                '-i', src, '-ac', '1', '-ar', '44100', seg])
        else:
            seg = f'{TTS_DIR}/tts_{sid}.flac'
            if not os.path.exists(seg):
                print('MISSING:', seg); continue
        gd = probe_dur(seg)
        # atempo 精确收口: 目标 = slot dur (keep 槽天然对齐, 也走同管线归一化响度)
        target = s['dur']
        tempo = max(0.5, min(2.0, gd / target))
        fit = f'/tmp/huaben-v7/l5_fit/fit_{sid}.wav'
        sh([FF, '-y', '-v', 'quiet', '-i', seg, '-filter:a',
            f'atempo={tempo:.4f},apad=whole_dur={target:.3f},atrim=0:{target:.3f},volume=1.6',
            '-ac', '1', '-ar', '44100', fit])
        ms = int(s['start'] * 1000)
        parts.append(f'[{idx}:a]adelay={ms}[t{idx}]')
        inputs.append(fit)
        idx += 1

    n = idx
    parts.append(f'[bgm]' + ''.join(f'[t{i}]' for i in range(1, idx)) +
                 f'amix=inputs={n}:duration=first:normalize=0,alimiter=limit=0.95[aout]')
    script = '/tmp/huaben-v7/l5_filter.txt'
    open(script, 'w', encoding='utf-8').write(';'.join(parts))
    mixed = '/tmp/huaben-v7/l5_mixed.wav'
    cmd = [FF, '-y', '-v', 'warning']
    for p in inputs:
        cmd += ['-i', p]
    cmd += ['-filter_complex_script', script, '-map', '[aout]', '-ar', '44100', mixed]
    rc = sh(cmd, timeout=900)
    print('mix rc:', rc, '| dur:', probe_dur(mixed))

    # 2) 合画面
    rc = sh([FF, '-y', '-i', SRC_VIDEO, '-i', mixed, '-map', '0:v', '-map', '1:a',
             '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', OUT], timeout=900)
    print('final rc:', rc, '| OUT:', OUT, '| dur:', probe_dur(OUT))

if __name__ == '__main__':
    main()
