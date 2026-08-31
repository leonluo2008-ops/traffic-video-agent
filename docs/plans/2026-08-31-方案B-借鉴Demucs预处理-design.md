# 2026-08-31 方案B：借鉴成熟项目组件强化 v7 管线 — 设计文档

## 背景

用户拍板方案 B：不整仓部署 Linly-Dubbing/VideoLingo，继续 v7 自研管线，**学习借鉴**两个成熟项目里已验证的组件。当前 v7 进度：L0-L2 已通（76 槽 / 87% 覆盖），L3-L5 未动。

## 借鉴点（已核实来源）

### 借鉴 ①：Demucs 人声分离预处理（来自 VideoLingo release note）

VideoLingo 官方 release：「先对原声 ASR，再用 Demucs 降噪后的音频做强制对齐，极大改善了漏句问题」。

我们的痛点对应：对联混战区（119-166s）背景乐 -25dB 干扰、字级 score 低于全片中位、错字率 8%（两个 ASR 版本分歧大）。假设：WhisperX 吃人声分离后的干净音轨，字级置信度上升、错字率下降 → difflib 融合相似度上升 → 槽位边界更准。

### 借鉴 ②：多 TTS 引擎备胎接入模式（来自 Linly-Dubbing 架构）

Linly-Dubbing 的 TTS 层是插件式（Edge TTS / XTTS / CosyVoice / GPT-SoVITS 可切换）。我们 IndexTTS-2.5 已在 PC 验证过，备胎按 YAGNI 暂缓——IndexTTS 哪天翻车再接。

## 改造设计（最小侵入）

```
L0 音频底座: tangbohu_16k.wav
    ↓ [新增] Demucs 分离 → vocals.wav（只对白轨，bgm 弃用）
L1 字级对齐: PC WhisperX 跑 vocals.wav → align_dump_v2.json
    ↓ 对比旧 align_dump.json（原始混音版）
L2 短语聚合: l2v4_fusion.py 不改代码，只换输入 → slots_v7_demucs.json
    ↓ 四指标对比（槽数/字流覆盖/混战区粒度/中位置信）
决策: 置信度↑或错字↓ → v7 主线换 vocals 版；否则记录结论保持原版
```

关键设计决策：
- **Demucs 部署到 PC `D:\AI-tool\demucs`**（2026-08-31 用户拍板：项目工具统一 D:\AI-tool 新建目录，禁止散乱；3080 GPU 推理 181s 音频预计 <30s，口径含首跑模型加载/下载预热；与 WhisperX 同机闭环，分离→对齐免中间传输）
- **fusion 脚本另存 v2 不改原件**——l2v4_fusion.py 输入输出路径全硬编码（:10-13 读 dump、:100 读 wav、:132 写 slots），照搬「零改动」只会跑旧数据或覆盖基线；v2 脚本换 align_dump_v2 + 输出 slots_v7_demucs.json，基线产物不被覆盖。v7_probe_align.py 同理先核验可换入参
- 对比指标六件套（S2/S3 修正）：槽位数、**B 流总字数 + 绝对覆盖字数**（覆盖率分母陷阱：Demucs 吞字使 B 变短→覆盖率虚升假阳性）、混战区（119-166s）槽粒度、对齐 score 中位、**混战区保留字数 guard**（A1：重叠人声被当伴奏吞掉恰伤目标区）、**difflib 融合相似度**（A2：因果链中介变量，脚本现成打印 :35）
- **决策规则定死**（S3）：六指标逐一报告方向+幅度，切换主线需「score 中位 ≥+0.01 且 B 流字数不缩 >3% 且混战区保留字数不降」三条同时成立；错字率测法=对穿肠唱词公开文本做参照，听感抽查**优先混战区**
- 听感维度（用户拍板）：混战区抽查要区分谁说/何时说/间隔，不止听「有没有字」
- gap/能量标注口径（A4）：v2 脚本从 vocals.wav 重算（混战区 type 分类跨版可比）

## 任务分解（Phase 2 plan 蓝本）

1. PC `D:\AI-tool\demucs` 新建目录部署（venv + 清华镜像装包 + HF_ENDPOINT=hf-mirror.com 下 htdemucs 模型，禁止装 C 盘）
2. tangbohu_16k.wav 传 PC → 分离 vocals.wav（GPU），听感抽查
3. PC D:\AI-tool\whisperx 重跑 v7_probe_align.py（换输入 vocals.wav）→ align_dump_v2.json
4. dump 拉回本机，l2v4_fusion.py 跑双 dump 融合（transcribe_dump 不变 + align_dump_v2）
5. 四指标对比报告 + 更新接力手册 + commit

## 不做的事（YAGNI）

- 不整仓 clone Linly-Dubbing / VideoLingo
- 不接多 TTS 备胎（IndexTTS 够用，翻车再接）
- 不动 L3-L5（Demucs 结论出来后继续填词层）
