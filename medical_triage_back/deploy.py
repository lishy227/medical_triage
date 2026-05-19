"""
生产环境部署脚本 - 使用 Uvicorn（ASGI 服务器）

Uvicorn 是 FastAPI 的推荐服务器，支持异步和多个 worker 进程。
Windows / Linux / Mac 全平台兼容。

使用方法:
    python deploy.py

或手动启动:
    uvicorn web_server:app --host 0.0.0.0 --port 5001 --workers 4
"""
import os
import sys


def main():
    """主函数 - 使用 Uvicorn 启动服务"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)

    try:
        import uvicorn
    except ImportError:
        print("错误: 未安装 uvicorn，请执行: pip install uvicorn[standard]")
        sys.exit(1)

    print("=" * 60)
    print("医疗导诊系统 - 生产环境部署")
    print("=" * 60)
    print("服务器: Uvicorn (ASGI)")
    print("框架:   FastAPI")
    print("监听地址: 0.0.0.0:5001")
    print("工作进程: 4")
    print("=" * 60)

    import socket
    try:
        hostname = socket.gethostname()
        ip_address = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
        print(f"服务器主机名: {hostname}")
        print(f"服务器 IP:    {ip_address}")
        print(f"API 文档:     http://{ip_address}:5001/docs")
        print("=" * 60)
    except Exception:
        pass

    print("启动服务中...")
    print("提示: 按 Ctrl+C 停止服务")
    print("=" * 60)

    uvicorn.run(
        'web_server:app',
        host='0.0.0.0',
        port=5001,
        workers=4,
        timeout_keep_alive=60,
        log_level='info',
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
