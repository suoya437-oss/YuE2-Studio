#!/usr/bin/env bash
# ============================================================
# YuE2 Studio 功能环境预装（新实例/换机后跑一次，免首次使用等待）
# 内容：SheetSage2 转录环境 + RVC 变声环境 + Seed-VC 变声环境
#       + Seed-VC 模型预下（防首次使用 CDN 卡死）+ demucs 人声分离模型预热
# 逻辑与 webui 首次使用时的自动安装完全一致，装完网页检查会直接跳过
# 幂等：重复执行安全，已装部分自动跳过
# 用法：bash /root/autodl-tmp/yue2-studio/bin/preinstall_envs.sh
# 预计耗时：15–30 分钟（约 10GB 下载，走腾讯源 + hf-mirror）
# ============================================================
set -uo pipefail

TENCENT="https://mirrors.cloud.tencent.com/pypi/simple"
BASE="${YUE2_BASE:-/root/autodl-tmp}"   # 通用化：非 AutoDL 平台 export YUE2_BASE=/your/path
REPO=$BASE/YuE
export HF_ENDPOINT="https://hf-mirror.com"
# 关键：pip 缓存/临时目录放数据盘，避免撑爆系统盘（30G 已被 conda+权重占满）
export PIP_CACHE_DIR=$BASE/pipcache
export TMPDIR=$BASE/tmp-build
mkdir -p "$PIP_CACHE_DIR" "$TMPDIR"

step(){ echo; echo "==== $* ===="; }

step "[0/6] seed-vc 仓库克隆（GitHub 走学术加速，失败自动直连重试）"
if [ ! -d "$BASE/seed-vc" ]; then
  source /etc/network_turbo || true
  git clone --depth 1 https://github.com/Plachtaa/seed-vc.git "$BASE/seed-vc" \
    || { unset http_proxy https_proxy; git clone --depth 1 https://github.com/Plachtaa/seed-vc.git "$BASE/seed-vc"; } \
    || echo "!! clone 两次均失败，Seed-VC 环境将不完整"
  unset http_proxy https_proxy || true
else
  echo "已存在，跳过"
fi

cd "$REPO"

step "[1/6] SheetSage2 转录环境（torch 2.8 + 模型约 4GB，最耗时）"
if [ ! -x .venv-sheetsage2/bin/python ]; then
  python3 -m venv .venv-sheetsage2 || {
    apt-get update -qq && apt-get install -y -qq python3.10-venv
    rm -rf .venv-sheetsage2 && python3 -m venv .venv-sheetsage2
  }
fi
SS2=.venv-sheetsage2/bin/python
"$SS2" -m pip install -q -U pip -i "$TENCENT"
"$SS2" -m pip install -q "huggingface-hub==0.36.0" -i "$TENCENT"
if [ ! -d models/SheetSage2 ] || [ -z "$(ls -A models/SheetSage2 2>/dev/null)" ]; then
  .venv-sheetsage2/bin/huggingface-cli download m-a-p/SheetSage2 --local-dir models/SheetSage2 \
    || echo "!! SheetSage2 模型下载失败"
fi
"$SS2" -c "import torch, torchaudio" 2>/dev/null \
  || "$SS2" -m pip install -q torch==2.8.0 torchaudio==2.8.0 -i "$TENCENT"
"$SS2" -c "import transformers" 2>/dev/null \
  || "$SS2" -m pip install -q -r models/SheetSage2/requirements.txt -i "$TENCENT"
"$SS2" -c "import torch, torchaudio, transformers; print('✓ SheetSage2 环境就绪')"

step "[2/6] RVC 变声环境（rvc-python + demucs）"
if [ ! -x .venv-rvc/bin/python ]; then /usr/bin/python3 -m venv .venv-rvc; fi
RVC=.venv-rvc/bin/python
# 注意：rvc-python 钦定 omegaconf==2.0.6，其旧式元数据会被 pip>=24.1 拒绝，
# 必须用旧版 pip 安装（报错原文：Please use pip<24.1）
"$RVC" -m pip install -q "pip<24.1" -i "$TENCENT"
"$RVC" -m pip install rvc-python demucs -i "$TENCENT" \
  || echo "!! rvc-python 安装失败，详见上方报错"
"$RVC" -m pip install -q "setuptools==80.9.0" -i "$TENCENT"  # pyworld 依赖 pkg_resources，≥81 的 setuptools 已将其移除
"$RVC" -c "import rvc_python, demucs; print('✓ RVC 环境就绪')"

step "[3/6] Seed-VC 变声环境（torch + 仓库 requirements）"
if [ ! -x .venv-seedvc/bin/python ]; then /usr/bin/python3 -m venv .venv-seedvc; fi
SVC=.venv-seedvc/bin/python
"$SVC" -m pip install -q -U pip -i "$TENCENT"
"$SVC" -m pip install -q "torch==2.4.0" "torchaudio==2.4.0" "torchvision==0.19.0" -i "$TENCENT"  # 按 requirements 钉的版本预装，避免先装最新再被降级、重复下载约 3GB
"$SVC" -m pip install -q demucs -i "$TENCENT"
if [ -f "$BASE/seed-vc/requirements.txt" ]; then
  "$SVC" -m pip install -q -r "$BASE/seed-vc/requirements.txt" -i "$TENCENT"
else
  echo "!! seed-vc 仓库缺失，requirements 未装"
fi
"$SVC" -m pip install -q "setuptools==80.9.0" -i "$TENCENT"  # funasr/modelscope 链路可能用到 pkg_resources，≥81 的 setuptools 已移除
"$SVC" -c "import demucs; print('✓ Seed-VC 环境就绪')"

step "[4/6] Seed-VC 模型预下（inference.py 用仓库内 ./checkpoints 独立缓存；CDN 偶发读停滞卡死，故超时+断点续传+重试）"
if [ -d "$BASE/seed-vc" ]; then
  cd "$BASE/seed-vc"
  svc_fetch() { # repo file —— 5 次重试，每次 7 分钟超时，hf_hub_download 自动续传
    local repo=$1 file=$2 try
    for try in 1 2 3 4 5; do
      echo "-- [尝试 $try/5] $repo :: $file"
      if timeout 420 "$REPO/.venv-seedvc/bin/python" - "$repo" "$file" <<'PYEOF'
import sys
from huggingface_hub import hf_hub_download
p = hf_hub_download(repo_id=sys.argv[1], filename=sys.argv[2], cache_dir="./checkpoints")
print("DOWNLOAD_OK", p)
PYEOF
      then
        return 0
      fi
      echo "   超时/中断（已下载部分自动保留续传），重试……"
    done
    echo "!! 最终失败: $repo :: $file（首次变声时会再自动尝试下载）"
    return 1
  }
  svc_fetch "Plachta/Seed-VC" "config_dit_mel_seed_uvit_whisper_base_f0_44k.yml"
  svc_fetch "Plachta/Seed-VC" "DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth"
  svc_fetch "lj1995/VoiceConversionWebUI" "rmvpe.pt"
  svc_fetch "funasr/campplus" "campplus_cn_common.bin"
  cd "$REPO"
else
  echo "!! seed-vc 仓库缺失，跳过模型预下"
fi

step "[5/6] 预热 demucs 人声分离模型（htdemucs 约 300MB，两个变声功能共用缓存）"
ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t 1 /tmp/_warm.wav -loglevel error
"$RVC" -m demucs --two-stems vocals -n htdemucs -o /tmp/_demucs_warm /tmp/_warm.wav >/dev/null 2>&1 \
  && echo "✓ htdemucs 已缓存" \
  || echo "!! 预热失败（不影响使用，首次变声时会自动下载）"

step "[6/6] 汇总"
du -sh .venv-sheetsage2 .venv-rvc .venv-seedvc models/SheetSage2 2>/dev/null
echo
echo "✅ 功能环境预装完成，网页三个功能（转录/RVC/Seed-VC 变声）首次使用免安装。"
