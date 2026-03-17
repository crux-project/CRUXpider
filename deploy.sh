#!/bin/bash

# CRUXpider 部署脚本
# 使用方法: ./deploy.sh [development|production]

MODE=${1:-development}

echo "🕷️  CRUXpider 部署脚本"
echo "模式: $MODE"
echo "================================"

# 检查Python版本
echo "检查Python环境..."
python_version=$(python --version 2>&1)
echo "Python版本: $python_version"

# 检查并安装依赖
echo "检查依赖..."
if [ ! -f "requirements.txt" ]; then
    echo "❌ 未找到 requirements.txt"
    exit 1
fi

# 安装依赖
echo "安装Python依赖..."
pip install -r requirements.txt

# 检查配置文件
if [ ! -f "config.py" ]; then
    echo "⚠️  未找到 config.py，使用默认配置"
fi

# 创建日志目录
mkdir -p logs

# 根据模式启动应用
if [ "$MODE" = "production" ]; then
    echo "🚀 启动生产模式..."
    
    # 检查是否安装了gunicorn
    if ! command -v gunicorn &> /dev/null; then
        echo "安装 gunicorn..."
        pip install gunicorn
    fi
    
    # 启动生产服务器
    echo "在端口5003上启动生产服务器..."
    gunicorn --bind 0.0.0.0:5003 --workers 4 --timeout 120 wsgi:app
    
elif [ "$MODE" = "development" ]; then
    echo "🔧 启动开发模式..."
    python app_integrated.py
    
else
    echo "❌ 无效的模式: $MODE"
    echo "用法: ./deploy.sh [development|production]"
    exit 1
fi
