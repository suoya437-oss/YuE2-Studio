# YuE2 Studio 部署指南

> 一键脚本见 `bin/setup.sh`，本文是它的展开说明与决策依据。

## 一、选卡（硬性要求）

| 要求 | 说明 | 合适 | 不合适 |
|------|------|------|--------|
| 显存 ≥ 24GB | BF16 推理硬门槛 | 3090 / **4090（性价比首选）** / L4 / A10 / A100 | T4 / V100 / 3060 |
| 架构 ≥ Ampere | BF16 支持（计算能力 8.0+） | 30/40 系、A/H 系 | 20 系及更早 |

## 二、选平台

| 平台 | 参考价 | 特点 |
|------|--------|------|
| **AutoDL（本项目主战场）** | 4090 约 ¥1.5–2.5/时 | 学术加速、按量计费、自定义服务代理 |
| 恒源云 / 仙宫云 | 与 AutoDL 接近 | 同类竞品 |
| RunPod / vast.ai | 4090 $0.4–0.8/时 | 海外、按秒计费 |
| 阿里云/腾讯云 | 明显更贵 | 企业生产环境 |

镜像选 **PyTorch 2.x + CUDA 12.x + Ubuntu 22.04**。

## 三、部署流程（对应 setup.sh 各步）

1. **[0] 自检**：显存 ≥23000MiB、计算能力 ≥8.0
2. **[1] 仓库**：clone 到 `/root/autodl-tmp`（数据盘，空间大）
3. **[2] base 环境**：`pip install .` + 两个必修项——
   - `huggingface-hub` 降到 `<1.0`（transformers 兼容）
   - **卸载 torchvision**（版本不匹配的它会连带炸 transformers 导入）
4. **[3] yue2 环境**：conda 建 python 3.12，只装 gradio（网页解释器）
5. **[4] ffmpeg**：apt 装（flac→mp3 转换用）
6. **[5] 权重**：`HF_ENDPOINT=https://hf-mirror.com` 预下载 YuE2-3B（约 15GB）
7. **[6] 部署**：复制 webui 脚本到 `/root/autodl-tmp/`

之后 `bash bin/start.sh` → 控制台「自定义服务」。

## 四、翻唱环境（SheetSage2，首次转录时自动安装）

网页首次点「转录」会自动：建独立 venv → 下载模型（133 文件）→ 装 torch 2.8 与依赖 → 转录。
全程约 15–30 分钟（约 4GB 下载，走腾讯源）。已知注意：
- Python 3.12 下需把 requirements 里的 `numpy==1.24.3` 换成 `1.26.4`（自动装流程已处理不了的，手动 sed，见踩坑实录 #17）
- 别重复点转录按钮（双进程抢 GPU）

## 五、日常开关机

| 场景 | 操作 |
|------|------|
| 开机 | `bash /root/autodl-tmp/yue2-studio/bin/start.sh` → 控制台点「自定义服务」 |
| 换新实例 | 重新上传本项目 + clone 仓库 + `bash bin/setup.sh`（数据盘不随镜像走） |
| 页面打不开 | 控制台**重新点**「自定义服务」；仍不行走 SSH 隧道 `-L 6006:localhost:6006` |
| 下歌 | 网页点下载链接（base64 内嵌，不走代理）；或 JupyterLab 右键 |
| 收工 | 控制台**关机**（停止计费，数据保留）；长期不用先下载歌曲再释放实例 |

## 六、成本参考

- 4090：约 ¥2/时；单曲 2–10 分钟；翻唱转录 1–2 分钟（环境就绪后）
- 充值 ¥50 ≈ 25 小时 ≈ 数百首歌
- 模型权重许可 CC BY-NC 4.0：**个人创作 OK，商用需另行授权**

## 七、通用部署（非 AutoDL 平台）

项目本质只依赖「≥24GB 显存 + BF16 的 NVIDIA GPU + Ubuntu」，AutoDL 是参考部署环境而非绑定。
所有 AutoDL 专属逻辑都有兜底：`/etc/network_turbo` 不存在自动跳过；conda 缺失时提示改用
任意 Python + `pip install gradio`；网页监听 `0.0.0.0:6006`，任何平台直接 `http://IP:6006` 访问。

**环境变量**（AutoDL 上不设任何变量，行为与原来完全一致）：

| 变量 | 作用 | 默认值（AutoDL 布局） |
|------|------|----------------------|
| `YUE2_BASE` | 工作区根路径（仓库/产物/变声脚本都放这） | `/root/autodl-tmp` |
| `YUE2_PYGEN` | 生成用解释器 | `/root/miniconda3/bin/python`（缺失自动探测 `python3`） |
| `YUE2_WEBUI_PY` | 网页解释器（需装 gradio） | conda `yue2` 环境（缺失自动探测 `python3`） |
| `YUE2_WEBUI_USER` / `YUE2_WEBUI_PASS` | 网页登录账号/密码（**两者都设置才启用鉴权**） | 不设置 = 无鉴权 |

> 🔐 **安全提醒**：AutoDL 的「自定义服务」地址是平台代理后的私有入口，无鉴权尚可接受；
> 但自有服务器把 6006 暴露到公网时，**务必**在启动前 `export YUE2_WEBUI_USER=admin
> YUE2_WEBUI_PASS=强密码`，否则任何知道 IP 的人都能白嫖你的 GPU。

**各平台要点**：

| 平台 | 要点 |
|------|------|
| 恒源云 / 仙宫云 | 与 AutoDL 同类，几乎零改造，`YUE2_BASE` 按其数据盘路径设一下即可 |
| RunPod / vast.ai | 海外直连快：腾讯源换官方 PyPI、删 `HF_ENDPOINT` 镜像；网页直接 `IP:6006` |
| 自有服务器 / 工作站（3090/4090） | 最通用形态：Ubuntu 22.04 + 驱动 + `YUE2_BASE=/your/path`；无租金、数据在手；注意 6006 端口防火墙放行 |

系统依赖（脚本会自动装，仅列明）：`git`、`ffmpeg`（apt）、`python3.10-venv`（变声/转录 venv 用），
因此**推荐 Debian/Ubuntu 系**；其他发行版需自行替换 apt 为对应包管理器。
