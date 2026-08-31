# -*- coding: utf-8 -*-
"""
WhisperX 完整路线: large-v3 转写 + wav2vec2 zh 字级对齐 -> slots_v2.json 时间轴校准
v3: 模糊窗口匹配 (转写错字容忍) + transcribe dump 复用 + original_track_runs 联动校准
"""
import os, sys, json, re, difflib, traceback

BASE = r"D:\AI-tool\whisperx\jobs\huaben"
FW_MODEL = r"D:\AI-tool\whisperx\models\fw-v3"
W2V2_MODEL = r"D:\AI-tool\whisperx\models\w2v2-zh"
AUDIO = os.path.join(BASE, "tangbohu_16k.wav")
SLOTS = os.path.join(BASE, "slots.json")
DUMP = os.path.join(BASE, "transcribe_dump.json")
OUT_JSON = os.path.join(BASE, "slots_v2.json")
OUT_MD = os.path.join(BASE, "timeline_calibration_report.md")

import torch

_PAIRS = ("萬万與与醜丑專专業业叢丛東东絲丝丟丢兩两嚴严喪丧個个豐丰臨临為为麗丽舉举麼么義义烏乌樂乐喬乔習习鄉乡書书買买亂乱爭争於于虧亏雲云亙亘亞亚產产畝亩親亲億亿僅仅從从倫伦倉仓儀仪們们價价眾众優优夠够傘伞嶺岭聽听誰谁對对馬马鳥鸟龍龙風风電电話话時时問问師师來来發发裡里後后幾几氣气沒没說说見见車车紅红綠绿藍蓝黃黄"
          "川穿腸肠賢贤弟弟鳥鸟鳳风鵬鹏樓楼臺台銀银鐵铁銅铜錢钱鐘钟鑼锣鼓鼓琴琴瑟瑟簫箫笛笛"
          )
_T2, _S2 = _PAIRS[0::2], _PAIRS[1::2]
assert len(_T2) == len(_S2), f"t2s mismatch {len(_T2)} vs {len(_S2)}"
T2S = str.maketrans(_T2, _S2)

def norm(t):
    t = re.sub(r"[\s,，。.!?！？、：:;；\"'“”‘’…—\-~～《》<>（）()]+", "", t)
    t = t.translate(T2S)
    return "".join(ch for ch in t.lower() if '\u4e00' <= ch <= '\u9fff' or ch.isalnum())

def fuzzy_find(cand_stream, ref, min_cover):
    """在候选字流中模糊找 ref: 返回 (cover, start_t, end_t) 或 None"""
    if not cand_stream or not ref:
        return None
    wtxt = "".join(c for c, _, _ in cand_stream)
    sm = difflib.SequenceMatcher(None, wtxt, ref, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None
    matched = sum(b.size for b in blocks)
    cover = matched / len(ref)
    i0 = blocks[0].a
    i1 = blocks[-1].a + blocks[-1].size - 1
    # 跨度惩罚: 匹配块之间的空洞 (插入噪声)
    span = i1 - i0 + 1
    score = cover - 0.02 * max(0, span - matched)
    return score, cover, cand_stream[i0][1], cand_stream[i1][2]

def main():
    doc = json.load(open(SLOTS, encoding="utf-8"))
    slots = doc["slots"] if isinstance(doc, dict) else doc
    print(f"slots: {len(slots)}", flush=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}", flush=True)

    # ---- 1. 转写 (有 dump 则复用) ----
    if os.path.exists(DUMP) and "--redo" not in sys.argv:
        segments = json.load(open(DUMP, encoding="utf-8"))
        print(f"transcribe: reuse dump ({len(segments)} segs)", flush=True)
    else:
        from faster_whisper import WhisperModel
        wm = WhisperModel(model_size_or_path=FW_MODEL, device=device,
                          compute_type="float16" if device == "cuda" else "int8")
        segments_iter, info = wm.transcribe(AUDIO, language="zh", beam_size=5, vad_filter=True,
                                            vad_parameters={"min_silence_duration_ms": 300},
                                            initial_prompt="以下是普通话简体中文句子。")
        segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments_iter]
        print(f"transcribed: {len(segments)} segments, audio {info.duration:.1f}s", flush=True)
        json.dump(segments, open(DUMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- 2. whisperx 字级对齐 ----
    import whisperx
    align_model, metadata = whisperx.load_align_model(language_code="zh", device=device, model_name=W2V2_MODEL)
    aligned = whisperx.align(segments, align_model, metadata, AUDIO, device,
                             return_char_alignments=True, print_progress=False)
    stream = []
    for seg in aligned["segments"]:
        chars = seg.get("chars")
        if chars is None:
            continue
        rows = chars.to_dict("records") if hasattr(chars, "to_dict") else chars
        for ch in rows:
            if ch.get("start") is not None and ch.get("end") is not None:
                stream.append((str(ch.get("char", "")), ch["start"], ch["end"]))
    print(f"char stream: {len(stream)} chars", flush=True)

    # ---- 3. 多层模糊匹配: 窗口优先, 拼音兜底 (同音转写错字克星) ----
    from pypinyin import lazy_pinyin
    def to_py(txt):
        return "".join(lazy_pinyin(txt))
    # 预转拼音流 (一次)
    py_stream = "".join(lazy_pinyin("".join(c for c, _, _ in stream)))
    # 音节边界索引: 每 3 个字符是 1 个拼音音节 (lazy_pinyin 输出无分隔)
    # 用逐字 pinyin 列表重建 — 精确对位
    char_py = lazy_pinyin("".join(c for c, _, _ in stream), errors=lambda cs: list(cs))
    assert len(char_py) == len(stream), f"py align mismatch {len(char_py)} vs {len(stream)}"
    py_syls = [(i, p) for i, p in enumerate(char_py)]

    def fuzzy_find_py(cand_idx, ref):
        """拼音流模糊匹配: cand_idx = 字符索引列表; 返回 (score, cover, i0, i1) 或 None"""
        import bisect
        if not cand_idx or not ref:
            return None
        syls = [py_syls[i][1] for i in cand_idx]
        starts = [0]
        for s in syls:
            starts.append(starts[-1] + len(s))
        wtxt = "".join(syls)
        rtxt = to_py(ref)
        sm = difflib.SequenceMatcher(None, wtxt, rtxt, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        if not blocks:
            return None
        matched = sum(b.size for b in blocks)
        cover = matched / len(rtxt)
        # 拼音串字符位置 -> 音节序号 -> 流索引
        p0, p1 = blocks[0].a, blocks[-1].a + blocks[-1].size - 1
        k0 = bisect.bisect_right(starts, p0) - 1
        k1 = bisect.bisect_right(starts, p1) - 1
        i0, i1 = cand_idx[k0], cand_idx[k1]
        span = i1 - i0 + 1
        score = cover - 0.02 * max(0, span - matched)
        return score, cover, i0, i1

    results = []
    for i, s in enumerate(slots):
        t0, t1 = float(s["start"]), float(s["end"])
        ref = norm(s.get("orig", ""))
        if len(ref) < 2:
            results.append({**s, "aligned": False, "align_note": "empty/too-short orig"}); continue
        # 拼音-窗口 + 拼音-全局兜底 (拼音层涵盖字面精确匹配)
        # 原声区槽 (keep/use_original_track) 禁用全局兜底: 吟唱/拖腔在全片重复出现, 全局匹配必错
        is_orig = bool(s.get("keep") or s.get("use_original_track"))
        win_idx = [j for j, c in enumerate(stream) if c[1] >= t0 - 3.5 and c[2] <= t1 + 3.5]
        min_cover = 0.75 if len(ref) <= 4 else 0.5
        best, mode = None, None
        r2 = fuzzy_find_py(win_idx, ref)
        if r2 and r2[1] >= min_cover:
            best, mode = r2, "py-win"
        if best is None and not is_orig:
            r3 = fuzzy_find_py(list(range(len(stream))), ref)
            if r3 and r3[1] >= min_cover:
                best, mode = r3, "py-global"
        if best is not None:
            score, cover, i0, i1 = best
            ns, ne = stream[i0][1], stream[i1][2]
            suspicious = abs(ns - t0) > 6.0
            if suspicious and mode == "py-global":
                # 全局兜底位移过大 = 误匹配, 保留原标注时间只打标
                results.append({**s, "aligned": False, "align_note": "global-match-suspect"}); continue
            results.append({**s, "aligned": True, "start": round(ns, 3), "end": round(ne, 3),
                            "shift": round(ns - t0, 3), "cover": round(cover, 2),
                            "match_mode": mode, "suspicious": suspicious})
        else:
            results.append({**s, "aligned": False, "align_note": "low-cover"})
        r_ = results[-1]
        if (i + 1) % 10 == 0 or i == len(slots) - 1 or not r_.get("aligned"):
            tag = "OK " if r_.get("aligned") else "MISS"
            ns = r_.get("start"); ne = r_.get("end")
            print(f"[{i+1}/{len(slots)}] {tag} {s.get('id','?')} {t0:.2f}->{t1:.2f}"
                  + (f" => {ns:.2f}->{ne:.2f} shift={r_['shift']:+.2f} cover={r_.get('cover')}"
                     if r_.get("aligned") else f" ({r_.get('align_note')})"), flush=True)

    # ---- 4. original_track_runs 联动: 用首尾槽校准 ----
    runs = doc.get("original_track_runs", []) if isinstance(doc, dict) else []
    id2r = {r["id"]: r for r in results}
    runs_v2 = []
    for run in runs:
        r_new = dict(run)
        first, last = id2r.get(run["first"]), id2r.get(run["last"])
        if first and first.get("aligned"):
            r_new["start"] = first["start"]
        if last and last.get("aligned"):
            r_new["end"] = last["end"]
        runs_v2.append(r_new)
        print(f"run {run['first']}~{run['last']}: {run['start']:.2f}~{run['end']:.2f}"
              f" => {r_new['start']:.2f}~{r_new['end']:.2f}", flush=True)

    out = {"source": doc.get("source", ""), "total": doc.get("total"),
           "slots": results, "original_track_runs": runs_v2}
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- 5. 报告 ----
    import statistics
    ok = [r for r in results if r.get("aligned") and not r.get("suspicious")]
    shifts = [r["shift"] for r in ok]
    md = ["# 时间轴校准报告 (WhisperX 字级对齐 + 模糊匹配 v3)", "",
          f"- slots: {len(results)}  对齐: {sum(1 for r in results if r.get('aligned'))}"
          f"  其中可疑(位移>6s): {sum(1 for r in results if r.get('suspicious'))}"
          f"  失败: {sum(1 for r in results if not r.get('aligned'))}",
          f"- 位移(可信集): 中位 {statistics.median(shifts):+.3f}s  均值 {statistics.mean(shifts):+.3f}s"
          f"  |max| {max(map(abs, shifts)):.3f}s", ""]
    for r in results:
        if not r.get("aligned"):
            md.append(f"- ✗ {r['id']} [{r['start']}~{r['end']}] {r.get('align_note','')} — 保留标注值")
    md += ["", "| id | 标注 | 实测 | 位移 | 覆盖率 | 模式 |", "|---|---|---|---|---|---|"]
    orig = {s["id"]: s for s in slots}
    for r in results:
        if r.get("aligned"):
            o = orig.get(r["id"], r)
            flag = " ⚠" if r.get("suspicious") else ""
            md.append(f"| {r['id']}{flag} | {float(o['start']):.2f}~{float(o['end']):.2f}"
                      f" | {r['start']:.2f}~{r['end']:.2f} | {r['shift']:+.2f}"
                      f" | {r.get('cover')} | {r.get('match_mode')} |")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(md))
    print(f"\nDONE: {sum(1 for r in results if r.get('aligned'))}/{len(results)} aligned", flush=True)
    print(f"median shift (trusted): {statistics.median(shifts):+.3f}s", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)