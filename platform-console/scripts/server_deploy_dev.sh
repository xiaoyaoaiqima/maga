#!/bin/bash
# 注意：此脚本在 1Panel 服务器端执行
# 路径请根据你的上传路径修改

# 遇到错误立即退出
set -e

# --- 配置区 ---
ENV="dev" # 对应任务环境：dev | prod
DOMAIN="dev-raap.sharpasshark.com" # 站点域名
# --------------

# 注意：此路径请根据你的实际上传路径修改
UPLOAD_FILE="/tmp/raap-admin-frontend/dist.zip"
SITE_PATH="/opt/1panel/www/sites/${DOMAIN}/index"

if [ -f "$UPLOAD_FILE" ]; then
    echo "--- 开始部署新版本 [${ENV}] ---"

    # 1. 确保安装了 unzip
    if ! command -v unzip &> /dev/null; then
        echo "正在安装 unzip..."
        apt-get update && apt-get install -y unzip
    fi

    # 2. 备份旧版本
    BACKUP_NAME="dist_backup_$(date +%Y%m%d_%H%M%S)"
    if [ -d "${SITE_PATH}/dist" ]; then
        echo "正在备份旧版本到 ${BACKUP_NAME}..."
        mv "${SITE_PATH}/dist" "${SITE_PATH}/${BACKUP_NAME}"
    fi

    # 3. 解压新版本到 SITE_PATH/dist 目录
    echo "正在解压新版本到 ${SITE_PATH}/dist ..."
    mkdir -p "${SITE_PATH}/dist"

    # 强制覆盖模式解压
    if ! unzip -o "$UPLOAD_FILE" -d "${SITE_PATH}/dist"; then
        echo "❌ 错误：解压失败"
        # 尝试回滚（如果存在备份）
        if [ -d "${SITE_PATH}/${BACKUP_NAME}" ]; then
            echo "尝试回滚到上个版本..."
            rm -rf "${SITE_PATH}/dist"
            mv "${SITE_PATH}/${BACKUP_NAME}" "${SITE_PATH}/dist"
        fi
        exit 1
    fi

    # 4. 清理上传的文件
    echo "清理临时文件..."
    rm -f "$UPLOAD_FILE"

    # 5. 清理超过 5 个的历史备份
    echo "清理冗余备份..."
    # 使用 find 配合 xargs 更安全
    cd "${SITE_PATH}"
    ls -dt dist_backup_* 2>/dev/null | tail -n +6 | xargs rm -rf || true

    echo "🎉 部署成功！"
else
    echo "❌ 错误：未找到上传的文件 $UPLOAD_FILE"
    # 确保目录存在，方便下次手动上传
    UPLOAD_DIR=$(dirname "$UPLOAD_FILE")
    mkdir -p "$UPLOAD_DIR"
    echo "已确保上传目录存在: $UPLOAD_DIR"
    exit 1
fi

