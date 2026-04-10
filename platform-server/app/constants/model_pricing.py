"""
主流 LLM 模型参考价格库 (USD per 1K tokens)
用于模型同步时自动填充默认成本

价格参考时间：2025-01
汇率参考：1 RMB ≈ 0.138 USD
"""
from decimal import Decimal
from typing import Dict, Optional

# 价格结构: { "input": 0.000xxx, "output": 0.000xxx }
# 单位：美元 / 1K tokens
MODEL_PRICING_REGISTRY: Dict[str, Dict[str, float]] = {
    # ========== DeepSeek (官网价: 2元/1M in, 8元/1M out) ==========
    # 2元/1M ≈ $0.276/1M = $0.000276/1K
    # 8元/1M ≈ $1.104/1M = $0.001104/1K
    "deepseek-chat": {"input": 0.000276, "output": 0.001104},
    "deepseek-coder": {"input": 0.000276, "output": 0.001104},
    "deepseek-v3": {"input": 0.000276, "output": 0.001104},
    "deepseek-v3.2": {"input": 0.000276, "output": 0.001104},
    "deepseek-reasoner": {"input": 0.000276, "output": 0.001104}, # R1
    "deepseek-r1": {"input": 0.000276, "output": 0.001104},

    # ========== OpenAI (官网价) ==========
    "gpt-4o": {"input": 0.0025, "output": 0.0100},
    "gpt-4o-2024-05-13": {"input": 0.0050, "output": 0.0150},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.0100, "output": 0.0300},
    "gpt-4": {"input": 0.0300, "output": 0.0600},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "o1-preview": {"input": 0.0150, "output": 0.0600},
    "o1-mini": {"input": 0.0030, "output": 0.0120},

    # ========== Qwen (阿里云通义千问) ==========
    # 价格参考自 2024-05 后的大幅降价版
    # qwen-max: 0.0032元/1k input ≈ $0.0004416
    "qwen-max": {"input": 0.0004416, "output": 0.0017664},
    # qwen-plus: 0.0008元/1k input ≈ $0.0001104
    "qwen-plus": {"input": 0.0001104, "output": 0.000276},
    # qwen-flash: 0.0001元/1k input ≈ $0.0000138
    "qwen-flash": {"input": 0.0000138, "output": 0.0000138},
    # qwen-turbo: 0.0003元/1k input ≈ $0.0000414
    "qwen-turbo": {"input": 0.0000414, "output": 0.0000828},
    # qwen-coder: 0.001元/1k input ≈ $0.000138
    "qwen-coder": {"input": 0.000138, "output": 0.000552},
    "qwen-long": {"input": 0.00007, "output": 0.00028},
    "qwen-vl-max": {"input": 0.00276, "output": 0.00276},
    "qwen-vl-plus": {"input": 0.001104, "output": 0.001104},
    
    # ========== Claude (Anthropic) ==========
    "claude-3-5-sonnet-20241022": {"input": 0.0030, "output": 0.0150},
    "claude-3-5-haiku-20241022": {"input": 0.0010, "output": 0.0050},
    "claude-3-opus-20240229": {"input": 0.0150, "output": 0.0750},
    "claude-3-sonnet-20240229": {"input": 0.0030, "output": 0.0150},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},

    # ========== Gemini (Google) ==========
    "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
    "gemini-1.5-flash": {"input": 0.00035, "output": 0.00105},
}

def get_model_price_reference(model_id: str) -> Optional[Dict[str, Decimal]]:
    """
    根据模型 ID 获取参考价格
    支持模糊匹配 (e.g., deepseek-chat-v2 匹配 deepseek-chat)
    """
    if not model_id:
        return None
        
    model_key = model_id.lower()
    
    # 1. 精确匹配
    if model_key in MODEL_PRICING_REGISTRY:
        price = MODEL_PRICING_REGISTRY[model_key]
        return {
            "input": Decimal(str(price["input"])),
            "output": Decimal(str(price["output"]))
        }
    
    # 2. 前缀/包含匹配
    # 按键长度倒序，优先匹配更长的 key (防止 gpt-4 匹配到 gpt-4o)
    sorted_keys = sorted(MODEL_PRICING_REGISTRY.keys(), key=len, reverse=True)
    for key in sorted_keys:
        # 如果模型名包含 key (e.g. "azure-gpt-4o" contains "gpt-4o")
        if key in model_key:
            price = MODEL_PRICING_REGISTRY[key]
            return {
                "input": Decimal(str(price["input"])),
                "output": Decimal(str(price["output"]))
            }
            
    return None

