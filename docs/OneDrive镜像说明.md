# OneDrive 项目工作区镜像说明

> 2026-08-30 设立。本项目的完整工作现场（源码 + 测试素材 + 中间/结果产物）单向上云，
> 在其他电脑（PC / Zbook）打开 OneDrive 即可查看工作进展。

## 使用方式

| 你在哪 | 做什么 |
|---|---|
| PC / Zbook | 打开 `OneDrive → Hermes-Exchange → 项目工作区 → traffic-video-agent/` 浏览（只读） |
| PC / Zbook | 要给 surface 传素材/任务文件 → 放 `Hermes-Exchange → 交接-inbox → traffic-video-agent/` |
| surface（Agent） | 工作产物正常落盘项目目录，commit 或等 ≤30 分钟自动上云 |

## 机制

- **方向单向后镜像**：surface 为唯一事实源 → OneDrive。含删除语义（surface 端删了的文件，同步后 OneDrive 端也消失），保持"镜像 = 真实现场"。历史保留靠 Git 提交记录。
- **触发**：每次 `git commit` 后自动同步（post-commit 钩子）+ 每 30 分钟增量兜底（rclone 差异比对，只传变更文件）。
- **过滤**：`.git` / `.venv` / `node_modules` / `__pycache__` / 系统垃圾文件不上云；**测试素材和产物全部上云**（这正是本镜像与 Git 仓库的分工：Git 管轻量源码，OneDrive 存全量工作现场）。
- **脚本**：`~/.hermes/scripts/onedrive-mirror-projects.sh`（支持多项目，清单 `onedrive-mirror-projects.conf`）；日志 `~/.hermes/log/onedrive-mirror.log`。

## 注意

- 不要直接编辑 OneDrive 上的文件——下一次同步会被 surface 侧覆盖。
- 大视频文件首次上云较慢（受 OneDrive 上行带宽限制），之后只增量传变更。