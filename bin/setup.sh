#!/usr/bin/env bash
# ============================================================
# YuE2 Studio 一键部署脚本（AutoDL 全新实例）
# 前提：RTX 4090 级（≥24GB 显存、BF16）+ PyTorch 2.x + CUDA 12.x 镜像
# 用法：cd /root/autodl-tmp/yue2-studio && bash bin/setup.sh
# 幂等：重复执行安全，已装部分自动跳过
# ============================================================
set -euo pipefail

TENCENT="https://mirrors.cloud.tencent.com/pypi/simple"   # 实测最快；清华/阿里在部分时段拥堵
BASE_PY="/root/miniconda3/bin/python"                      # base 环境：生成用（依赖最全）
STUDIO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==== [0/6] 环境自检 ===="
command -v nvidia-smi >/dev/null || { echo "❌ 无 GPU"; exit 1; }
VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1)
CCAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | cut -d. -f1)
echo "显存 ${VRAM}MiB | 计算能力 ${CCAP}.x"
[ "${VRAM}" -ge 23000 ] || { echo "❌ 显存不足 24GB"; exit 1; }
[ "${CCAP}" -ge 8 ]     || { echo "❌ 不支持 BF16（需 Ampere+）"; exit 1; }

# AutoDL 学术加速（克隆 GitHub 用；对国内镜像无效但不冲突）
[ -f /etc/network_turbo ] && source /etc/network_turbo || true

echo "==== [1/6] 数据盘与仓库 ===="
mkdir -p /root/autodl-tmp
cd /root/autodl-tmp
[ -d YuE ] || git clone https://github.com/multimodal-art-projection/YuE.git
cd YuE

echo "==== [2/6] base 环境：安装 YuE2（生成解释器） ===="
"${BASE_PY}" -m pip install . -i "${TENCENT}"
# 两个已知必修项（详见 docs/troubleshooting.md #4 #5）：
"${BASE_PY}" -m pip install "huggingface-hub>=0.34.0,<1.0" -i "${TENCENT}" || true
"${BASE_PY}" -m pip uninstall -y torchvision || true   # 坏的 torchvision 会连带炸掉 transformers 导入
"${BASE_PY}" -c "import torch, yue2; print('✓ base 环境就绪 torch', torch.__version__)"

echo "==== [3/6] yue2 环境：gradio（网页解释器） ===="
source /root/miniconda3/etc/profile.d/conda.sh
conda env list | grep -q "^yue2 " || conda create -y -n yue2 python=3.12
conda activate yue2
python -m pip install gradio -i "${TENCENT}"
conda deactivate

echo "==== [4/6] ffmpeg（flac 转 mp3） ===="
command -v ffmpeg >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq ffmpeg; }
ffmpeg -version | head -1

echo "==== [5/6] 预下载模型权重（约 15GB，走国内镜像） ===="
export HF_ENDPOINT="https://hf-mirror.com"
"${BASE_PY}" - <<'PYEOF'
from huggingface_hub import snapshot_download
snapshot_download("m-a-p/YuE2-3B")
print("✓ YuE2-3B 权重就绪")
PYEOF

echo "==== [6/6] 部署网页工作台 ===="
cp -f "${STUDIO_DIR}/app/yue2_webui.py" /root/autodl-tmp/yue2_webui.py
cp -f "${STUDIO_DIR}/app/rvc_convert.py" /root/autodl-tmp/rvc_convert.py        # RVC 变声流水线（网页「声音克隆」调用）
cp -f "${STUDIO_DIR}/app/seedvc_convert.py" /root/autodl-tmp/seedvc_convert.py  # Seed-VC 零样本变声流水线
mkdir -p /root/autodl-tmp/output_web

# 可选冒烟测试（默认示例请求，2-10 分钟）：取消下行注释执行
# "${BASE_PY}" examples/generate.py --output /root/autodl-tmp/output_web/smoke_$(date +%s)

cat <<'TIP'

✅ YuE2 Studio 部署完成！
   启动：  bash /root/autodl-tmp/yue2-studio/bin/start.sh
   访问：  AutoDL 控制台 → 自定义服务
   翻唱：  首次转录会自动安装 SheetSage2 环境（约 15-30 分钟，含约 4GB 下载）
TIP
