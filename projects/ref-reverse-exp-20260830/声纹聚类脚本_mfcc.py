
import numpy as np, json, subprocess
from python_speech_features import mfcc
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform
import wave

blocks = json.load(open("/tmp/v2_blocks.json"))
frame_sets = {}
for i, (a, b) in enumerate(blocks):
    if b - a < 0.30:
        continue
    fp = f"/tmp/spk_blk{i}.wav"
    w = wave.open(fp)
    n = w.getnframes()
    sig = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    w.close()
    mf = mfcc(sig, samplerate=16000, winlen=0.025, winstep=0.01, numcep=20, nfilt=26)
    d = np.diff(mf, axis=0)
    d = np.vstack([d[:1], d])
    X = np.concatenate([mf, d], axis=1)  # 帧级 40 维
    # 按帧能量加权：响度大的帧更能代表说话人
    frame_sets[i] = X

# 块间距离：用对称化的 Hausdorff-like 度量 = 两组帧特征互近邻平均余弦距离
ids = sorted(frame_sets)
import itertools
D = np.zeros((len(ids), len(ids)))
normed = {i: frame_sets[i] / (np.linalg.norm(frame_sets[i], axis=1, keepdims=True) + 1e-8) for i in ids}
for x, y in itertools.combinations(range(len(ids)), 2):
    A, B = normed[ids[x]][:, :20], normed[ids[y]][:, :20]  # 只用 cepstral 部分
    An, Bn = A / (np.linalg.norm(A, axis=1, keepdims=True)+1e-8), B / (np.linalg.norm(B, axis=1, keepdims=True)+1e-8)
    S = An @ Bn.T
    dxy = (1 - S.max(axis=1)).mean()
    dyx = (1 - S.max(axis=0)).mean()
    d = (dxy + dyx) / 2
    D[x, y] = D[y, x] = d

print("块间距离矩阵 (0=同一人, 越大越不同):")
print("      " + "  ".join(f"B{i}" for i in ids))
for x in range(len(ids)):
    print(f"B{ids[x]}  " + "  ".join(f"{D[x, y]:.3f}" for y in range(len(ids))))

Z = linkage(squareform(D), method="average")
for k in [2, 3]:
    labels = fcluster(Z, t=k, criterion="maxclust")
    cl = {}
    for i, lab in zip(ids, labels):
        cl.setdefault(lab, []).append(i)
    print(f"\n=== k={k} ===")
    for lab, members in sorted(cl.items()):
        print(f"  Speaker {chr(64+lab)}: " + ", ".join(f"块{m}({blocks[m][0]:.1f}-{blocks[m][1]:.1f})" for m in members))
