"""
配置管理模块 - 从.env文件和环境变量读取应用配置

功能：
- 从.env文件加载环境变量
- 从环境变量读取LLM配置（API密钥、基础URL、模型名称）
- 从环境变量读取数据库配置
- 提供默认配置值（适合本地开发）

配置文件位置：
- 默认：medical_triage_back/.env（与config.py同目录）
- 支持自定义路径（通过参数传入）

配置项：
- API_KEY: LLM服务的API密钥
- BASE_URL: LLM服务的基础URL
- MODEL: 使用的模型名称
- DATA_FILE: 症状数据文件路径
- ENCODING: 文件编码
- DATABASE_URL: 数据库连接URL

使用示例：
    from config import load_config, Config
    
    # 加载配置（自动读取.env文件）
    config = load_config()
    
    # 访问配置项
    print(config.api_key)
    print(config.model)
    
    # 访问身体部位列表
    print(config.body_types)
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """
    应用配置数据类
    
    包含应用运行所需的所有配置项，使用dataclass简化定义。
    所有字段都有默认值，适合本地开发使用。
    
    字段：
    - api_key: LLM服务的API密钥（默认空字符串）
    - base_url: LLM服务的基础URL（默认阿里云百炼）
    - model: 模型名称（默认qwen-plus）
    - data_file: 症状数据文件路径（默认table.json）
    - encoding: 文件编码（默认utf-8）
    - body_types: 身体部位列表（默认预定义列表）
    - stage_names: 导诊阶段名称列表
    
    示例：
        config = Config(
            api_key='sk-xxxx',
            base_url='https://api.example.com/v1',
            model='gpt-4'
        )
    """
    
    # LLM配置
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    
    # 数据配置
    data_file: str = "table.json"
    encoding: str = "utf-8"
    
    # 导诊配置
    body_types: List[str] = field(default_factory=list)
    stage_names: List[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """
        初始化后处理
        
        如果body_types或stage_names为空，填充默认值。
        这样用户只需要覆盖需要修改的配置项。
        """
        if not self.body_types:
            # 默认身体部位列表，覆盖常见就诊部位
            self.body_types = [
                '头颅', '眼', '耳', '鼻', '口腔', '喉', '面部', '足', '腿', 
                '前颈部', '后颈部', '胸部', '心脏', '上腹部', '下腹部', 
                '双髋部', '生殖系统', '肩膀', '胸椎', '背部', '腰椎', 
                '腰部', '臀部', '手', '手臂', '皮肤'
            ]
        if not self.stage_names:
            # 导诊阶段名称
            self.stage_names = ['身体部位', '初步症状', '具体症状']


def _load_env_file(file_path: str | None = None) -> None:
    """
    从.env文件加载环境变量
    
    解析.env文件，将KEY=VALUE格式的行设置为环境变量。
    已存在的环境变量不会被覆盖（保留系统环境变量优先级）。
    
    支持的格式：
    - KEY=VALUE
    - KEY="VALUE"（带引号）
    - 忽略空行和注释行（以#开头）
    
    Args:
        file_path: .env文件路径，默认使用与config.py同目录的.env文件
        
    示例.env文件：
        API_KEY=sk-xxxx
        BASE_URL=https://api.example.com/v1
        MODEL=gpt-4
        # 这是注释
        DATABASE_URL=sqlite:///app.db
    """
    if file_path is None:
        # 默认路径：与config.py同目录的.env文件
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, '.env')

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            line: str
            for line in f:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue
                # 解析KEY=VALUE格式
                if '=' in line:
                    key, value = line.split('=', 1)
                    # 使用setdefault，不覆盖已存在的环境变量
                    os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        # .env文件不存在时静默处理（使用默认配置）
        pass


def load_config() -> Config:
    """
    加载配置
    
    加载顺序（优先级从低到高）：
    1. Config数据类的默认值
    2. .env文件中定义的环境变量
    3. 系统环境变量
    
    Returns:
        Config配置对象，包含所有配置项
        
    使用示例：
        config = load_config()
        
        # 创建LLM客户端
        client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
    """
    # 加载.env文件到环境变量
    _load_env_file()
    
    # 从环境变量创建Config对象（环境变量优先级高于默认值）
    return Config(
        api_key=os.getenv('API_KEY', ''),
        base_url=os.getenv('BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        model=os.getenv('MODEL', 'qwen-plus'),
        data_file=os.getenv('DATA_FILE', 'table.json'),
        encoding=os.getenv('ENCODING', 'utf-8')
    )
