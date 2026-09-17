#!/usr/bin/env bash
# YuE2 Studio 日常启动（每次开机后执行）
# 用法：bash /root/autodl-tmp/yue2-studio/bin/start.sh
set -euo pipefail

cd /root/autodl-tmp

# 数据盘是新的（换实例/释放过）→ 引导重新部署
if [ ! -d YuE ]; then
    echo "❌ 仓库不存在（数据盘是新的）。请先上传本项目并执行："
    echo "   cd /root/autodl-tmp/yue2-studio && bash bin/setup.sh"
    exit 1
fi
if [ ! -f yue2_webui.py ]; then
    cp -f /root/autodl-tmp/yue2-studio/app/yue2_webui.py yue2_webui.py 2>/dev/null \
        || { echo "❌ 缺少 yue2_webui.py，请上传本项目"; exit 1; }
fi

mkdir -p output_web
echo "启动 YuE2 Studio 网页工作台（Ctrl+C 停止）……"
echo "启动后：AutoDL 控制台 → 自定义服务 打开网页"
exec /root/miniconda3/envs/yue2/bin/python -u /root/autodl-tmp/yue2_webui.py
