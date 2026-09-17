#!/usr/bin/env bash
# YuE2 Studio 日常启动（每次开机后执行）
# 用法：bash bin/start.sh
# 通用化（非 AutoDL 平台用环境变量覆盖，不用改任何文件）：
#   YUE2_BASE      工作区根路径（默认 /root/autodl-tmp）
#   YUE2_WEBUI_PY  网页解释器（默认 conda yue2 环境，缺失自动探测 python3）
set -euo pipefail

BASE="${YUE2_BASE:-/root/autodl-tmp}"
WEBUI_PY="${YUE2_WEBUI_PY:-/root/miniconda3/envs/yue2/bin/python}"
[ -x "${WEBUI_PY}" ] || WEBUI_PY="$(command -v python3 || command -v python)"
cd "${BASE}"

# 工作区是新的（换机器/换盘）→ 引导重新部署
if [ ! -d YuE ]; then
    echo "❌ 仓库不存在（工作区是新的）。请先上传本项目并执行："
    echo "   cd ${BASE}/yue2-studio && bash bin/setup.sh"
    exit 1
fi
if [ ! -f yue2_webui.py ]; then
    cp -f "${BASE}/yue2-studio/app/yue2_webui.py" yue2_webui.py 2>/dev/null \
        || { echo "❌ 缺少 yue2_webui.py，请上传本项目"; exit 1; }
fi

mkdir -p output_web
echo "启动 YuE2 Studio 网页工作台（Ctrl+C 停止）……"
echo "启动后：AutoDL 控制台 → 自定义服务；其他平台 http://机器IP:6006"
exec "${WEBUI_PY}" -u "${BASE}/yue2_webui.py"
