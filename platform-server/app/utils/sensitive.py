"""
敏感数据脱敏工具

支持对以下类型数据进行脱敏：
- 密码、token、secret
- 手机号、身份证号
- 邮箱、银行卡号
"""
import re
from typing import Any, Optional

from app.core.config import settings


# 预编译的正则表达式
PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
ID_CARD_PATTERN = re.compile(r'\d{17}[\dXx]|\d{15}')
BANK_CARD_PATTERN = re.compile(r'\d{16,19}')


def mask_value(value: str, mask_char: str = "*", visible_prefix: int = 3, visible_suffix: int = 4) -> str:
    """
    对字符串值进行脱敏处理
    
    Args:
        value: 要脱敏的字符串
        mask_char: 脱敏字符，默认 *
        visible_prefix: 保留前几位，默认 3
        visible_suffix: 保留后几位，默认 4
        
    Returns:
        脱敏后的字符串
    """
    if not value or not isinstance(value, str):
        return value
    
    length = len(value)
    
    # 短字符串直接全部脱敏
    if length <= visible_prefix + visible_suffix:
        return mask_char * length
    
    # 保留前后几位，中间脱敏
    mask_length = length - visible_prefix - visible_suffix
    return value[:visible_prefix] + mask_char * mask_length + value[-visible_suffix:]


def mask_phone(phone: str) -> str:
    """手机号脱敏：保留前3后4"""
    if not phone or len(phone) != 11:
        return phone
    return phone[:3] + "****" + phone[-4:]


def mask_email(email: str) -> str:
    """邮箱脱敏：用户名只显示前2位"""
    if not email or "@" not in email:
        return email
    username, domain = email.split("@", 1)
    if len(username) <= 2:
        masked_username = "*" * len(username)
    else:
        masked_username = username[:2] + "*" * (len(username) - 2)
    return f"{masked_username}@{domain}"


def mask_id_card(id_card: str) -> str:
    """身份证号脱敏：保留前6后4"""
    if not id_card or len(id_card) not in (15, 18):
        return id_card
    return id_card[:6] + "*" * (len(id_card) - 10) + id_card[-4:]


def mask_bank_card(card_number: str) -> str:
    """银行卡号脱敏：保留前4后4"""
    if not card_number or len(card_number) < 8:
        return card_number
    return card_number[:4] + "*" * (len(card_number) - 8) + card_number[-4:]


def mask_token(token: str) -> str:
    """Token 脱敏：只显示前8位"""
    if not token:
        return token
    if len(token) <= 8:
        return "*" * len(token)
    return token[:8] + "*" * (len(token) - 8)


def _is_sensitive_key(key: str, sensitive_fields: Optional[list[str]] = None) -> bool:
    """
    判断键名是否为敏感字段
    
    Args:
        key: 键名
        sensitive_fields: 敏感字段列表，默认使用配置中的列表
        
    Returns:
        是否为敏感字段
    """
    if sensitive_fields is None:
        sensitive_fields = settings.LOG_SENSITIVE_FIELDS
    
    key_lower = key.lower()
    return any(field in key_lower for field in sensitive_fields)


def mask_sensitive_data(
    data: Any,
    enabled: Optional[bool] = None,
    sensitive_fields: Optional[list[str]] = None,
    max_depth: int = 10
) -> Any:
    """
    递归脱敏敏感数据
    
    Args:
        data: 要处理的数据（dict、list 或其他）
        enabled: 是否启用脱敏，默认使用配置
        sensitive_fields: 敏感字段列表，默认使用配置
        max_depth: 最大递归深度，防止无限递归
        
    Returns:
        脱敏后的数据（深拷贝）
    """
    # 检查是否启用脱敏
    if enabled is None:
        enabled = settings.effective_sensitive_mask
    
    if not enabled:
        return data
    
    if max_depth <= 0:
        return data
    
    if sensitive_fields is None:
        sensitive_fields = settings.LOG_SENSITIVE_FIELDS
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if _is_sensitive_key(key, sensitive_fields):
                # 敏感字段，进行脱敏
                if isinstance(value, str):
                    result[key] = _mask_by_pattern(key, value)
                elif value is not None:
                    result[key] = "***"
                else:
                    result[key] = value
            else:
                # 非敏感字段，递归处理
                result[key] = mask_sensitive_data(
                    value, 
                    enabled=enabled, 
                    sensitive_fields=sensitive_fields,
                    max_depth=max_depth - 1
                )
        return result
    
    elif isinstance(data, (list, tuple)):
        return type(data)(
            mask_sensitive_data(
                item, 
                enabled=enabled, 
                sensitive_fields=sensitive_fields,
                max_depth=max_depth - 1
            ) 
            for item in data
        )
    
    elif isinstance(data, str):
        # 对字符串值进行模式匹配脱敏
        return _mask_string_patterns(data)
    
    else:
        return data


def _mask_by_pattern(key: str, value: str) -> str:
    """根据字段名选择合适的脱敏方式"""
    key_lower = key.lower()
    
    if any(k in key_lower for k in ["phone", "mobile", "telephone"]):
        return mask_phone(value)
    elif any(k in key_lower for k in ["email"]):
        return mask_email(value)
    elif any(k in key_lower for k in ["id_card", "idcard", "identity"]):
        return mask_id_card(value)
    elif any(k in key_lower for k in ["card", "bank"]):
        return mask_bank_card(value)
    elif any(k in key_lower for k in ["token", "secret", "key", "authorization"]):
        return mask_token(value)
    else:
        # 默认脱敏：显示前3后4
        return mask_value(value)


def _mask_string_patterns(value: str) -> str:
    """
    对字符串中的敏感模式进行脱敏
    
    用于处理日志消息中可能包含的敏感信息
    """
    result = value
    
    # 脱敏手机号
    for phone in PHONE_PATTERN.findall(result):
        result = result.replace(phone, mask_phone(phone))
    
    # 脱敏邮箱
    for email in EMAIL_PATTERN.findall(result):
        result = result.replace(email, mask_email(email))
    
    # 脱敏身份证号
    for id_card in ID_CARD_PATTERN.findall(result):
        if len(id_card) in (15, 18):
            result = result.replace(id_card, mask_id_card(id_card))
    
    return result


def mask_headers(headers: dict) -> dict:
    """
    脱敏 HTTP 请求头
    
    特别处理 Authorization 等敏感头
    """
    sensitive_headers = [
        "authorization", "x-api-key", "x-auth-token", 
        "cookie", "set-cookie", "x-access-token"
    ]
    
    result = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if any(h in key_lower for h in sensitive_headers):
            if isinstance(value, str) and len(value) > 10:
                result[key] = value[:10] + "***"
            else:
                result[key] = "***"
        else:
            result[key] = value
    
    return result

