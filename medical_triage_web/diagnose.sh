#!/bin/bash
# 医疗导诊服务诊断脚本

echo "========== 医疗导诊服务诊断 =========="
echo ""

echo "1. 检查 PM2 日志..."
pm2 logs medical-triage --lines 50

echo ""
echo "2. 检查进程详情..."
pm2 describe medical-triage

echo ""
echo "3. 检查端口占用..."
netstat -tlnp | grep 5001 || ss -tlnp | grep 5001

echo ""
echo "4. 检查 Python 依赖..."
cd /opt/medical_triage
python3 -c "import flask" 2>/dev/null && echo "Flask: OK" || echo "Flask: 未安装"
python3 -c "import requests" 2>/dev/null && echo "Requests: OK" || echo "Requests: 未安装"

echo ""
echo "5. 直接测试启动..."
timeout 5 python3 web_server.py 2>&1 &
sleep 2
curl -s http://localhost:5001/api/welcome?session_id=test || echo "直接启动失败"
pkill -f web_server.py

echo ""
echo "========== 诊断完成 =========="
