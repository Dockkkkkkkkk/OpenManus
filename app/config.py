import threading
import tomllib
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field


def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = get_project_root()
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"


class LLMSettings(BaseModel):
    model: str = Field(..., description="Model name")
    base_url: str = Field(..., description="API base URL")
    api_key: str = Field(..., description="API key")
    max_tokens: int = Field(4096, description="Maximum number of tokens per request")
    temperature: float = Field(1.0, description="Sampling temperature")


class AppConfig(BaseModel):
    llm: Dict[str, LLMSettings]


class Config:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._config = None
                    self._load_initial_config()
                    self._initialized = True

    @staticmethod
    def _get_config_path() -> Path:
        root = PROJECT_ROOT
        config_path = root / "config" / "config.toml"
        if config_path.exists():
            return config_path
        example_path = root / "config" / "config.example.toml"
        if example_path.exists():
            return example_path
        raise FileNotFoundError("No configuration file found in config directory")

    def _load_config(self) -> dict:
        config_path = self._get_config_path()
        with config_path.open("rb") as f:
            return tomllib.load(f)

    def _load_initial_config(self):
        raw_config = self._load_config()
        print(f"[DEBUG] 开始加载配置文件: {self._get_config_path()}")
        
        # 创建配置字典
        config_dict = {"llm": {}}
        
        # 1. 加载通用LLM配置
        base_llm = raw_config.get("llm", {})
        default_settings = {
            "model": base_llm.get("model"),
            "base_url": base_llm.get("base_url"), 
            "api_key": base_llm.get("api_key"),
            "max_tokens": base_llm.get("max_tokens", 4096),
            "temperature": base_llm.get("temperature", 0.0),
        }
        config_dict["llm"]["default"] = default_settings
        safe_api_key = f"{default_settings['api_key'][:5]}...{default_settings['api_key'][-4:]}" if default_settings['api_key'] else "None"
        print(f"[DEBUG] 默认LLM配置: model={default_settings['model']}, base_url={default_settings['base_url']}, api_key={safe_api_key}")
        
        # 2. 加载vision模型配置（如果存在）
        if "vision" in base_llm:
            vision_config = base_llm["vision"]
            vision_settings = {**default_settings, **vision_config}
            config_dict["llm"]["vision"] = vision_settings
            safe_api_key = f"{vision_settings['api_key'][:5]}...{vision_settings['api_key'][-4:]}" if vision_settings['api_key'] else "None"
            print(f"[DEBUG] 视觉模型配置: model={vision_settings['model']}, base_url={vision_settings['base_url']}, api_key={safe_api_key}")
        
        # 3. 加载OpenAI配置（如果存在）
        if "openai" in raw_config:
            openai_settings = raw_config["openai"]
            openai_config = {
                "model": openai_settings.get("model"),
                "base_url": openai_settings.get("api_base"),
                "api_key": openai_settings.get("api_key"),
                "max_tokens": base_llm.get("max_tokens", 4096),
                "temperature": base_llm.get("temperature", 0.0),
            }
            config_dict["llm"]["openai"] = openai_config
            safe_api_key = f"{openai_config['api_key'][:5]}...{openai_config['api_key'][-4:]}" if openai_config['api_key'] else "None"
            print(f"[DEBUG] OpenAI配置: model={openai_config['model']}, base_url={openai_config['base_url']}, api_key={safe_api_key}")
        
        # 4. 为各个代理分配特定模型配置
        # 确保为所有需要的代理提供配置
        agent_configs = {
            "manus": config_dict["llm"].get("default"),  # Manus代理使用默认LLM
            "swe": config_dict["llm"].get("openai", config_dict["llm"]["default"]),  # SWE代理优先使用OpenAI，否则使用默认
        }
        
        # 将代理配置添加到主配置中
        for agent_name, agent_config in agent_configs.items():
            if agent_name not in config_dict["llm"]:
                config_dict["llm"][agent_name] = agent_config
                safe_api_key = f"{agent_config['api_key'][:5]}...{agent_config['api_key'][-4:]}" if agent_config['api_key'] else "None"
                print(f"[DEBUG] {agent_name}代理配置: model={agent_config['model']}, base_url={agent_config['base_url']}, api_key={safe_api_key}")
        
        # 5. 加载其他特定LLM配置
        llm_overrides = {
            k: v for k, v in base_llm.items() 
            if isinstance(v, dict) and k != "vision"
        }
        
        for name, override_config in llm_overrides.items():
            merged_config = {**default_settings, **override_config}
            config_dict["llm"][name] = merged_config
            safe_api_key = f"{merged_config['api_key'][:5]}...{merged_config['api_key'][-4:]}" if merged_config['api_key'] else "None"
            print(f"[DEBUG] 特定LLM配置 {name}: model={merged_config['model']}, base_url={merged_config['base_url']}, api_key={safe_api_key}")
        
        # 创建最终的配置对象
        self._config = AppConfig(**config_dict)
        
        # 打印已加载的所有配置
        print(f"[DEBUG] 配置加载完成，可用配置: {list(config_dict['llm'].keys())}")

    @property
    def llm(self) -> Dict[str, LLMSettings]:
        return self._config.llm


config = Config()
