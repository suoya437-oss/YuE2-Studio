# YuE2 Studio —— 项目上下文（新会话必读）

云端 AI 音乐工作站：基于开源模型 YuE2（歌词→歌曲 + 翻唱），部署在 AutoDL 租赁的
RTX 4090 上，通过 Gradio 网页工作台操作。**已完整交付并日常使用中。**

> 本项目本地路径：`D:\yue2-studio`（代码在此改，改完 scp 到服务器）

## 服务器直连

SSH 私钥路径与当前实例的登录指令记录在本地私有文件 **`LOCAL-PRIVATE.md`**（已被
.gitignore 排除，**不随仓库发布**）。

- ⚠️ 实例迁移/换机后端口和地址会变：让用户从 AutoDL 控制台复制新的「SSH 登录指令」，
  并同步更新 `LOCAL-PRIVATE.md`
- 常用巡检：`ps aux | grep yue2_webui`（网页进程）、`ls /root/autodl-tmp/output_web/`（产物）

## 服务器上的关键路径

| 路径 | 作用 |
|------|------|
| `/root/autodl-tmp/yue2-studio/` | 本项目（setup.sh / start.sh / 文档） |
| `/root/autodl-tmp/yue2_webui.py` | 运行中的网页工作台（= 本项目 app/yue2_webui.py） |
| `/root/autodl-tmp/YuE/` | 官方模型仓库（生成引擎 + SheetSage2 转录） |
| `/root/autodl-tmp/output_web/` | 所有产物：每首歌/每次转录一个时间戳目录 |

## 三个解释器（勿混用！历史踩坑核心）+ 后两个独立 venv

| 解释器 | 用途 |
|--------|------|
| `/root/miniconda3/bin/python` | **生成**（base 环境，依赖最全：torch 2.10 + yue2） |
| `/root/miniconda3/envs/yue2/bin/python` | **网页**（只有 gradio） |
| `/root/autodl-tmp/YuE/.venv-sheetsage2/bin/python` | **转录**（SheetSage2 专用，torch 2.8） |
| `/root/autodl-tmp/YuE/.venv-rvc/bin/python` | **RVC 变声**（demucs + rvc-python，Python 3.10 venv，首次使用时网页自动安装） |
| `/root/autodl-tmp/YuE/.venv-seedvc/bin/python` | **零样本变声**（Seed-VC，仓库在 /root/autodl-tmp/seed-vc，模型缓存在 hf-seedvc/） |

`/root/autodl-tmp/rvc_convert.py` = RVC 变声流水线（.pth 模型）；
`/root/autodl-tmp/seedvc_convert.py` = 零样本变声流水线（参考音频即可，唱歌模式保旋律）。
均由网页「声音克隆」面板调用（双模式切换），也可 CLI 单独跑。

## 常用操作

```bash
# 重启网页（先杀旧进程）
pkill -f yue2_webui.py; nohup /root/miniconda3/envs/yue2/bin/python -u /root/autodl-tmp/yue2_webui.py > /root/autodl-tmp/webui_console.log 2>&1 &

# 手动生成（--request 传 JSON 文件路径；--output 必须是不存在的新目录）
/root/miniconda3/bin/python /root/autodl-tmp/YuE/examples/generate.py \
  --request <req.json> --cot full --output <新目录>

# 批量 flac 转 mp3
for f in /root/autodl-tmp/output_web/*/audio.flac; do ffmpeg -y -i "$f" -codec:a libmp3lame -q:a 2 "${f%.flac}.mp3"; done
```

## 改代码的流程

本地改 `app/yue2_webui.py` → scp 推到服务器 `/root/autodl-tmp/yue2_webui.py` →
`pkill` 旧进程并重启（注意：转录/生成进行中时先等它跑完，重启会丢后台任务跟踪）。

## 必读文档

- `docs/troubleshooting.md` —— 17 个实战坑与修法（改环境/装依赖前先查这里）
- `docs/modes.md` —— 三种生成模式（full/melody/off）与风格串权重规则
- `docs/deploy-guide.md` —— 选卡、平台、部署与开关机流程

## 约定

- pip 一律用腾讯源 `https://mirrors.cloud.tencent.com/pypi/simple`
- HuggingFace 一律走镜像 `HF_ENDPOINT=https://hf-mirror.com`
- 模型权重许可 CC BY-NC 4.0（非商用）
- 用户偏好：中文沟通、界面表单化、少敲命令；改完要在服务器验证
