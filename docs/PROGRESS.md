# traffic-video-agent — 项目进度跟踪

> 更新：2026-08-16 · 技术路线推倒重来
> ⚠️ 旧技术路线（LatentSync 口型重渲染 / ComfyUI 部署）**已废弃删除**（git 历史有备份）。
> 当前唯一有效：2026-08-16 用户澄清的需求 + 技术栈。见 `docs/plans/2026-08-16-requirements.md`。

## 项目定位

引流传单号矩阵业务——批量生成 2-10 分钟无出镜竖屏短视频（上下分屏：上屏影视素材做梗 + 下屏操作录屏讲解），产能提升 10-100 倍。

## 核心思路（已确认）

**保留影视素材原画面（口型不动），只替换音频。**

```
影视素材片段 → 提取角色音频 → indexTTS 克隆角色音色
    → 输入目标文稿 → 生成匹配原片段节奏情绪的新音频
    → 替换原音频（画面口型不变，但"说"的是我们的内容）
```

**关键区别**：不需要 GPU 重渲染视频口型，只是音频合成替换，轻量得多。

## 完整工作流（以文稿时间线为主轴）

```
Stage 1: 素材检索 + 目标文稿生成
  ├─ 从海量素材找匹配目标文稿的片段（卡点1）
  └─ 把课程文稿改写成匹配素材音频的目标文稿（卡点2）
Stage 2: indexTTS 音频生成（克隆角色音色 → 生成匹配音频 → 替换原音频）
Stage 3: 人工按文稿时间轴录制下半段操作视频
Stage 4: AI 按"目标文稿时间轴 + 音频时间轴"对录屏初检
```

## 技术栈（本轮确认，分层组合）

| 层 | 职责 | 技术 | 边界 |
|---|---|---|---|
| ① 素材层 | 存/找/管影视素材 | **Eagle**（PC 库） | ✅定位文件/打标签/AI语义搜索；❌不懂视频内容 |
| ② 预检层 | 视频内容理解：谁在说话/情绪/切片段/抽音频 | **ComfyUI**（本地批量分析）+ **Gemini 3.5 Flash**（云端细看） | ComfyUI 重算力本地批量；Gemini 语义理解准 |
| ③ 改写层 | 课程文稿→角色口吻台词+时长节奏匹配 | **LLM**（DeepSeek/GLM） | ✅角色扮演改写；❌生成不了音频 |
| ④ 音频层 | 克隆角色音色→生成匹配音频→替换 | **indexTTS 2.5** | ✅零样本音色克隆+时长/情感控制；❌不懂画面 |
| ⑤ 录制层 | 人工按文稿时间轴录下半段 | 人工 | — |
| ⑥ 对齐层 | 初检：录屏 vs 文稿/音频时间轴 | **LLM + ffmpeg** | ✅检查对齐、冗余 |
| ⑦ 交付 | 打包给剪辑师 | 脚本 | — |

## 两大核心卡点（用户明确）

1. **卡点1 素材检索**：从海量影视素材快速找匹配目标文稿的片段
2. **卡点2 文稿改写**：把课程文稿转成"和素材音频相匹配"的音频文稿（长度/节奏/情绪贴合原片段）

## 待澄清/拍板（Brainstorm 进行中）

- [ ] 素材预检触发方式：全库一键预检索引 vs 每次按需预检
- [ ] ComfyUI 交互方式：用户要可视化界面+进度+失败可定位（吸取上次教训）
- [ ] 素材检索匹配标准（主题/情绪/角色/时长）
- [ ] 目标文稿改写程度（保持原意 vs 彻底角色口吻）
- [ ] 上下屏最终合成方式（合成一个 vs 分开交付）

## 当前阶段

**Phase 1: Brainstorming**（powerflow 流程）。需求已梳理，技术栈分层已确认，待拍板剩余问题后进入 Plan。

## indexTTS-2.5 PC 部署状态（2026-08-16）

**部署方式**：SSH 代部署环境（用户定），模型/辅助模型由助手经 ModelScope/hf-mirror 下载。

**已完成**：
- 节点 `ComfyUI-Index-TTS` 克隆到 `custom_nodes/`，ComfyUI 重启后 13 个 IndexTTS 节点全部加载
- 主模型 `IndexTTS-2.5` 8/8 文件齐全（config/feat1/feat2/gpt.pth/codec.pth/s2mel.pth/wav2vec2bert_stats/tiktoken）
- w2v-bert-2.0 语音特征模型完整（580M 参数，Wav2Vec2BertModel 加载 OK）
- BigVGAN 声码器 config.json 已补全（ModelScope 无此仓库，需从 hf-mirror 手动补）
- 推理依赖全部装齐（wetext 替代 pynini，audiotools 训练用跳过）

**踩坑记录（关键！）**：
1. requirements.txt 中文注释 → GBK UnicodeDecodeError，用 `-X utf8` 解决
2. descript-audiotools GitHub clone 受 PYTHONUTF8 影响失败 → 训练用跳过
3. pynini Windows 无 pip 源 → front.py 优先 wetext，免装
4. **w2v-bert-2.0 需整仓**（model.safetensors 2.3G + conformer_shaw.pt 1.1G），ModelScope 下载可能卡文件锁 → 用 hf-mirror 手动 curl 补
5. **BigVGAN 不在 ModelScope**（404）→ 必须从 hf-mirror 手动下 config.json + bigvgan_generator.pt
6. scp 传 PC 中文路径 → 用正斜杠 `C:/Users/...`
7. 模型目录 `ComfyUI/models/IndexTTS-2.5/`（带点5）

**待用户操作**：~~ComfyUI 上跑测试工作流，报错找助手。~~（已跑通，见下）

**🚀 TTS 2.5 引擎实测通过（2026-08-16 14:10）**：
- 在 ComfyUI 上成功生成样音 `tts2_5_base_00001.flac`（0.31MB），PC 端 TTS 2.5 推理无问题
- 样音已拉取到本地 `ref/成片范例/tts2_5_验证样音.flac`

**关键踩坑补充（audiotools 是硬依赖！）**：
- 之前判断"audiotools 训练专用、推理不需要"**是错的**——IndexTTS-2.5 的 s2mel/DAC 模块（`dac/__init__.py` 顶层 `import audiotools`）硬依赖它
- PyPI 无此包，须从 GitHub 编译装：`pip install --proxy http://127.0.0.1:7897 "git+https://github.com/descriptinc/audiotools@0.7.4#egg=descript-audiotools"`（PC 代理 7897）
- 装完会重装 psutil 等依赖 → **正在运行的 ComfyUI 会崩，须重启**
- requirements.txt 里 `==0.7.2` 与 `git 0.7.4` 冲突会导致启动器崩溃 → 已注释 `==0.7.2` 行

## Git 状态

- 分支 main，与 origin/main 一致
- 旧技术路线文档已删，待 commit
- 未跟踪：docs/PROGRESS.md、docs/plans/2026-08-16-requirements.md、test-assets/

---

# 2026-08-16 下午~晚上：编排方法论定型 + v4 全流程跑通（阶段性存档点）

## 阶段成果总览

**A 方向方法论已完整定型并实测跑通**：识别 → 编排（智能决策）→ TTS → 裁切 → 打包，全链路在"大话西游 + SP鱼鳞焊"测试用例上验证。本阶段核心产出为四条编排铁律 + 机器字数校验闭环 + 零重叠裁切规则。

## ① 编排 Agent 四大铁律（需求文档固化）

1. **角色分工禁自问自答**：谁讲解谁求教由原对话流动态决定，一来一回才是戏
2. **短片段必须编排禁剔除**：3-5 字短句承载"反应/追问"，是对话流动的关键
3. **从整个剧情编排知识点**：先理清完整对话流，再嵌入知识点
4. **配角台词分类启发**：纯情绪反应短句 → 保留原声不 TTS（音色零风险）；剧情衔接台词（含剧情专属名词）→ 攍写课程语境；判断标准=是否依赖剧情专属名词

## ② 字数约束闭环（≤2 字 + 机器校验）

- 定标：改写段 |目标字数 − 原字数| ≤ 2（口型对齐的本质）
- `scripts/count_chars.py`：解析编排稿 → 机器计字（剔标点）→ 校验 → 产出 `docs/verification/编排稿元数据.json`
- 流程固化：编排产出后必跑脚本，不 PASS 打回重写；**禁模型自数字数**（实证 LLM 数错两次：A 段标 25 实为 23）
- LLM 数字数不可靠的教训：生成时大致贴近即可，精确校验交给确定性代码

## ③ 编排稿 v4（新流程完整重排，用户验收"比较 OK"）

- 分类决策表 + K1-K4 知识单元落位 + 对话流验证（A引入→B求教→C教K1→D续教K2K3→E疑虑→F带K4→G相助→H推脱→I追问→J应允）
- **改写 5 段**：A/B/C/D/F（至尊宝 4 + 紫霞 B，紫霞唯一 TTS 段）
- **原声保留 5 段**：E/G/H/I/J
- 字数差：A+1 / B+1 / C-1 / D+0 / F+0，全 PASS

## ④ TTS 生成 + 零重叠裁切（PC 实测）

**IndexTTS 2.5 生成 5/5 成功**（`scripts/run_v4_generate.py`）：
- 参考音频：重裁 A-F 段（纯人声母带 `dahua_master_vocals.wav`，±0.3s）——用户已删旧参考目录，重裁即恢复
- 参数沿用 Base 节点已验证组合（temperature 0.8 / top_p 0.8 / top_k 30 / num_beams 3 / rep 10.0 / seed 5000+idx）

**裁切规则 v2（零重叠，用户指出重叠问题后修正）**：
- 旧逻辑盲切 ±1.5s → B-J 连续对话链（间隙仅 1s）相邻段各重叠 2s，8 处重复
- 新规则：**相邻段间隙 ≥ 3s（2×冗余）→ 各自 ±1.5s；间隙 < 3s → 间隙中点平分（每段仍留 0.5s 缓冲）**；首末段照常外扩 1.5s
- 10 段视频 + 5 段原声音频全部重切，音视频切点对齐，零重叠验证通过
- 脚本：`scripts/recut_zero_overlap.py`（规则内嵌文档，通用非硬编码）

## ⑤ 交付物（PC `D:\AI-tool\组合包_大话西游测试_v4\`）

- 10 段原声视频（零重叠切点）+ TTS 音频 5 段（flac）+ 原声音频片段 5 段（wav）
- 使用法：TTS 段 = 原声视频（静音）+ TTS 音频；原声段 = 原声视频直接用
- 服务器镜像：`/tmp/v4_deliver/`（TTS flac 5 个）

## ⑥ 本阶段踩坑

1. **PC PowerShell 中文列出目录为空**（编码陷阱）→ Python 列目录
2. **scp 中文路径用正斜杠** `C:/Users/...`
3. **cmd 嵌套引号转义难** → 永远写 .py 上传执行，不内联
4. **飞书 DM 多附件易丢** → 逐条发或 lark-cli im+messages-send
5. **裁切冗余不能盲目 ±1.5s** → 必须先看相邻段间隙，<3s 平分（`recut_zero_overlap.py` 已固化规则）
6. **用户已删 ComfyUI input 参考音频目录**——参考音频是易失资源，从母带重裁脚本在 run_v4_generate.py ①部分

## Git 存档点

- main 分支 tag `v0.4-编排方法论定型`（2026-08-16）
- 新分支 `redesign-flow`：整体流程重新梳理（用户 2026-08-16 指示）
- ref/（513M 素材）与 test-assets/（47M）不进 git（.gitignore）
