# 🎵 YuE2 Studio —— 云端 AI 音乐工作站

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![UI](https://img.shields.io/badge/UI-Gradio-orange.svg)
![GPU](https://img.shields.io/badge/GPU-24GB%2B%20VRAM-red.svg)
![Model](https://img.shields.io/badge/model-YuE2--3B-informational)

> **English** — A cloud AI music workstation built on YuE2: form-based songwriting, melody-locked
> song covers, ABC score editing, and dual-mode voice conversion (RVC / Seed-VC). Deploy with one
> script on any 24 GB GPU (tested on AutoDL RTX 4090). Docs are in Chinese; feel free to open an issue.

基于开源模型 [YuE2](https://github.com/multimodal-art-projection/YuE) 的云端音乐生成工作站：
**表单化写歌、翻唱任意歌曲、乐谱级编辑**，全部在浏览器完成。

## 功能一览

| 能力 | 说明 |
|------|------|
| 🎬 智能创作 | 填表单（语言/人声/曲风/乐器/速度）+ 写歌词 → 出完整歌曲，附带可编辑的 ABC 乐谱 |
| 🎙️ 翻唱改编 | 上传任意歌曲 → SheetSage2 自动转谱 → 换风格/人声/歌词重唱 |
| 🎼 乐谱编辑 | 改 ABC 乐谱里的音符/和弦 → 重新渲染，精确打磨旋律 |
| ⚡ 快速直出 | 跳过乐谱规划，一键出 demo |
| 🎧 页内试听下载 | 音频 base64 内嵌页面，下载不经代理（AutoDL 代理传文件会断） |
| 📈 实时进度 | 生成/转录的时长、阶段、百分比、日志实时刷新 |

## 架构

```
浏览器 ── AutoDL「自定义服务」(6006端口) ──> Gradio 网页工作台 (yue2_webui.py, yue2 conda 环境)
                                              │
                                              ├── 生成: base 环境 python + YuE 仓库 examples/generate.py
                                              │        （--request 传 JSON 文件路径，--output 必须全新目录）
                                              ├── 转录: YuE/.venv-sheetsage2 独立环境 + SheetSage2
                                              └── 产物: output_web/时间戳/  (audio.flac → ffmpeg 转 mp3)
```

## 快速开始（AutoDL 全新实例）

1. 租一台 **RTX 4090 / 24GB**（镜像选 PyTorch 2.x + CUDA 12.x + Ubuntu 22.04）
2. 把本项目上传到服务器 `/root/autodl-tmp/yue2-studio/`
3. 执行部署（约 20–40 分钟，含 15GB 权重下载）：

   ```bash
   cd /root/autodl-tmp/yue2-studio && bash bin/setup.sh
   ```

4. 启动网页工作台：

   ```bash
   bash bin/start.sh
   ```

5. AutoDL 控制台点「自定义服务」打开网页，开写歌。

> ⚠️ AutoDL 的**数据盘不随镜像走**：换新实例后需要重新 clone 仓库并跑一次 `setup.sh`
>（脚本有缓存检测，已装过的部分会跳过）。

## 日常使用

- 开机 → `bash bin/start.sh` → 控制台点「自定义服务」
- 页面打不开 → 先去控制台**重新点一次**「自定义服务」（实例迁移后旧代理地址会失效）
- 用完 → 控制台**关机**（按量计费停止；数据盘保留）

## 文档

- [部署指南](docs/deploy-guide.md) —— 选卡、平台、流程详解
- [三种模式详解](docs/modes.md) —— 智能创作 / 翻唱改编 / 快速直出
- [踩坑实录](docs/troubleshooting.md) —— 17 个实际踩过的坑与修法（部署前必读）

## 硬件与成本

- 要求：NVIDIA GPU ≥ 24GB 显存、支持 BF16（3090/4090/L4/A10/A100）
- 参考：AutoDL 4090 约 ¥2/时；单曲生成 2–10 分钟

## 许可边界（重要）

- **本项目代码**：MIT License，可自由使用修改（见 [LICENSE](LICENSE)）；
- **本项目的部署脚本只负责引导下载模型**，模型权重（YuE2-3B、SheetSage2 等）版权归各自作者，
  其中 YuE2 权重为 **CC BY-NC 4.0：个人创作 OK，商用需另行向模型作者取得授权**；
- 请勿将下载的模型权重打包再分发。
