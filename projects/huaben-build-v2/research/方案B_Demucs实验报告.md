# 方案B实验报告：Demucs 人声分离预处理（2026-08-31）

## 结论

**不切换主线。** 决策规则三条门（设计文档 commit 9f841eb）过了零条半——B 流字数门通过（-0.5%≤3%），score 门与混战区保留字数门均失败。

## 六指标对比（同口径复跑）

| 指标 | 基线（原声混音） | Demucs vocals | 方向 |
|---|---|---|---|
| B 流总字数 | 429 | 427 | -2 |
| 绝对覆盖字数 | 374/429 (87%) | 372/427 (87%) | 持平 |
| 槽位数 | 76 | 75 | -1 |
| 混战区（119-166s）槽/字 | 24 槽 122 字 | 23 槽 120 字 | 微降 |
| 混战区槽粒度 min/中位/max | 0.4/1.1/2.6s | 0.4/1.0/2.6s | 持平 |
| score 中位 | 0.928 | 0.924 | -0.004 ✗ |
| difflib 融合相似度 | 0.748 | 0.748 | 持平 |

vocals 版 low(<0.5) score 率：14/437 (3.2%)。

## 判读

1. **假设证伪**：混战区（对联互喷段）对齐差的根因不是背景乐干扰，而是**多说话人语音重叠**——Demucs 只分离「人声 vs 伴奏」，不分「人声 vs 人声」。htdemucs 对 1993 国语配音混音分离干净（GPU 4.9s），但对重叠对白无能为力，分离后甚至轻微损伤（score -0.004，混战区 -2 字）。
2. **VideoLingo 的收益场景不适用于本素材**：其 release note 场景是「BGM 响、漏句多」的现代剧集；本片段 BGM 本就不重。
3. **正面价值**：管线更简单——v7 主线不引入 Demucs 依赖；混战区精度问题的出路在别处（说话人分离/L3 层容错/人工锚点），不在预处理。

## 执行记录

- 复用 PC 既有 `D:\AI-tool\vocal-sep-server`（demucs 4.1.0 + ComfyUI python，htdemucs --two-stems=vocals），GPU 分离 187.2s 音频耗时 4.9s
- `v7_probe_align_v2.py`（PC jobs/huaben/）：转写文本沿用原声版（单变量），仅对齐音频换 vocals → align_dump_v2.json（437 字戳）
- `l2v4_fusion_v2.py`（本 research/）：B 流换 v2 dump，能量标注源换 vocals.wav，输出 slots_v7_demucs.json（75 槽）
- vocals.wav / no_vocals.wav 未入 git（32MB 可再生：`python -m demucs -n htdemucs --two-stems=vocals input/tangbohu_16k.wav`）

## 附注：文件系统异常

实验期间本机出现目录级闪断（research/ 及父目录反复 ENOENT，dmesg 有 `delayed_fput hogged CPU` 记录，疑与 rclone FUSE 挂载相关）。本报告及产物经 git 对象库直接提取/重试窗口提交，数据未受损。建议择机重启观察。
