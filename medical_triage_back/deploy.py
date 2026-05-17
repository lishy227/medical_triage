"""
生产环境部署脚本 - 使用 Waitress（跨平台统一方案）

Waitress 是纯 Python 的 WSGI 服务器，支持 Windows、Linux、Mac 全平台，
无需额外依赖，性能满足生产环境需求。

使用方法:
    python deploy.py

或手动启动:
    waitress-serve --host=0.0.0.0 --port=5001 --threads=4 web_server:app
"""
import os
import sys
import subprocess


def check_waitress() -> bool:
    """检查是否安装了 waitress"""
    try:
        import waitress
        return True
    except ImportError:
        return False


def install_waitress() -> bool:
    """安装 waitress"""
    print("正在安装 waitress...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'waitress'],
                      check=True, capture_output=True)
        print("waitress 安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"安装 waitress 失败: {e}")
        return False


def main():
    """主函数 - 使用 Waitress 启动服务"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)
    
    # 检查并安装 waitress
    if not check_waitress():
        print("未检测到 waitress，正在安装...")
        if not install_waitress():
            print("错误: 无法安装 waitress，请手动安装: pip install waitress")
            sys.exit(1)
    
    print("=" * 60)
    print("医疗导诊系统 - 生产环境部署")
    print("=" * 60)
    print("服务器: Waitress (跨平台 WSGI 服务器)")
    print("监听地址: 0.0.0.0:5001")
    print("工作线程: 4")
    print("连接超时: 60秒")
    print("=" * 60)
    
    # 显示服务器 IP 地址，方便调试
    import socket
    try:
        hostname = socket.gethostname()
        ip_address = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
        print(f"服务器主机名: {hostname}")
        print(f"服务器 IP: {ip_address}")
        print("=" * 60)
    except:
        pass
    
    # 导入应用并启动
    from waitress import serve
    from web_server import app
    
    print("启动服务中...")
    print("提示: 按 Ctrl+C 停止服务")
    print("=" * 60)
    
    serve(
        app,
        host='0.0.0.0',
        port=5001,
        threads=4,              # 工作线程数
        channel_timeout=60,     # 连接超时（秒）
        cleanup_interval=30,    # 清理间隔（秒）
        ident='MedicalTriageServer/1.0'  # 服务器标识
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
