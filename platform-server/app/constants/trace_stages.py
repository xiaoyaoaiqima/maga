"""
Trace Stage 常量定义

文章生产全链路阶段：
- 内容生成阶段
- 内容治理阶段
- 人工反馈阶段（RLHF）
- 情报回流阶段（规划中）
"""


class TraceStage:
    """Trace 阶段常量"""
    
    # ==================== 内容生成阶段 ====================
    PLUGIN_RENDER = "plugin_render"       # Plugin 变量渲染
    PROMPT_RENDER = "prompt_render"       # Prompt 模板渲染
    GE_GENERATION = "ge_generation"       # GE 内容生成
    
    # ==================== 内容治理阶段 ====================
    AG_BAN_ILLEGAL = "ag_ban_illegal"           # 违规内容检测
    AG_BAN_UNREASONABLE = "ag_ban_unreasonable" # 不合理内容检测
    AG_CRITIC_QUALITY = "ag_critic_quality"     # 质量评分
    
    # ==================== 人工反馈阶段（RLHF）====================
    RLHF_LIKE = "rlhf_like"       # 喜欢/不喜欢操作
    RLHF_ADOPT = "rlhf_adopt"     # 采纳/不采纳/废弃操作
    RLHF_SCORE = "rlhf_score"     # 评分操作
    RLHF_TAG = "rlhf_tag"         # 问题标签操作
    RLHF_EDIT = "rlhf_edit"       # 内容修改操作
    
    # ==================== LLM 调用 ====================
    LLM_CALL = "llm_call"         # LLM API 调用
    
    # ==================== 调试阶段 ====================
    DEBUG = "debug"               # 调试调用
    EXPERT_CALL = "expert_call"   # Expert 调用
    
    # RLHF 阶段列表
    RLHF_STAGES = [
        RLHF_LIKE,
        RLHF_ADOPT,
        RLHF_SCORE,
        RLHF_TAG,
        RLHF_EDIT,
    ]
    
    # 所有阶段列表
    ALL_STAGES = [
        # 内容生成
        PLUGIN_RENDER,
        PROMPT_RENDER,
        GE_GENERATION,
        # 内容治理
        AG_BAN_ILLEGAL,
        AG_BAN_UNREASONABLE,
        AG_CRITIC_QUALITY,
        # 人工反馈
        RLHF_LIKE,
        RLHF_ADOPT,
        RLHF_SCORE,
        RLHF_TAG,
        RLHF_EDIT,
        # LLM
        LLM_CALL,
        # 调试
        DEBUG,
        EXPERT_CALL,
    ]
    
    @classmethod
    def is_rlhf_stage(cls, stage: str) -> bool:
        """判断是否为 RLHF 阶段"""
        return stage in cls.RLHF_STAGES
    
    @classmethod
    def get_stage_display_name(cls, stage: str) -> str:
        """获取阶段显示名称"""
        display_names = {
            cls.PLUGIN_RENDER: "Plugin 渲染",
            cls.PROMPT_RENDER: "Prompt 渲染",
            cls.GE_GENERATION: "GE 生成",
            cls.AG_BAN_ILLEGAL: "违规检测",
            cls.AG_BAN_UNREASONABLE: "不合理检测",
            cls.AG_CRITIC_QUALITY: "质量评分",
            cls.RLHF_LIKE: "喜欢操作",
            cls.RLHF_ADOPT: "采纳操作",
            cls.RLHF_SCORE: "RLHF 评分",
            cls.RLHF_TAG: "问题标签",
            cls.RLHF_EDIT: "内容修改",
            cls.LLM_CALL: "LLM 调用",
            cls.DEBUG: "调试",
            cls.EXPERT_CALL: "Expert 调用",
        }
        return display_names.get(stage, stage)

