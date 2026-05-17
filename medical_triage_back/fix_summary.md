# 阿里云服务器卡死问题修复总结

## 问题现象
- 服务器启动后卡在 `正在加载医学知识库: medical.json`
- 只加载了 1000 条记录后就没有响应
- 后续 API 请求（如 `/api/welcome`）无响应

## 根本原因
`medical.json` 文件太大，同步加载阻塞了 Flask 的主线程，导致服务器无法处理新的 HTTP 请求。

## 修复内容

### 1. 异步加载医学知识库 (web_server.py)
- 将 `medical.json` 的加载改为**后台线程异步加载**
- 主线程启动后立即开始监听 HTTP 请求
- 知识库加载完成前，会员详细建议功能返回友好提示

### 2. 启用多线程模式 (web_server.py)
- `app.run()` 添加 `threaded=True` 参数
- 关闭 debug 模式 (`debug=False`)，避免性能损耗

### 3. 添加 LLM 调用超时 (agents/base_agent.py)
- `_call_llm()` 方法添加 `timeout=30.0` 参数
- 防止 API 请求无限期挂起

### 4. 创建生产环境部署脚本 (deploy.py)
- 使用 Gunicorn 替代 Flask 开发服务器
- 4 个 worker 进程处理并发请求
- 自动重启机制防止内存泄漏

## 部署步骤

### 方式一：快速测试（修复后的开发模式）
```bash
cd /opt/medical_triage/medical_triage_back
python web_server.py
```

### 方式二：生产环境（推荐）
```bash
cd /opt/medical_triage/medical_triage_back
pip install gunicorn
python deploy.py
```

或者直接用 gunicorn：
```bash
gunicorn -w 4 -b 0.0.0.0:5001 --timeout 60 --keep-alive 5 web_server:app
```

## 验证修复

1. 启动服务器后，应该立即看到：
   ```
   正在后台加载医学知识库: /opt/medical_triage/medical_triage_back/knowledge_base/medical.json
   ```

2. HTTP 请求应该立即响应，不再卡住

3. 知识库加载完成后会显示：
   ```
   医学知识库加载完成，共 XXXX 条记录
   ```

## 其他优化建议

1. **使用 Nginx 反向代理**：
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:5001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

2. **使用 Supervisor 管理进程**：
   ```ini
   [program:medical_triage]
   command=/opt/medical_triage/venv/bin/gunicorn -w 4 -b 0.0.0.0:5001 web_server:app
   directory=/opt/medical_triage/medical_triage_back
   user=www-data
   autostart=true
   autorestart=true
   ```

3. **监控服务器资源**：
   ```bash
   # 查看内存使用
   free -h
   
   # 查看进程
   ps aux | grep python
   
   # 查看日志
   tail -f /var/log/medical_triage.log
   ```
