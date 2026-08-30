# -*- coding: utf-8 -*-
"""
slots_v2 → slots_v3 数据契约修正器 (v2, 2026-08-30 用户裁决: 画本审核值不作准, Whisper 优先)
规则:
  R1 dur 派生: = end-start 重算
  R2 KEEP 槽: Whisper 匹配值优先 (cover>=0.6 且 span比∈[0.4,2.5] 直接吃);
     低质 → ASR 段锚定; 无匹配(蒙太奇无语音区) → 画本标注仅作占位
  R3 TTS 槽: 同 R2 阈值; 低质 → ASR 段锚定
  R3.5 对联混战区: 证据表终审 (含槽手术: N38/N44 复合槽拆分, N46 '群众'误标并入台词,
     漏收台词补 KEEP 槽) — 无 needs_review 拍板环节, 证据即终审 (用户 2026-08-30 裁决)
  R4 全局一致性: 排序 → 中点切分 → 倒挂 ASR 重锚; 禁止回退画本值
  R5 校验: dur 一致 / 零重叠 / TTS 语速∈[1.2,8]字/s / run 与 TTS 零冲突
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
        st, en, rule = o["start"], o["end"], "R2-montage-placeholder(Whisper无语音)"
    else:
        m_st, m_en = s["start"], s["end"]
        span, cover = m_en - m_st, s.get("cover", 0)
        ratio = span / a_dur if a_dur else 9.9
        if cover >= 0.6 and 0.4 <= ratio <= 2.5:
            st, en, rule = m_st, m_en, f"whisper-accept(cover={cover},r={ratio:.2f})"
        else:
            best = max(segs, key=lambda g: min(g["end"], m_en) - max(g["start"], m_st))
            prev_end = final[-1]["end"] if final else 0.0
            st = max(best["start"], prev_end + 0.05)
            en = max(st + 0.3, best["end"])
            rule = f"asr-snap(cover={cover},r={ratio:.2f})"
    audit.append(f"{s['id']:5s} {'KEEP' if keep else 'TTS'} {o['start']:7.2f}~{o['end']:7.2f} -> {st:7.2f}~{en:7.2f}  {rule}")
    final.append({**s, "start": round(st, 3), "end": round(en, 3)})

# ---- R3.5 证据表终审 + 槽手术 (对联混战区 117~182s, 全部来源=transcribe_dump ASR 段) ----
# 槽手术:
#   N38 复合槽拆 N38a/N38b ('哈哈真行啊' 漏收句补 K1 KEEP)
#   N44 复合槽拆 N44a/N44b (N46 '群众chanting'=误标, 实为台词'鱼肥果熟入我肚'→N44b;
#       '奴家灶头怎配鱼' 漏收句补 K2 KEEP)
SURGERY = {
    "N38": [
        {"id": "N38a", "start": 126.40, "end": 128.90, "role": "华安+群杂",
         "orig": "年年暮暮朝朝", "text": "虚虚假假，年年岁岁", "keep": False, "use_original_track": False,
         "evidence": "ASR[122.66~128.90]尾段(叠字链后半, 与N37同段按字数比切)"},
        {"id": "N38b", "start": 131.99, "end": 134.22, "role": "华安+群杂",
         "orig": "快出对子对死他", "text": "快出对子对死他", "keep": False, "use_original_track": False,
         "evidence": "ASR[131.99~134.22] 全段"},
        {"id": "K1", "start": 129.99, "end": 131.99, "role": "华安",
         "orig": "哈哈真行啊", "text": "", "keep": True, "use_original_track": False,
         "evidence": "ASR[129.99~131.99] 表演依赖笑句, KEEP 原声"},
    ],
    "N44": [
        {"id": "N44a", "start": 155.22, "end": 158.22, "role": "对穿肠",
         "orig": "我家坟头来种树", "text": "盆满钵满入我囊", "keep": False, "use_original_track": False,
         "evidence": "ASR[155.22~158.22] 全段 (复合槽前半)"},
        {"id": "N44b", "start": 160.74, "end": 162.46, "role": "对穿肠",
         "orig": "鱼肥果熟入我肚", "text": "坑爹车主赚得欢", "keep": False, "use_original_track": False,
         "evidence": "ASR[160.74~162.46]'鱼飞过船入我洞'=同音错字; 旧N46'群众chanting'为误标, 实为台词"},
        {"id": "K2", "start": 158.22, "end": 160.26, "role": "华安",
         "orig": "鱼肥果熟入我肚(对句)", "text": "", "keep": True, "use_original_track": False,
         "evidence": "ASR[158.22~160.26]'奴家灶盆杂配鱼' 画本漏收, 戏腔对句 KEEP 原声"},
    ],
    "N46": None,   # 删除: 误标'群众', 时段归 N44b
}
EVIDENCE = {
    "N37": (122.66, 126.40, "ASR[122.66~128.90]前段(叠字链前半, 字数比12/20切)"),
    "N39": (134.22, 138.22, "ASR 全段'十口心思思君思国思社稷+八目共赏'"),
    "N40": (137.40, 141.22, "'八目共赏'尾接'赏花赏月赏秋香'=ASR[138.22~141.22]"),
    "N41": (143.22, 148.22, "ASR 全段(同音错字版 orig)"),
    "N42": (148.22, 151.22, "ASR 全段"),
    "N43": (151.22, 155.22, "ASR 全段"),
    "N45": (162.66, 164.66, "ASR 全段'你老娘来亲下厨'"),
    "N47": (170.48, 174.44, "ASR[170.48~171.96]+[171.96~174.44] 两段合"),
    "N48": (174.44, 177.04, "ASR[174.44~175.64]+[175.64~177.04] 两段合"),
    "N49": (177.04, 181.02, "笑声'哈哈'在177~179(ASR漏捕非语音)+台词ASR[179.22~181.02]; 18字/3.98s=4.5字/s"),
    "N50": (181.06, 181.70, "片尾残段, ASR[181.26~]'你出'=片尾截断不入槽"),
}
# 应用手术
_out = []
for s in final:
    sid = s["id"]
    if sid in SURGERY:
        if SURGERY[sid] is None:
            audit.append(f"  R3.5 DEL {sid} (误标, 时段归 N44b)")
            continue
        for repl in SURGERY[sid]:
            _out.append({**{k: v for k, v in s.items() if k not in ("start", "end", "dur", "id", "orig", "text", "keep", "use_original_track", "shift", "cover", "match_mode", "aligned", "evidence")}, **repl})
            audit.append(f"  R3.5 SPLIT {repl['id']} -> {repl['start']:.2f}~{repl['end']:.2f}  {repl['evidence'][:36]}")
    else:
        _out.append(s)
final = _out
for s in final:
    if s["id"] in EVIDENCE:
        st, en, note = EVIDENCE[s["id"]]
        s["start"], s["end"] = round(st, 3), round(en, 3)
        s["evidence"] = note
        audit.append(f"  R3.5 {s['id']:5s} -> {st:7.2f}~{en:7.2f}  证据: {note[:38]}")

# ---- R4: 排序 → 迭代中点切分 → 倒挂 ASR 重锚 (禁止回退画本) ----
final.sort(key=lambda s: s["start"])
trims = []
def overlaps():
    return [(i-1, i) for i in range(1, len(final)) if final[i]["start"] < final[i-1]["end"] - 0.001]
guard = 0
while overlaps() and guard < 8:
    guard += 1
    for a, b in overlaps():
        mid = (final[b]["start"] + final[a]["end"]) / 2
        final[a]["end"] = round(mid - 0.02, 3); final[b]["start"] = round(mid + 0.02, 3)
        trims.append(f"R4-trim {final[a]['id']}~{final[b]['id']} @ {mid:.2f}")
    # 倒挂槽 ASR 重锚
    for i, s in enumerate(final):
        if s["end"] - s["start"] < 0.25:
            best = max(segs, key=lambda g: min(g["end"], s["end"]) - max(g["start"], s["start"]))
            prev_end = final[i-1]["end"] if i > 0 else 0.0
            st = max(best["start"], prev_end + 0.05); en = max(st + 0.3, min(best["end"], 181.70))
            s["start"], s["end"] = round(st, 3), round(en, 3)
            s["evidence"] = (s.get("evidence", "") + " | R4倒挂ASR重锚").strip(" |")
            trims.append(f"R4-reanchor {s['id']} -> {st:.2f}~{en:.2f}")
final.sort(key=lambda s: s["start"])

# R1 dur 派生
for s in final:
    s["dur"] = round(s["end"] - s["start"], 3)

# runs 重建 + TTS 冲突钳制 (TTS 校准值优先, 直用区让位)
ids = [s["id"] for s in final]
runs = []
for r in v2["original_track_runs"]:
    if r["first"] not in ids or r["last"] not in ids: continue
    a, b = ids.index(r["first"]), ids.index(r["last"])
    st = min(x["start"] for x in final[a:b+1]); en = max(x["end"] for x in final[a:b+1])
    runs.append({"first": r["first"], "last": r["last"], "start": round(st,3), "end": round(en,3)})
tts_spans = [(s["start"], s["end"]) for s in final if not (s.get("keep") or s.get("use_original_track"))]
for r in runs:
    for ts, te in tts_spans:
        if te > r["start"] and ts < r["end"]:
            if ts >= r["start"]: r["end"] = min(r["end"], round(ts - 0.05, 3))
            else:               r["start"] = max(r["start"], round(te + 0.05, 3))
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
print(f"\nslots: {len(final)} (TTS {sum(1 for s in final if not (s.get('keep') or s.get('use_original_track')))}, KEEP {sum(1 for s in final if s.get('keep') or s.get('use_original_track'))})")
print("ERRS:", errs if errs else "NONE ✓")
print("FLAGS(人审):"); print("\n".join("  " + f for f in flags) if flags else "  NONE ✓")

if not errs:
    json.dump({"source": old["source"], "total": len(final), "slots": final, "original_track_runs": runs},
              open(f"{BASE}/slots_v3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nslots_v3.json WRITTEN")
else:
    print("\nNOT WRITTEN — fix errors first")