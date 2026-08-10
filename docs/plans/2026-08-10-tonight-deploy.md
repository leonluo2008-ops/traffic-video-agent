# 今晚执行计划：PC GPU 环境部署 + 管线验证

> 2026-08-10 创建 · 用户晚上回家开机后执行

## 背景

用户白天在办公室，无法操作 PC。晚 20:00+ 回家开机后执行本计划。

**目标**：在 PC（5070Ti 16GB）上部署 lip sync 推理环境，验证"给定视频+音频 → 重渲染口型"管线可跑通。

**架构**：
```
本机 (Linux 服务器)                    PC (Win11, 5070Ti)
  traffic-video-agent                     ComfyUI + LatentSync/MuseTalk
       │                                        │
       │  ① A2A（部署阶段）                      │
       ├────────────────────────────────────────→│  a2a_call → 装/配/测
       │                                        │
       │  ② ComfyUI HTTP API（运行阶段）         │
       ├────────────────────────────────────────→│  POST /prompt → poll → download
       │                                        │
       │  ③ Tailscale 100.109.238.27:8188        │
       └────────────────────────────────────────→│  ComfyUI 默认端口 8188
```

## 前置确认（开机后第一件事）

用户需要确认：

1. **哪台 PC 是 5070Ti 那台？**
   Tailscale 上的候选：
   - `pc-luo-1`（100.109.238.27）— 12h 前在线
   - `zenbook-luo`（100.85.145.22）— 当前在线
   - `pc-luo`（100.64.99.8）— 234天没上线

2. **那台 PC 上 Hermes 装好了吗？A2A 配通了吗？**
   - 如果没装 Hermes → 走远程桌面/SSH 手动部署，不走 A2A
   - 如果装了 Hermes 但 A2A 没配 → 先配 A2A 再部署
   - 如果 A2A 已配通 → 直接 a2a_call 开始部署

3. **ComfyUI 是否已在运行？端口是 8188 吗？**

4. **Tailscale 确认连通**：本机 ping PC 的 Tailscale IP

## Step 1: 环境探测（~5min）

```bash
# 本机操作：确认 Tailscale 连通
tailscale ping <PC_TAILSCALE_IP>

# 如果 PC 上 Hermes A2A 已配通：
# 通过 a2a_call 探测 PC 环境
a2a_call(agent="pc", message="运行以下命令并返回结果：nvidia-smi, python --version, pip list | findstr comfy")
```

探测目标：
- GPU 型号和显存确认（nvidia-smi）
- Python 版本
- ComfyUI 是否已装、版本、端口
- PyTorch + CUDA 版本
- 磁盘剩余空间（模型文件较大）

## Step 2: 安装 ComfyUI Lip Sync 节点（~15min）

### 方案：ComfyUI + LatentSync 自定义节点

**推荐节点**：
- LatentSync: `https://github.com/bytedance/LatentSync` 官方仓库
- 或 ComfyUI 封装版（如果社区有）
- ComfyUI_wav2lip（备选/对比用）: `https://github.com/ShmuelRonen/ComfyUI_wav2lip`

**部署命令**（通过 A2A 或远程操作 PC 执行）：

```bash
# 1. 进入 ComfyUI custom_nodes 目录
cd <ComfyUI路径>/custom_nodes

# 2. 克隆 LatentSync
git clone https://gh-proxy.com/https://github.com/bytedance/LatentSync.git

# 3. 安装依赖
cd LatentSync
pip install -r requirements.txt

# 4. 下载模型权重
# latentsync_unet.pt（~1.5GB）和 whisper tiny.pt（~75MB）
# 从 HuggingFace 下载：https://huggingface.co/ByteDance/LatentSync
# 国内用 hf-mirror.com 镜像
set HF_ENDPOINT=https://hf-mirror.com
python -c "from huggingface_hub import snapshot_download; snapshot_download('ByteDance/LatentSync', local_dir='./checkpoints')"

# 5. 重启 ComfyUI
```

**备选：MuseTalk**（如果 LatentSync 装不上或 VRAM 不够 1.6）

```bash
cd <ComfyUI路径>/custom_nodes
git clone https://gh-proxy.com/https://github.com/TMElyralab/MuseTalk.git
cd MuseTalk
pip install -r requirements.txt
# 下载模型权重
```

## Step 3: ComfyUI HTTP API 调用验证（~10min）

ComfyUI 跑起来后，从本机通过 HTTP API 提交工作流：

```python
# 本机测试代码
import requests
import json
import time
import urllib.parse

COMFYUI_URL = "http://100.109.238.27:8188"  # PC 的 Tailscale IP

# 1. 提交工作流
workflow = {
    # LatentSync workflow JSON
    # 需要从 ComfyUI 界面导出 API 格式的 workflow
    # 先手动在 ComfyUI 界面跑一次，导出 API JSON
}

response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
prompt_id = response.json()["prompt_id"]

# 2. 轮询结果
while True:
    history = requests.get(f"{COMFYUI_URL}/history/{prompt_id}").json()
    if prompt_id in history:
        break
    time.sleep(2)

# 3. 下载结果
output_data = history[prompt_id]["outputs"]
# 从 /view 端点下载输出文件
```

**验证标准**：
- 给一个 10 秒测试视频 + 10 秒测试音频
- ComfyUI API 提交 → 处理 → 返回结果视频
- 结果视频中人物口型已改变
- 处理时间 < 60 秒（10 秒视频）

## Step 4: 记录结果 + 更新设计文档

部署完成后：
1. 记录实际 VRAM 占用、处理速度、输出质量
2. 截取效果对比（原视频 vs lip sync 后）
3. 更新 `docs/plans/2026-08-10-design.md` 中的技术选型表
4. 确认最终技术路线（LatentSync 1.5 vs MuseTalk）

## 风险与降级

| 风险 | 降级方案 |
|---|---|
| LatentSync 1.6 需要 18GB VRAM | 用 1.5 版本（8GB 即可） |
| PC 上 Hermes 没装/A2A 没配 | 用户远程桌面手动操作，不走 A2A |
| ComfyUI 无 LatentSync 节点 | 用 ComfyUI_wav2lip（更成熟）或直接跑 LatentSync CLI |
| Tailscale 连接不稳定 | 用局域网 IP 直连（如果同一网络） |
| 模型下载慢（HuggingFace 被墙） | 用 hf-mirror.com 镜像或 ModelScope |

## 今晚执行 Checklist

- [ ] PC 开机，Tailscale 上线
- [ ] 确认 5070Ti 那台的 Tailscale IP
- [ ] 确认 PC 上 Hermes + A2A 状态
- [ ] Tailscale ping 连通测试
- [ ] ComfyUI 环境探测（GPU/Python/PyTorch）
- [ ] 安装 LatentSync 节点 + 模型权重
- [ ] ComfyUI 重启确认节点加载
- [ ] HTTP API 提交测试工作流
- [ ] 验证 lip sync 输出效果
- [ ] 记录 VRAM/速度/质量数据
- [ ] 更新设计文档

## 关键信息速查

| 项 | 值 |
|---|---|
| PC Tailscale IP | 待确认（候选 100.109.238.27 / 100.85.145.22） |
| ComfyUI 端口 | 8188（默认） |
| ComfyUI HTTP API | POST /prompt, GET /history/{id}, GET /view |
| LatentSync GitHub | https://github.com/bytedance/LatentSync |
| LatentSync HF 权重 | https://huggingface.co/ByteDance/LatentSync |
| HF 国内镜像 | https://hf-mirror.com |
| MuseTalk GitHub | https://github.com/TMElyralab/MuseTalk |
| GitHub 镜像 | https://gh-proxy.com/ |
| 本机 Tailscale IP | 100.126.167.88 (luo-surface-pro) |
