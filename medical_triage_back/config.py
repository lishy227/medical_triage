"""
配置管理模块 - 使用 python-dotenv 和 pydantic 进行配置管理

功能：
- 从.env文件加载环境变量（使用 python-dotenv）
- 使用 Pydantic 进行配置验证和类型转换
- 支持默认值和配置覆盖

使用示例：
    from config import get_config, Config
    
    # 获取配置（自动读取.env文件，单例模式）
    config = get_config()
    
    # 访问配置项
    print(config.api_key)
    print(config.model)
"""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """
    应用配置类 - 使用 Pydantic Settings 进行验证和管理
    
    配置优先级（从高到低）：
    1. 环境变量
    2. .env 文件
    3. 默认值
    """
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略未定义的环境变量
    )
    
    # LLM配置
    api_key: str = Field(default='', description='LLM服务的API密钥')
    base_url: str = Field(
        default='https://dashscope.aliyuncs.com/compatible-mode/v1',
        description='LLM服务的基础URL'
    )
    model: str = Field(default='qwen-plus', description='使用的模型名称')
    
    # 数据配置
    data_file: str = Field(default='table.json', description='症状数据文件路径')
    encoding: str = Field(default='utf-8', description='文件编码')
    
    # 数据库配置
    database_url: str = Field(
        default='sqlite:///medical_triage.db',
        description='数据库连接URL'
    )

    # 会话存储配置
    redis_url: str = Field(
        default='',
        description='Redis连接URL。留空则使用进程内存存储（开发/单进程），'
                    '填写则使用Redis共享存储（生产/多worker），例如: redis://localhost:6379/0'
    )
    
    # 安全配置
    jwt_secret: str = Field(
        default='',
        description='JWT签名密钥。生产环境必须设置，可通过 JWT_SECRET_KEY 环境变量注入。'
                    '运行: python -c "import secrets; print(secrets.token_urlsafe(43))"'
    )
    jwt_expire_hours: int = Field(
        default=168,  # 7天
        description='JWT过期时间（小时）'
    )
    
    # 导诊配置
    body_types: List[str] = Field(
        default_factory=lambda: [
            '头颅', '眼', '耳', '鼻', '口腔', '喉', '面部', '足', '腿', 
            '前颈部', '后颈部', '胸部', '心脏', '上腹部', '下腹部', 
            '双髋部', '生殖系统', '肩膀', '胸椎', '背部', '腰椎', 
            '腰部', '臀部', '手', '手臂', '皮肤'
        ],
        description='身体部位列表'
    )
    stage_names: List[str] = Field(
        default_factory=lambda: ['身体部位', '初步症状', '具体症状'],
        description='导诊阶段名称列表'
    )
    
    @field_validator('database_url', mode='before')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """确保数据库URL包含协议前缀"""
        if v and '://' not in v:
            return f"sqlite:///{v}"
        return v
    
    @property
    def is_configured(self) -> bool:
        """检查配置是否完整（API密钥是否设置）"""
        return bool(self.api_key)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """
    获取配置（单例模式）
    
    使用 lru_cache 确保配置只加载一次，提高性能
    
    Returns:
        Config配置对象
        
    使用示例：
        config = get_config()
        
        # 创建LLM客户端
        client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
    """
    return Config()


# 向后兼容的别名
load_config = get_config


if __name__ == "__main__":
    # 测试配置加载
    config = get_config()
    print(f"API Key: {'已设置' if config.api_key else '未设置'}")
    print(f"Model: {config.model}")
    print(f"Base URL: {config.base_url}")
    print(f"Database URL: {config.database_url}")
    print(f"JWT Expire: {config.jwt_expire_hours} hours")
    print(f"Body Types: {len(config.body_types)} 个部位")
