#!/usr/bin/env bash
# ============================================================
# YuE2 Studio 一键部署脚本
# 前提：≥24GB 显存 + BF16（Ampere+）的 NVIDIA GPU + Ubuntu（推荐 22.04）
# 用法：cd yue2-studio && bash bin/setup.sh
# 通用化（非 AutoDL 平台用环境变量覆盖，不用改任何文件）：
#   YUE2_BASE    工作区根路径（默认 /root/autodl-tmp，即 AutoDL 数据盘布局）
#   YUE2_PYGEN   生成用 Python 解释器（默认 /root/miniconda3/bin/python，缺失自动探测 python3）
# 幂等：重复执行安全，已装部分自动跳过
# ============================================================
set -euo pipefail

TENCENT="https://mirrors.cloud.tencent.com/pypi/simple"   # 国内实测最快；海外机器可换官方源
BASE="${YUE2_BASE:-/root/autodl-tmp}"
BASE_PY="${YUE2_PYGEN:-/root/miniconda3/bin/python}"
[ -x "${BASE_PY}" ] || BASE_PY="$(command -v python3 || command -v python)"
STUDIO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==== [0/6] 环境自检 ===="
command -v nvidia-smi >/dev/null || { echo "❌ 无 GPU"; exit 1; }
VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1)
CCAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | cut -d. -f1)
echo "显存 ${VRAM}MiB | 计算能力 ${CCAP}.x | 工作区 ${BASE}"
[ "${VRAM}" -ge 23000 ] || { echo "❌ 显存不足 24GB"; exit 1; }
[ "${CCAP}" -ge 8 ]     || { echo "❌ 不支持 BF16（需 Ampere+）"; exit 1; }

# AutoDL 学术加速（克隆 GitHub 用；其他平台无此文件，自动跳过）
[ -f /etc/network_turbo ] && source /etc/network_turbo || true

echo "==== [1/6] 工作区与仓库 ===="
mkdir -p "${BASE}"
cd "${BASE}"
[ -d YuE ] || git clone https://github.com/multimodal-art-projection/YuE.git
cd YuE

echo "==== [2/6] 生成环境：安装 YuE2（解释器: ${BASE_PY}） ===="
"${BASE_PY}" -m pip install . -i "${TENCENT}"
# 两个已知必修项（详见 docs/troubleshooting.md #4 #5）：
"${BASE_PY}" -m pip install "huggingface-hub>=0.34.0,<1.0" -i "${TENCENT}" || true
"${BASE_PY}" -m pip uninstall -y torchvision || true   # 坏的 torchvision 会连带炸掉 transformers 导入
"${BASE_PY}" -c "import torch, yue2; print('✓ 生成环境就绪 torch', torch.__version__)"

echo "==== [3/6] 网页环境：gradio（conda 可选） ===="
[ -f /root/miniconda3/etc/profile.d/conda.sh ] && source /root/miniconda3/etc/profile.d/conda.sh
if command -v conda >/dev/null 2>&1; then
  conda env list | grep -q "^yue2 " || conda create -y -n yue2 python=3.12
  conda activate yue2
  python -m pip install gradio -i "${TENCENT}"
  conda deactivate
else
  echo "!! 未检测到 conda：跳过此步。请在任意 Python 3.10+ 里 pip install gradio，"
  echo "   启动时用环境变量 YUE2_WEBUI_PY 指定该解释器即可"
fi

echo "==== [4/6] ffmpeg（flac 转 mp3） ===="
command -v ffmpeg >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq ffmpeg; }
ffmpeg -version | head -1

echo "==== [5/6] 预下载模型权重（约 15GB，走国内镜像） ===="
export HF_ENDPOINT="https://hf-mirror.com"   # 海外机器可去掉此行走官方源
"${BASE_PY}" - <<'PYEOF'
from huggingface_hub import snapshot_download
snapshot_download("m-a-p/YuE2-3B")
print("✓ YuE2-3B 权重就绪")
PYEOF

echo "==== [6/6] 部署网页工作台 ===="
cp -f "${STUDIO_DIR}/app/yue2_webui.py" "${BASE}/yue2_webui.py"
cp -f "${STUDIO_DIR}/app/rvc_convert.py" "${BASE}/rvc_convert.py"        # RVC 变声流水线（网页「声音克隆」调用）
cp -f "${STUDIO_DIR}/app/seedvc_convert.py" "${BASE}/seedvc_convert.py"  # Seed-VC 零样本变声流水线
mkdir -p "${BASE}/output_web"

# 可选冒烟测试（默认示例请求，2-10 分钟）：取消下行注释执行
# "${BASE_PY}" examples/generate.py --output "${BASE}/output_web/smoke_run"

cat <<TIP

✅ YuE2 Studio 部署完成！
   启动：  bash ${BASE}/yue2-studio/bin/start.sh
   访问：  AutoDL 控制台 → 自定义服务；其他平台直接 http://机器IP:6006
   翻唱：  首次转录会自动安装 SheetSage2 环境（约 15-30 分钟，含约 4GB 下载）
TIP
