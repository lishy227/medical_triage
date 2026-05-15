"""
主入口 - 交互式CLI
"""
import os
import sys


# 添加父目录到路径，以便导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, Config
from triage import TriageEngine


def main() -> None:
    """主函数"""
    config: Config = load_config()
    if not config.api_key:
        print("错误: 未找到 API 密钥")
        print("\n请创建 .env 文件或设置环境变量:")
        print("  DASHSCOPE_API_KEY=your_api_key")
        sys.exit(1)
    
    engine: TriageEngine = TriageEngine(config)
    
    print(engine.get_welcome_message())
    
    while True:
        try:
            user_input: str = input("\n> ").strip()
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', '退出']:
                print("再见！")
                break
            
            if user_input.lower() in ['reset', '重启']:
                engine.reset()
                print(engine.get_welcome_message())
                continue
            
            response: str
            is_complete: bool
            response, is_complete = engine.process(user_input)
            print(f"\n{response}")
            
            if is_complete:
                print("\n导诊结束。输入 'reset' 重新开始，或 'quit' 退出。")
        
        except KeyboardInterrupt:
            print("\n再见！")
            break
        except Exception as e:
            print(f"发生错误: {e}")


if __name__ == "__main__":
    main()
