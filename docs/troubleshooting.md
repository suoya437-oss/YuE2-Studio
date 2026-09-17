# 踩坑实录 —— YuE2 云端部署 21 坑全记录

> 以下每一条都在真实部署中踩过并验证过修法。部署新环境前通读一遍，能省数小时。

## 环境类

### 1. AutoDL 镜像不含数据盘
`保存镜像` 只打包系统盘（/root 下除 autodl-tmp 外）。换新实例后 `/root/autodl-tmp` 是空的：仓库要重新 clone，网页脚本要重新上传。conda 环境、`~/.cache/huggingface` 模型缓存（约 15GB）在系统盘里、随镜像走。
**修**：新实例跑 `bin/setup.sh`（幂等），或克隆实例时保留数据盘。

### 2. pip 源慢/403 随机切换
清华源某时段 50kB/s；阿里源走代理时 403；官方源直连超时。
**修**：固定用腾讯源 `https://mirrors.cloud.tencent.com/pypi/simple`（实测稳定 10MB/s）。学术加速 `source /etc/network_turbo` 只对 GitHub/HF/官方 PyPI 有效，与国内镜像互斥。

### 3. conda + .venv + uv 三层环境互相打架
AutoDL 的 conda 环境里可能挂着 venv 激活钩子，`pip` 装进的位置和 `python` 运行的环境可能不是同一个，出现"装了但 import 不到"。
**修**：所有关键解释器用**绝对路径**：网页=`/root/miniconda3/envs/yue2/bin/python`，生成=`/root/miniconda3/bin/python`，转录=`YuE/.venv-sheetsage2/bin/python`。

### 4. huggingface-hub 1.x 与 transformers 冲突
报错 `huggingface-hub>=0.34.0,<1.0 is required ... found 1.31.0`。
**修**：`pip install "huggingface-hub>=0.34.0,<1.0"`。

### 5. 坏的 torchvision 连带炸 transformers
报错 `RuntimeError: operator torchvision::nms does not exist`（torchvision 与 torch 版本不匹配时导入即崩，transformers 可选导入它被连坐）。
**修**：`pip uninstall -y torchvision`（音频模型根本不需要它）。

### 6. numpy 被 yue2-infer 的自动升级器搞坏
`[yue2-infer] Upgrading numpy ... Permission denied` 后 `ModuleNotFoundError: No module named 'numpy'`（升级失败但已卸掉旧的）。
**修**：`chmod -R u+w .venv && chown -R root:root .venv`，然后 `force-reinstall "numpy>=2.2"`。

### 7. yue2 包找不到（src-layout）
仓库是 src 布局，包在 `src/yue2/`，不在根目录。
**修**：正常 `pip install .` 即可；若用 PYTHONPATH 必须指向 `仓库/src`。

## 生成类

### 8. `--request` 是 JSON 文件路径，不是文本
直接传描述文字会报 `FileNotFoundError`（它按 Path 读文件）。请求 JSON 结构：
```json
{"id": "song_name", "style": "Chinese lyrics, pop, piano, 90 BPM",
 "lyrics": "[Verse]\n...\n\n[Chorus]\n...", "cot": "full", "seed": 42}
```
**修**：把内容写成 `.json` 文件再传路径。`id` 必须文件名安全（英文/数字/`_`/`-`）。

### 9. `--output` 必须是不存在的新目录
复用旧目录直接报错退出：`Choose a fresh output directory`。
**修**：每次用时间戳目录；脚本只 mkdir 父目录。

### 10. 人声性别漂移（写"男声"出女声）
中文人声标签约束力弱 + 采样随机性。
**修**：英文标签放风格串**最前面**并二次强调：`deep male baritone vocals, ..., male voice`；满意后记种子复现。

### 11. 歌词长度决定歌曲时长
一段主歌+一段副歌 ≈ 1 分钟。要 3–4 分钟：V-C-V-C-Bridge-C 结构。段落标签用英文 `[Verse]/[Chorus]/[Bridge]`。

## 网页类（Gradio）

### 12. gradio 生成器处理函数崩溃（tqdm_class）
`AttributeError: 'XXProgressBar' object has no attribute 'tqdm_class'`（gradio 内部 iterate_with_progress_bar）。
**修**：处理函数改成普通函数（非生成器），用后台线程 + 定时刷新（gr.Timer）替代 yield。

### 13. 单输出组件收到元组
`Expected str, but the value was ('...',)`。
**修**：单输出返回裸字符串，别带元组括号/尾逗号。

### 14. 新旧版本参数差异
`demo.queue(default_concurrency_limit=...)` 老版本不认；`every=` 参数部分版本不支持。
**修**：try/except 分层降级（见 `app/yue2_webui.py` 尾部）。

### 15. AutoDL 代理传输音频文件必断
下载 1MB 的 mp3 都会导致「自定义服务」页面崩溃（进程不死，通道断）。
**修**：音频 base64 内嵌 HTML 组件（`<audio>` + `<a download>`），下载在浏览器本地完成；或走 JupyterLab 右键下载。

### 16. 页面打不开但服务正常
实例迁移后旧代理地址失效。
**修**：控制台**重新点一次**「自定义服务」；或 SSH 隧道 `-L 6006:localhost:6006` 走 `http://localhost:6006`。

## 转录类（SheetSage2 翻唱）

### 17. Python 3.12 与官方依赖不兼容
venv 建在 3.12 上时 `numpy==1.24.3` 无预编译包，源码编译崩（`pkgutil.ImpImporter`）。
**修**：`sed -i 's/numpy==1.24.3/numpy==1.26.4/' requirements.txt` 后重装。另外：SheetSage2 必须独立 venv（官方要求，与 YuE2 依赖互斥）；重复点击转录按钮会产生双进程抢 GPU，`ps aux | grep infer.py` 查杀旧的。

## 变声类（RVC / Seed-VC，2026-09 新实例迁移实测）

### 18. rvc-python 装不上：pip≥24.1 拒绝 omegaconf 2.0.6
报 `ResolutionImpossible`，rvc-python 所有版本依赖冲突。根因：它钦定 `omegaconf==2.0.6`，该包元数据写法（`PyYAML>=5.1.*`）不合新规范，pip 24.1 起直接拒装。
**修**：在该 venv 里先降级 pip 再装：`pip install "pip<24.1"` → `pip install rvc-python demucs`。

### 19. pyworld 报 No module named 'pkg_resources'
setuptools ≥81 已移除 pkg_resources，而 rvc-python 依赖的 pyworld 还在用。
**修**：`pip install setuptools==80.9.0`（RVC 与 Seed-VC 两个 venv 都要）。

### 20. 系统盘 30G 被 pip 缓存撑爆，venv 安装报 No space left on device
pip 缓存与临时目录默认在系统盘 `/root`（已压着 conda 9.3G + 权重缓存 9.7G）；装 torch 级别的大包必爆。
**修**：`/root/.config/pip/pip.conf` 写入 `[global]` + `cache-dir = /root/autodl-tmp/pipcache`（一劳永逸，含网页自动安装路径）；批量装时再设 `TMPDIR=/root/autodl-tmp/tmp-build`。清旧缓存 `rm -rf /root/.cache/pip`（实测清出 13G）。

### 21. scp 覆盖正在运行的 bash 脚本会当场炸
bash 边读边执行，运行中覆盖同名脚本会按旧偏移读新内容，报莫名语法错误。
**修**：等脚本跑完再推；或推成新文件名再 `mv` 原子替换。
