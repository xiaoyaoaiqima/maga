"""
LLM response parsing helpers.
"""
import json
from typing import Any, Dict, List, Optional


def parse_function_calls(message: Dict[str, Any]) -> Optional[str]:
    """
    Extract function/tool calls from an LLM message and return JSON string.
    Supports OpenAI tool_calls (new) and function_call (legacy).
    """
    if message.get("tool_calls"):
        function_calls: List[Dict[str, Any]] = []
        for tool_call in message["tool_calls"]:
            function_info = tool_call.get("function", {})
            function_calls.append(
                {
                    "id": tool_call.get("id", ""),
                    "type": tool_call.get("type", "function"),
                    "function": {
                        "name": function_info.get("name", ""),
                        "arguments": function_info.get("arguments", ""),
                    },
                }
            )
        return json.dumps(
            {
                "type": "function_calls",
                "function_calls": function_calls,
            },
            ensure_ascii=False,
        )
    
    if message.get("function_call"):
        function_call = message["function_call"]
        return json.dumps(
            {
                "type": "function_calls",
                "function_calls": [
                    {
                        "id": "",
                        "type": "function",
                        "function": {
                            "name": function_call.get("name", ""),
                            "arguments": function_call.get("arguments", ""),
                        },
                    }
                ],
            },
            ensure_ascii=False,
        )
    
    return None
