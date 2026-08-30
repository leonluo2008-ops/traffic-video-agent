# -*- coding: utf-8 -*-
"""
slots_v2 → slots_v3 数据契约修正器 (2026-08-30 v6 复盘定规)
规则 (R1-R5), 全部源自 v2 实测事故:
  R1 dur 是派生量: 永远 = end-start 重算 (v2 事故: 53 槽 dur 全是旧标注值 → atempo 目标错)
  R2 KEEP 槽(人工审核画本值)只读: 机器匹配仅在 cover>=0.75 且 span∈[0.5,1.67]×原dur 才可写;
     run 边界槽(first/last)放宽为 cover>=0.75 即可(只影响直用区拼接缝, 不进 TTS)
     (v2 事故: N46 1.5s 被撑成 6.7s)
  R3 TTS 槽机器实测优先, 但低质匹配(cover<0.6 或 span 比例出 [0.4,2.5])降级为
     "锚定 ASR 段边界" (v2 事故: N37 0.95s 装 10 字, N41 1.39s 装 11 字)
  R4 全局一致性闸门: 逐槽独立匹配后必须过 单调+零重叠 pass, 冲突中点切分
     (v2 事故: N43/N44 互叠, N47/N48/N49 三槽乱序)
  R5 进生产前校验: dur 一致 / 零重叠 / TTS 语速 ∈[1.2,8]字/s(Flag 人工审) / run 与 TTS 零冲突
"""
import json, re

BASE = "/home/luo/projects/traffic-video-agent/projects/huaben-build-v2"
old = json.load(open(f"{BASE}/slots.json", encoding="utf-8"))
v2  = json.load(open(f"{BASE}/slots_v2.json", encoding="utf-8"))
segs = json.load(open("/tmp/transcribe_dump.json", encoding="utf-8"))
O = {s["id"]: s for s in old["slots"]}
run_bound_ids = {m for r in v2["original_track_runs"] for m in (r["first"], r["last"])}

def nchars(t): return len(re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", t or ""))

final, audit = [], []
for s in v2["slots"]:
    o = O[s["id"]]
    a_dur = o["end"] - o["start"]
    keep = bool(s.get("keep") or s.get("use_original_track"))
    if not s.get("aligned"):
        st, en, rule = o["start"], o["end"], "R2-restore(unmatched)"
    else:
        m_st, m_en = s["start"], s["end"]
        span, cover = m_en - m_st, s.get("cover", 0)
        ratio = span / a_dur if a_dur else 9.9
        if keep:
            if s["id"] in run_bound_ids and cover >= 0.75:
                st, en, rule = m_st, m_en, f"R2-runbound(cover={cover})"
            elif cover >= 0.75 and 0.5 <= ratio <= 1.67:
                st, en, rule = m_st, m_en, f"R2-keep-ok(cover={cover},r={ratio:.2f})"
            else:
                st, en, rule = o["start"], o["end"], f"R2-keep-restore(cover={cover},r={ratio:.2f})"
        else:
            if cover >= 0.6 and 0.4 <= ratio <= 2.5:
                st, en, rule = m_st, m_en, f"R3-accept(cover={cover},r={ratio:.2f})"
            else:
                best = max(segs, key=lambda g: min(g["end"], m_en) - max(g["start"], m_st))
                prev_end = final[-1]["end"] if final else 0.0
                st = max(best["start"], prev_end + 0.05)
                en = max(st + 0.3, best["end"])
                rule = f"R3-asr-snap(cover={cover},r={ratio:.2f},seg={best['start']:.2f}~{best['end']:.2f})"
    audit.append(f"{s['id']:5s} {'KEEP' if keep else 'TTS'} {o['start']:7.2f}~{o['end']:7.2f} -> {st:7.2f}~{en:7.2f}  {rule}")
    final.append({**s, "start": round(st, 3), "end": round(en, 3)})

# ---- R3.5 对联混战区证据裁决 (146~181s: 槽↔ASR 非一对一, 算法无正义, 按证据表硬裁决) ----
# 每条来源 = transcribe_dump.json ASR 段 (同音错字已人工解码); None = 回退画本标注待用户拍板
EVIDENCE = {
    "N37": (122.66, 126.40, "对穿肠被逼念叠字链 ASR[122.66~128.90]前段(字数比12/20);后半'年年暮暮昭昭'归 N38 前半"),
    "N38": (131.99, 134.22, "复合槽: 前半'年年暮暮朝朝'在 ASR[126.4~128.9] 尾部(与N37同段), 后半'快出对子对死她'=ASR[131.99~134.22];取后半+needs_review"),
    "N39": (134.22, 138.22, "ASR[134.22~138.22]'十口心似四军四国似设计八目共赏' 全段"),
    "N40": (137.40, 141.22, "'八目共赏'=ASR[134.22~138.22]尾 + '赏花赏月赏秋香'=ASR[138.22~141.22]; 取衔接点"),
    "N41": (143.22, 148.22, "ASR[143.22~148.22]'我尚等魏玉峰陷陷一身胡胆'=同音错字版 orig"),
    "N42": (148.22, 151.22, "ASR 全段"),
    "N43": (151.22, 155.22, "ASR 全段"),
    "N44": (155.22, 158.22, "复合槽只取前半'我家坟头来种树'=ASR[155.22~158.22]; 后半'鱼肥果熟入我肚'=ASR[160.74~162.46]与 N46 重叠 → needs_review"),
    "N45": (162.66, 164.66, "ASR 全段'你老娘来倾下厨'"),
    "N46": (160.74, 162.46, "画本标'群众chanting'实为台词'鱼肥果熟入我肚'(ASR'鱼飞过船入我洞'同音错字); KEEP 原声无音频影响 → needs_review"),
    "N47": (170.48, 174.44, "ASR[170.48~171.96]+[171.96~174.44] 两段合"),
    "N48": (174.44, 177.04, "ASR[174.44~175.64]+[175.64~177.04] 两段合"),
    "N49": (177.04, 181.02, "真实跨度=笑声+台词: '哈哈'在 177~179 (ASR 漏捕笑声), '华安哪这儿没你的事了'=ASR[179.22~181.02]; 18字/3.98s=4.5字/s ✓"),
    "N50": (181.06, 181.70, "收尾余音让位 N49 后仅剩片尾残段 (ASR[181.26~181.74]'你出'= 片尾截断不入槽)"),
}
REVIEW = {"N38", "N44", "N46"}   # 画本结构级争议, 交用户拍板
for s in final:
    if s["id"] in EVIDENCE:
        st, en, note = EVIDENCE[s["id"]]
        s["start"], s["end"] = round(st, 3), round(en, 3)
        s["evidence"] = note
        if s["id"] in REVIEW: s["needs_review"] = True
        audit.append(f"  R3.5 {s['id']:5s} -> {st:7.2f}~{en:7.2f}  证据: {note[:38]}")

# ---- R4 一致性 pass: 先按 start 排序 (槽列表序≠时间序, v3 事故), 再中点切分 ----
order0 = {s["id"]: k for k, s in enumerate(final)}
final.sort(key=lambda s: s["start"])
trims = []
for i in range(1, len(final)):
    a, b = final[i-1], final[i]
    if b["start"] < a["end"] - 0.001:
        mid = (b["start"] + a["end"]) / 2
        a["end"] = round(mid - 0.02, 3); b["start"] = round(mid + 0.02, 3)
        trims.append(f"R4-trim {a['id']}~{b['id']} @ {mid:.2f}")
# 切分后若倒挂 (start >= end) 回退为标注值
for i, s in enumerate(final):
    if s["end"] - s["start"] < 0.25:
        o = O[s["id"]]; s["start"], s["end"] = o["start"], o["end"]; s["needs_review"] = True
        trims.append(f"R4-collapse {s['id']} -> 回退标注")

# R4-final: 残余冲突簇整体回退画本标注值 (标注版零重叠 by construction; 机器值互相矛盾的簇不可信)
guard = 0
while guard < 5:
    guard += 1
    final.sort(key=lambda s: s["start"])
    hit = None
    for i in range(1, len(final)):
        if final[i]["start"] < final[i-1]["end"] - 0.001:
            hit = i; break
    if hit is None: break
    lo, hi = hit - 1, hit
    grown = True
    while grown:
        T = lambda x: bool(x.get("keep") or x.get("use_original_track"))
        grown = False
        if lo > 0 and final[lo-1]["end"] > final[lo]["start"]: lo -= 1; grown = True
        if hi < len(final)-1 and final[hi+1]["start"] < final[hi]["end"]: hi += 1; grown = True
    # TTS 与 KEEP 冲突: KEEP (原声直用/直切) 让位 — TTS 需要足够时长装下新词
    T = lambda x: bool(x.get("keep") or x.get("use_original_track"))
    if T(final[lo]) != T(final[hi]):
        tts_side, keep_side = (hi, lo) if T(final[lo]) else (lo, hi)
        tts_s = final[tts_side]
        need = nchars(tts_s.get("text")) / 5.0   # 5字/s 基线预算
        have = tts_s["end"] - tts_s["start"]
        if have < need:
            tts_s["end"] = round(min(tts_s["end"] + (need - have), 181.70), 3)
            audit.append(f"  R4-keep-yield {tts_s['id']} 扩到 {tts_s['end']:.2f} (需{need:.1f}s 装词)")
            continue
    for k in range(lo, hi+1):
        s = final[k]; o = O[s["id"]]
        s["start"], s["end"] = o["start"], o["end"]; s["needs_review"] = True
    trims.append(f"R4-cluster-revert {[final[k]['id'] for k in range(lo, hi+1)]} -> 画本标注")

# R1 dur 派生
for s in final:
    s["dur"] = round(s["end"] - s["start"], 3)

# runs 重建 + TTS 冲突钳制 (TTS 是校准过的, 直用区让位)
ids = [s["id"] for s in final]
runs = []
for r in v2["original_track_runs"]:
    a, b = ids.index(r["first"]), ids.index(r["last"])
    st = min(x["start"] for x in final[a:b+1]); en = max(x["end"] for x in final[a:b+1])
    runs.append({"first": r["first"], "last": r["last"], "start": round(st,3), "end": round(en,3)})
tts_spans = [(s["start"], s["end"]) for s in final if not (s.get("keep") or s.get("use_original_track"))]
for r in runs:
    for ts, te in tts_spans:
        if te > r["start"] and ts < r["end"]:          # 有交叠
            if ts >= r["start"]: r["end"] = min(r["end"], round(ts - 0.05, 3))    # TTS 在尾部 → 收 run 尾
            else:               r["start"] = max(r["start"], round(te + 0.05, 3)) # TTS 在头部 → 推 run 头
for i in range(1, len(runs)):
    if runs[i]["start"] < runs[i-1]["end"]:
        mid = (runs[i]["start"] + runs[i-1]["end"]) / 2
        runs[i-1]["end"] = round(mid - 0.02, 3); runs[i]["start"] = round(mid + 0.02, 3)

# R5 校验
errs, flags = [], []
for i, s in enumerate(final):
    if i and s["start"] < final[i-1]["end"] - 0.001: errs.append(f"overlap {final[i-1]['id']}/{s['id']}")
    if abs(s["dur"] - (s["end"] - s["start"])) > 0.002: errs.append(f"dur-stale {s['id']}")
    if not (s.get("keep") or s.get("use_original_track")):
        cs = nchars(s.get("text")) / s["dur"] if s["dur"] else 99
        if not 1.2 <= cs <= 8:
            flags.append(f"{s['id']} 语速{cs:.1f}字/s dur={s['dur']}s text={s.get('text','')[:16]}")
for i, r in enumerate(runs):
    if i and r["start"] < runs[i-1]["end"] - 0.001: errs.append(f"run-overlap #{i-1}/#{i}")
    for ts, te in tts_spans:
        if te > r["start"] + 0.06 and ts < r["end"] - 0.06: errs.append(f"run/TTS-clash {r['first']}~{r['last']} vs {ts:.1f}")

print("\n".join(audit)); print()
print("\n".join(trims) if trims else "(no R4 trims)"); print()
for r in runs: print("run:", r)
print("\nERRS:", errs if errs else "NONE ✓")
print("FLAGS(人审):"); print("\n".join("  " + f for f in flags) if flags else "  NONE ✓")

if not errs:
    json.dump({"source": old["source"], "total": old["total"], "slots": final, "original_track_runs": runs},
              open(f"{BASE}/slots_v3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nslots_v3.json WRITTEN")
else:
    print("\nNOT WRITTEN — fix errors first")