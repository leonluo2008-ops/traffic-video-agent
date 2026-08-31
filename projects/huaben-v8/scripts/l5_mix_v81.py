# -*- coding: utf-8 -*-
"""dahua V8 L5: 混流合成 (v7 复盘三项改进全上)
改进 vs v7:
  1. DUCKING: 伴奏不再恒定 -8dB, 改 sidechaincompress 由人声动态压伴奏
  2. LOUDNORM: 最终混音 EBU R128 响度归一 (I=-16, 短视频标准)
  3. KEEP 槽原声从 Demucs vocals 干声轨取段 (比 v7 从 raw 混音轨取干净)

音轨结构:
  bg    = Demucs no_vocals.wav 全长
  voice = 28 TTS flac @槽起点 + 1 KEEP 段(vocals.wav 切片) @V8-017 起点
  mix   = sidechaincompress(bg, voice) + voice -> loudnorm
  final = raw video (视觉轨, 0-127s) + mix
"""
import json, os, subprocess, tempfile

import re as _re
BASE = next(os.path.join(p, d) for p in ['/home/luo/projects/traffic-video-agent/projects']
           for d in sorted(os.listdir(p), reverse=True)
           if _re.match(r'^hu[ai]ben-v8$', d) and 'build' not in d
           and os.path.exists(os.path.join(p, d, 'research', 'slots_v8_filled.json')))
TTS_DIR = '/tmp/huaben-v8/tts_out81'
DEM = f'{BASE}/research'          # Demucs 产物 (vocals.wav / no_vocals.wav 实际落此)
RAW_V = f'{BASE}/素材/大话西游素材_raw.mp4'   # 全片视频
SLOTS = json.load(open(f'{BASE}/research/slots_v8_filled.json', encoding='utf-8'))
OUT = f'{BASE}/输出'
os.makedirs(OUT, exist_ok=True)


def dur(p):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return None


def find_stem():
    for root, _, files in os.walk(DEM):
        if 'no_vocals.wav' in files:
            return root
    return None


def build_voice_track(tmp):
    """adelay 逐槽定位 + amix 归一(不除权, 保持响度): 分层 mix"""
    inputs, filters = [], []
    n = 0
    for s in SLOTS:
        sid, st = s['id'], s['start']
        if s['mode'] == 'keep_original':
            src = f"{tmp}/keep_{sid}.wav"
            # 从 vocals 干声轨切
            subprocess.run(['ffmpeg', '-y', '-v', 'error',
                            '-ss', f"{st:.3f}", '-t', f"{s['dur'] + 0.3:.3f}",
                            '-i', f'{find_stem()}/vocals.wav',
                            '-ar', '24000', '-ac', '1', src], check=True)
        else:
            src = f"{TTS_DIR}/tts_{sid}.flac"
            if not os.path.exists(src):
                print(f"!! 缺 {sid}, 跳过"); continue
        inputs += ['-i', src]
        # 毫秒 adelay
        filters.append(f"[{n}:a]adelay={int(st*1000)}|{int(st*1000)}[v{n}]")
        n += 1
    # amix: inputs=N, dropout_transition 大值避免尾部淡出, normalize=0 保持响度
    mix_in = ''.join(f'[v{i}]' for i in range(n))
    fc = ';'.join(filters) + f';{mix_in}amix=inputs={n}:normalize=0:dropout_transition=3[vout]'
    vc = f'{tmp}/voice.wav'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', *inputs,
                    '-filter_complex', fc, '-map', '[vout]', '-ar', '48000', '-ac', '2', vc], check=True)
    return vc


def main():
    tmp = tempfile.mkdtemp(prefix='v8mix_')
    print('[1/4] voice 轨 (29槽 adelay+amix)...')
    vc = build_voice_track(tmp)
    print('  voice.wav', round(dur(vc) or 0.0, 2), 's')

    print('[2/4] ducking 伴奏 (sidechaincompress)...')
    bg = f'{find_stem()}/no_vocals.wav'
    # 主=bg 被 voice 压: threshold=0.02, ratio=8, attack=5ms release=400ms
    duck = (f"[0:a][1:a]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=350:"
            f"makeup=1[bgd]")
    ducked = f'{tmp}/bg_ducked.wav'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', bg, '-i', vc,
                    '-filter_complex', duck, '-map', '[bgd]',
                    '-ar', '48000', '-ac', '2', ducked], check=True)

    print('[3/4] 混合 + loudnorm 预扫...')
    # 两遍法: 先测再施
    probe = subprocess.run(['ffmpeg', '-i', ducked, '-i', vc, '-filter_complex',
                            '[0:a][1:a]amix=inputs=2:normalize=0,'
                            'loudnorm=print_format=json:linear=true:I=-16:TP=-1.5:LRA=11',
                            '-f', 'null', '-'], capture_output=True, text=True)
    import re as _re
    m = _re.search(r'\{[^}]*"input_i"[^}]*\}', probe.stderr, _re.S)
    stats = json.loads(m.group(0)) if m else {}
    ln = (f"loudnorm=linear=true:I=-16:TP=-1.5:LRA=11"
          f":measured_I={stats.get('input_i', -24)}:measured_TP={stats.get('input_tp', -2)}"
          f":measured_LRA={stats.get('input_lra', 11)}:measured_thresh={stats.get('input_thresh', -34)}")

    print('[4/4] 终混 + 视频封装...')
    final = f'{OUT}/大话西游-鱼鳞焊-V8.1.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error',
                    '-i', RAW_V, '-i', ducked, '-i', vc,
                    '-filter_complex',
                    f'[1:a][2:a]amix=inputs=2:normalize=0,{ln}[aout]',
                    '-map', '0:v', '-map', '[aout]',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', final], check=True)
    print('=== L5 done:', final, round(dur(final) or 0.0, 2), 's', round(os.path.getsize(final)/1e6, 1), 'MB ===')


if __name__ == '__main__':
    main()
