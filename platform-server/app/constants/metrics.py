"""
RAAP 预定义指标查询配置
"""

DIMENSION_FILTER_TEMPLATE = """
    AND ({{tenant_filter}})
    AND ({{activity_filter}})
    AND ({{agent_filter}})
"""

# 预定义的 RAAP 指标查询（支持 tenant/activity/agent 多维度过滤）
RAAP_METRIC_QUERIES = {
    # ==================== AI算力看板 ====================
    "total_llm_token_cost": {
        "name": "成本汇总-总LLM Token成本",
        "query": """
            SELECT
                DATE(t.created_at) as date,
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) as total_cost,
                SUM(t.input_tokens) as total_input_tokens,
                SUM(t.output_tokens) as total_output_tokens
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY DATE(t.created_at), COALESCE(t.currency, 'USD')
            ORDER BY date DESC
        """,
        "description": "指定时间内 LLM Token 成本总额（按日期和币种分组）",
    },
    "avg_cost_per_output": {
        "name": "成本汇总-单篇内容平均成本",
        "query": """
            SELECT
                currency,
                AVG(content_cost) as avg_cost,
                COUNT(*) as content_count
            FROM (
                SELECT
                    t.content_id,
                    COALESCE(t.currency, 'USD') as currency,
                    SUM(t.total_cost) as content_cost
                FROM expert_call_trace t
                LEFT JOIN job j ON t.job_id = j.job_id
                WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
                  AND t.content_id IS NOT NULL
                  AND (j.is_deleted IS NULL OR j.is_deleted = 0)
                  AND ({{tenant_filter}})
                  AND ({{activity_filter}})
                  AND ({{agent_filter}})
                GROUP BY t.content_id, COALESCE(t.currency, 'USD')
            ) content_costs
            GROUP BY currency
        """,
        "description": "单篇内容平均成本（按币种分组）",
    },
    "llm_cost_by_model": {
        "name": "成本结构-按模型分布",
        "query": """
            SELECT
                t.model_code,
                t.provider_code,
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) AS total_cost,
                SUM(t.input_tokens) AS input_tokens,
                SUM(t.output_tokens) AS output_tokens,
                COUNT(*) AS call_count
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.model_code, t.provider_code, COALESCE(t.currency, 'USD')
            ORDER BY total_cost DESC
        """,
        "description": "按 LLM 模型和币种的成本分布",
    },
    "stage_avg_latency": {
        "name": "成本细分-阶段平均耗时",
        "query": """
            SELECT 
                t.stage,
                AVG(t.duration_ms) AS avg_latency_ms,
                MAX(t.duration_ms) AS max_latency_ms,
                MIN(t.duration_ms) AS min_latency_ms,
                COUNT(*) AS total_calls
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.stage
            ORDER BY avg_latency_ms DESC
        """,
        "description": "各执行阶段平均耗时（支持租户/活动/Agent过滤）",
    },
    "stage_fail_rate": {
        "name": "成本细分-阶段失败率",
        "query": """
            SELECT 
                t.stage,
                COUNT(*) as total_count,
                SUM(CASE WHEN t.status != 'success' THEN 1 ELSE 0 END) as fail_count,
                ROUND(SUM(CASE WHEN t.status != 'success' THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as fail_rate
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.stage
            ORDER BY fail_rate DESC
        """,
        "description": "各执行阶段失败率（支持租户/活动/Agent过滤）",
    },
    "governance_llm_cost": {
        "name": "成本细分-治理中心(AG)成本",
        "query": """
            SELECT
                DATE(t.created_at) as date,
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) as total_cost,
                SUM(t.input_tokens) as total_input_tokens,
                SUM(t.output_tokens) as total_output_tokens
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND t.stage LIKE 'ag_%'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY DATE(t.created_at), COALESCE(t.currency, 'USD')
            ORDER BY date DESC
        """,
        "description": "数据治理中心(AG)的 LLM 成本（按日期和币种分组）",
    },
    "expert_plugin_llm_cost": {
        "name": "成本细分-Expert插件成本",
        "query": """
            SELECT
                DATE(t.created_at) as date,
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) as total_cost,
                SUM(t.input_tokens) as total_input_tokens,
                SUM(t.output_tokens) as total_output_tokens
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND t.stage LIKE 'plugin_%'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY DATE(t.created_at), COALESCE(t.currency, 'USD')
            ORDER BY date DESC
        """,
        "description": "Expert 插件执行的 LLM 成本（按日期和币种分组）",
    },
    
    # ==================== 生成中心 ====================
    "generation_total_calls": {
        "name": "生成中心-总调用次数",
        "query": """
            SELECT
                COUNT(*) as total_count
            FROM job j
            WHERE j.create_time >= '{{start_date}}' AND j.create_time < '{{end_date}}'
              AND j.is_deleted = 0
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "生成中心总调用任务数（支持租户/活动/Agent过滤）",
    },
    "generation_agent_stats": {
        "name": "生成中心-Agent统计",
        "query": """
            SELECT
                content_stats.agent_code,
                COALESCE(a.agent_name, content_stats.agent_code) as agent_name,
                content_stats.content_count,
                COALESCE(call_stats.call_count, 0) as call_count,
                CASE WHEN running_jobs.running_count > 0 THEN 1 ELSE 0 END as is_running
            FROM (
                -- 主查询：基于 content 表统计生成数量（有生成数据的 agent）
                SELECT
                    c.agent_code,
                    COUNT(*) as content_count
                FROM content c
                WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
                  AND c.is_deleted = 0
                  AND c.agent_code IS NOT NULL
                  AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
                  AND (c.activity_id IS NULL OR {{content_activity_filter}})
                  AND ({{content_agent_filter}})
                GROUP BY c.agent_code
            ) content_stats
            LEFT JOIN agent a ON a.agent_code = content_stats.agent_code AND a.is_deleted = 0
            LEFT JOIN (
                -- 根据 content_id 统计 expert_call_trace 表中的调用次数
                SELECT
                    c.agent_code,
                    COUNT(DISTINCT t.id) as call_count
                FROM content c
                INNER JOIN expert_call_trace t ON c.content_id = t.content_id
                WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
                  AND c.is_deleted = 0
                  AND c.agent_code IS NOT NULL
                  AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
                  AND (c.activity_id IS NULL OR {{content_activity_filter}})
                  AND ({{content_agent_filter}})
                GROUP BY c.agent_code
            ) call_stats ON content_stats.agent_code = call_stats.agent_code
            LEFT JOIN (
                -- 根据 agent_code 查 job 表是否有 DEPLOYED 状态的任务
                SELECT
                    agent_code,
                    COUNT(*) as running_count
                FROM job
                WHERE status = 'DEPLOYED'
                  AND is_deleted = 0
                  AND agent_code IS NOT NULL
                GROUP BY agent_code
            ) running_jobs ON content_stats.agent_code = running_jobs.agent_code
            ORDER BY content_stats.content_count DESC
        """,
        "description": "各 Agent 的统计（包含已删除 Agent 的 content 统计，调用次数来自 expert_call_trace 表，运行状态来自 job 表 DEPLOYED 状态）",
    },
    "generation_agent_daily_trend": {
        "name": "生成中心-Agent日趋势（任务数）",
        "query": """
            SELECT
                j.agent_code,
                DATE(j.create_time) as date,
                COUNT(*) as call_count
            FROM job j
            WHERE j.create_time >= '{{start_date}}' AND j.create_time < '{{end_date}}'
              AND j.is_deleted = 0
              AND j.agent_code IS NOT NULL
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY j.agent_code, DATE(j.create_time)
            ORDER BY DATE(j.create_time) ASC
        """,
        "description": "各 Agent 的每日任务数趋势",
    },
    "generation_agent_content_daily_trend": {
        "name": "生成中心-Agent每日文章数趋势",
        "query": """
            SELECT
                c.agent_code,
                DATE(c.create_time) as date,
                COUNT(*) as content_count
            FROM content c
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
            GROUP BY c.agent_code, DATE(c.create_time)
            ORDER BY DATE(c.create_time) ASC
        """,
        "description": "各 Agent 的每日生成文章数量趋势",
    },
    "ge_expert_request_count": {
        "name": "生成中心-Expert请求数量",
        "query": """
            SELECT
                t.expert_config_code,
                COUNT(*) as request_count,
                SUM(CASE WHEN t.status = 'success' THEN 1 ELSE 0 END) as success_count,
                ROUND(SUM(CASE WHEN t.status = 'success' THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as success_rate
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND t.stage = 'generation'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.expert_config_code
        """,
        "description": "GE Expert 接收任务数量和成功率（支持租户/活动/Agent过滤）",
    },
    "ge_expert_success_output_count": {
        "name": "生成中心-成功输出内容数量",
        "query": """
            SELECT
                t.expert_config_code,
                COUNT(DISTINCT t.content_id) AS success_outputs
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.status = 'success'
              AND t.stage = 'generation'
              AND t.content_id IS NOT NULL
              AND t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.expert_config_code
        """,
        "description": "GE Expert 成功输出内容数量（支持租户/活动/Agent过滤）",
    },
    "ge_expert_avg_latency": {
        "name": "生成中心-平均生成耗时",
        "query": """
            SELECT
                t.expert_config_code,
                AVG(t.duration_ms) AS avg_latency_ms,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.duration_ms) AS p50_latency_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY t.duration_ms) AS p95_latency_ms,
                COUNT(*) AS total_tasks
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND t.stage = 'generation'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.expert_config_code
            ORDER BY avg_latency_ms DESC
        """,
        "description": "GE Expert 平均内容生成耗时（支持租户/活动/Agent过滤）",
    },
    "ge_expert_avg_llm_cost": {
        "name": "生成中心-单内容平均 LLM 成本",
        "query": """
            SELECT
                t.expert_config_code,
                AVG(t.total_cost) AS avg_llm_cost,
                SUM(t.total_cost) AS total_llm_cost,
                COUNT(*) AS call_count
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND t.stage = 'generation'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.expert_config_code
        """,
        "description": "GE Expert 单内容平均 LLM 成本（支持租户/活动/Agent过滤）",
    },

    # ==================== 对齐治理中心 (AG) ====================
    "ag_governance_overview": {
        "name": "AG治理-概览统计",
        "query": """
            SELECT
                COUNT(*) as total_checks,
                SUM(CASE WHEN CAST(JSON_UNQUOTE(JSON_EXTRACT(t.result_summary, '$.score')) AS UNSIGNED) < 60 THEN 1 ELSE 0 END) as total_blocks,
                ROUND(SUM(CASE WHEN CAST(JSON_UNQUOTE(JSON_EXTRACT(t.result_summary, '$.score')) AS UNSIGNED) < 60 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100, 2) as block_rate
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.stage LIKE 'ag_%'
              AND t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "AG 治理总览（审核次数、拦截次数、拦截率）",
    },
    "ag_reject_distribution": {
        "name": "AG治理-拦截分布",
        "query": """
            SELECT
                t.stage,
                COUNT(*) as check_count,
                SUM(CASE WHEN CAST(JSON_UNQUOTE(JSON_EXTRACT(t.result_summary, '$.score')) AS UNSIGNED) < 60 THEN 1 ELSE 0 END) as block_count,
                ROUND(SUM(CASE WHEN CAST(JSON_UNQUOTE(JSON_EXTRACT(t.result_summary, '$.score')) AS UNSIGNED) < 60 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100, 2) as block_rate
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.stage LIKE 'ag_%'
              AND t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.stage
            ORDER BY block_count DESC
        """,
        "description": "各治理阶段的拦截分布",
    },

    # ==================== 多维度AI评论专家组 ====================
    "critic_content_stats": {
        "name": "评论专家组-文章统计",
        "query": """
            SELECT 
                SUM(CASE WHEN c.is_valid IS NULL THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE WHEN c.is_valid IS NOT NULL THEN 1 ELSE 0 END) as total_input_count,
                SUM(CASE WHEN c.is_valid = 0 THEN 1 ELSE 0 END) as rejected_count,
                ROUND(
                    SUM(CASE WHEN c.is_valid = 0 THEN 1 ELSE 0 END) * 100.0 / 
                    NULLIF(SUM(CASE WHEN c.is_valid IS NOT NULL THEN 1 ELSE 0 END), 0),
                    2
                ) as rejected_rate
            FROM content c
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
        """,
        "description": "评论专家组文章统计（待输入、总输入、总拒绝、拒绝比例）",
    },
    "critic_expert_stats": {
        "name": "评论专家组-各专家统计",
        "query": """
            SELECT
                csr.expert_func,
                le.id,
                le.expert_name,
                le.expert_type,
                le.description,
                COUNT(*) as total_input,
                SUM(CASE WHEN csr.passed = 0 THEN 1 ELSE 0 END) as rejected_count
            FROM critic_score_record csr
            INNER JOIN logic_expert le
                ON le.expert_func = csr.expert_func
               AND le.expert_type = 'BAN'
               AND le.is_deleted = 0
               AND le.enabled = 1
            WHERE csr.create_time >= '{{start_date}}' AND csr.create_time < '{{end_date}}'
              AND csr.source_type = 'job'
            GROUP BY csr.expert_func, le.id, le.expert_name, le.expert_type, le.description
            ORDER BY le.id
        """,
        "description": "各评论专家的统计（不合法/不合规/不合理/不合目的），从 logic_expert 表中获取 expert_type = BAN 的专家",
    },
    "critic_quality_dimensions": {
        "name": "评论专家组-文章质量六维度",
        "query": """
            SELECT
                csr.expert_func,
                le.expert_name,
                ROUND(AVG(csr.score), 2) as avg_score
            FROM critic_score_record csr
            INNER JOIN logic_expert le
                ON le.expert_func = csr.expert_func
               AND le.expert_type = 'CRITIC'
               AND le.is_deleted = 0
               AND le.enabled = 1
            WHERE csr.create_time >= '{{start_date}}' AND csr.create_time < '{{end_date}}'
              AND csr.source_type = 'job'
            GROUP BY csr.expert_func, le.expert_name
            ORDER BY le.expert_name
        """,
        "description": "文章质量六维度平均分（优雅性/营销效果/内容质量/品牌匹配/创造力/人设真实感）",
    },
    
    # ==================== 治理中心 ====================
    "governance_persona_stats": {
        "name": "治理中心-人设多样性统计",
        "query": """
            SELECT 
                COUNT(DISTINCT JSON_UNQUOTE(JSON_EXTRACT(c.context_list, '$."人设"'))) as persona_count,
                COUNT(CASE WHEN JSON_EXTRACT(c.context_list, '$."人设"') IS NOT NULL THEN 1 END) as with_persona_count,
                COUNT(*) as total_count,
                ROUND(COUNT(CASE WHEN JSON_EXTRACT(c.context_list, '$."人设"') IS NOT NULL THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2) as persona_ratio
            FROM content c
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
        """,
        "description": "人设多样性统计（人设数量、人设适配占比）",
    },
    "governance_persona_distribution": {
        "name": "治理中心-人设分布",
        "query": """
            SELECT 
                JSON_UNQUOTE(JSON_EXTRACT(c.context_list, '$."人设"')) as persona_name,
                COUNT(*) as content_count
            FROM content c
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND JSON_EXTRACT(c.context_list, '$."人设"') IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
            GROUP BY JSON_UNQUOTE(JSON_EXTRACT(c.context_list, '$."人设"'))
            ORDER BY content_count DESC
            LIMIT 10
        """,
        "description": "人设分布Top10",
    },
    "governance_quality_trend": {
        "name": "治理中心-内容质量趋势",
        "query": """
            SELECT
                DATE_FORMAT(csr.create_time, '%Y-%m-%d %H:%i') as time_minute,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticMarket' THEN csr.score END), 2) as marketing_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticGrace' THEN csr.score END), 2) as grace_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticContentQuality' THEN csr.score END), 2) as quality_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticBrandAlign' THEN csr.score END), 2) as brand_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticCreativity' THEN csr.score END), 2) as creativity_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticPersonaAuth' THEN csr.score END), 2) as persona_score,
                ROUND(AVG(csr.score), 2) as avg_score
            FROM critic_score_record csr
            WHERE csr.create_time >= '{{start_date}}' AND csr.create_time < '{{end_date}}'
              AND csr.source_type = 'job'
              AND csr.expert_func IN (
                  SELECT expert_func FROM logic_expert
                  WHERE expert_type = 'CRITIC' AND is_deleted = 0 AND enabled = 1
              )
            GROUP BY DATE_FORMAT(csr.create_time, '%Y-%m-%d %H:%i')
            ORDER BY DATE_FORMAT(csr.create_time, '%Y-%m-%d %H:%i')
        """,
        "description": "六维度质量评分按分钟趋势",
    },
    "governance_quality_by_agent": {
        "name": "治理中心-Agent六维评分",
        "query": """
            SELECT
                c.agent_code,
                a.agent_name,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticMarket' THEN csr.score END), 2) as marketing_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticGrace' THEN csr.score END), 2) as grace_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticContentQuality' THEN csr.score END), 2) as quality_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticBrandAlign' THEN csr.score END), 2) as brand_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticCreativity' THEN csr.score END), 2) as creativity_score,
                ROUND(AVG(CASE WHEN csr.expert_func = 'CriticPersonaAuth' THEN csr.score END), 2) as persona_score,
                ROUND(AVG(csr.score), 2) as avg_score,
                COUNT(DISTINCT c.content_id) as content_count
            FROM critic_score_record csr
            INNER JOIN content c ON csr.content_id = c.content_id
            LEFT JOIN agent a ON c.agent_code = a.agent_code AND a.is_deleted = 0
            WHERE csr.create_time >= '{{start_date}}' AND csr.create_time < '{{end_date}}'
              AND csr.source_type = 'job'
              AND csr.expert_func IN (
                  SELECT expert_func FROM logic_expert
                  WHERE expert_type = 'CRITIC' AND is_deleted = 0 AND enabled = 1
              )
              AND c.agent_code IS NOT NULL
            GROUP BY c.agent_code, a.agent_name
            ORDER BY avg_score DESC
        """,
        "description": "按Agent分组的六维度质量评分平均值",
    },
    "critic_expert_score_distribution": {
        "name": "评分专家-分数区间分布(5区间)",
        "query": """
            SELECT
                csr.expert_func,
                le.expert_name,
                CONCAT('r', LEAST(FLOOR(csr.score / 20) + 1, 5)) as score_range,
                COUNT(1) as content_count
            FROM critic_score_record csr
            INNER JOIN logic_expert le
                ON le.expert_func = csr.expert_func
               AND le.expert_type = 'CRITIC'
               AND le.is_deleted = 0
               AND le.enabled = 1
            WHERE csr.create_time >= '{{start_date}}' AND csr.create_time < '{{end_date}}'
              AND csr.source_type = 'job'
            GROUP BY csr.expert_func, le.expert_name, score_range
            ORDER BY le.expert_name, score_range DESC
        """,
        "description": "六个评分专家在不同分数区间(0-19,20-39,40-59,60-79,80-100)的文章数分布",
    },
    "critic_expert_score_distribution_10": {
        "name": "评分专家-分数区间分布(10区间)",
        "query": """
            SELECT
                csr.expert_func,
                le.expert_name,
                FLOOR(csr.score / 10) * 10 as score_range,
                COUNT(1) as content_count
            FROM critic_score_record csr
            INNER JOIN logic_expert le
                ON le.expert_func = csr.expert_func
               AND le.expert_type = 'CRITIC'
               AND le.is_deleted = 0
               AND le.enabled = 1
            WHERE csr.create_time >= '{{start_date}}' AND csr.create_time < '{{end_date}}'
              AND csr.source_type = 'job'
            GROUP BY csr.expert_func, le.expert_name, score_range
            ORDER BY le.expert_name, score_range
        """,
        "description": "六个评分专家在10分区间(0-9,10-19,...,90-100)的文章数分布，用于内容丰富度热力图",
    },
    
    # ==================== RLHF ====================
    "rlhf_user_like_rate": {
        "name": "RLHF-用户喜欢比例",
        "query": """
            SELECT
                COUNT(CASE WHEN f.like_status = 1 THEN 1 END) as like_count,
                COUNT(CASE WHEN f.like_status = -1 THEN 1 END) as dislike_count,
                COUNT(*) as total_count,
                ROUND(COUNT(CASE WHEN f.like_status = 1 THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2) as like_rate
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.like_status != 0
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "用户喜欢比例（支持租户/活动/Agent过滤）",
    },
    "rlhf_adopt_rate": {
        "name": "RLHF-用户采纳比例",
        "query": """
            SELECT
                COUNT(CASE WHEN f.adopt_status = 1 THEN 1 END) as adopt_count,
                COUNT(CASE WHEN f.adopt_status = -1 THEN 1 END) as reject_count,
                COUNT(*) as total_count,
                ROUND(COUNT(CASE WHEN f.adopt_status = 1 THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2) as adopt_rate
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.adopt_status != 0
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "用户采纳内容比例（支持租户/活动/Agent过滤）",
    },
    "rlhf_user_dislike_rate": {
        "name": "RLHF-用户不喜欢比例",
        "query": """
            SELECT
                COUNT(CASE WHEN f.like_status = -1 THEN 1 END) as dislike_count,
                COUNT(*) as total_count,
                ROUND(COUNT(CASE WHEN f.like_status = -1 THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2) as dislike_rate
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.like_status != 0
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "用户不喜欢比例（支持租户/活动/Agent过滤）",
    },
    "rlhf_edit_after_adopt_rate": {
        "name": "RLHF-采纳后被修改比例",
        "query": """
            SELECT
                COUNT(CASE WHEN f.adopt_status = 1 AND f.modify_count > 0 THEN 1 END) as edited_after_adopt,
                COUNT(CASE WHEN f.adopt_status = 1 THEN 1 END) as adopt_count,
                ROUND(COUNT(CASE WHEN f.adopt_status = 1 AND f.modify_count > 0 THEN 1 END) /
                      NULLIF(COUNT(CASE WHEN f.adopt_status = 1 THEN 1 END), 0) * 100, 2) as edit_after_adopt_rate
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "采纳后被修改的比例（支持租户/活动/Agent过滤）",
    },
    "rlhf_issue_type_distribution": {
        "name": "RLHF-问题类型分布",
        "query": """
            SELECT
                t.tag_name AS issue_type,
                COUNT(f.id) AS issue_count
            FROM rlhf_issue_tag t
            INNER JOIN rlhf_feedback f ON JSON_CONTAINS(f.issue_tag_ids, CAST(t.id AS JSON))
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.tag_name
            ORDER BY issue_count DESC
        """,
        "description": "反馈问题类型分布（支持租户/活动/Agent过滤）",
    },
    
    # ==================== RLHF 人工专家反馈报告 ====================
    "rlhf_inspection_stats": {
        "name": "RLHF报告-抽检反馈统计",
        "query": """
            SELECT
                COUNT(*) as total_inspection_count,
                COUNT(CASE WHEN f.review_status = 'LIKED' THEN 1 END) as like_count,
                COUNT(CASE WHEN f.review_status = 'DISLIKED' THEN 1 END) as dislike_count,
                ROUND(COUNT(CASE WHEN f.review_status = 'LIKED' THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2) as like_rate,
                ROUND(COUNT(CASE WHEN f.review_status = 'DISLIKED' THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2) as dislike_rate,
                0 as like_edit_rate
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.review_status != 'PENDING'
              AND f.is_deleted = 0
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
        """,
        "description": "人工专家反馈报告统计（共抽检文章数量、喜欢数、不喜欢数、喜欢率、不喜欢率、喜欢编辑率）",
    },
    "rlhf_inspection_issue_tag_distribution": {
        "name": "RLHF报告-问题标签分布柱状图",
        "query": """
            SELECT
                t.id as tag_id,
                t.tag_name,
                t.tag_category,
                COUNT(f.id) AS count
            FROM rlhf_issue_tag t
            INNER JOIN rlhf_feedback f ON JSON_CONTAINS(f.issue_tag_ids, CAST(t.id AS JSON))
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.review_status != 'PENDING'
              AND f.is_deleted = 0
              AND t.is_deleted = 0
              AND t.enabled = 1
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.id, t.tag_name, t.tag_category
            ORDER BY count DESC
        """,
        "description": "人工专家反馈报告-问题标签分布（用于柱状图）",
    },
    "rlhf_inspection_issue_tag_wordcloud": {
        "name": "RLHF报告-问题标签词云",
        "query": """
            SELECT
                t.tag_name as name,
                COUNT(f.id) AS value
            FROM rlhf_issue_tag t
            INNER JOIN rlhf_feedback f ON JSON_CONTAINS(f.issue_tag_ids, CAST(t.id AS JSON))
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.review_status != 'PENDING'
              AND f.is_deleted = 0
              AND t.is_deleted = 0
              AND t.enabled = 1
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY t.tag_name
            HAVING COUNT(f.id) > 0
            ORDER BY value DESC
            LIMIT 100
        """,
        "description": "人工专家反馈报告-问题标签词云数据",
    },
    "rlhf_inspection_detail_list": {
        "name": "RLHF报告-抽检详情列表",
        "query": """
            SELECT
                f.id as article_id,
                f.title as inspection_title,
                SUBSTRING(f.content, 1, 100) as content_preview,
                CASE
                    WHEN f.adopt_status = 1 THEN '采纳'
                    WHEN f.adopt_status = -1 THEN '不采纳'
                    WHEN f.review_status = 'LIKED' THEN '喜欢'
                    WHEN f.review_status = 'DISLIKED' THEN '不喜欢'
                    ELSE '待处理'
                END as inspection_result,
                COALESCE(f.review_user_name, f.like_user_name, f.adopt_user_name) as inspector_name,
                COALESCE(f.review_time, f.like_time, f.adopt_time, f.updated_at) as inspection_time,
                f.modified_title,
                SUBSTRING(f.modified_content, 1, 100) as modified_content_preview
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.review_status != 'PENDING'
              AND f.is_deleted = 0
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            ORDER BY COALESCE(f.review_time, f.like_time, f.adopt_time, f.updated_at) DESC
        """,
        "description": "人工专家反馈报告-抽检详情列表（支持分页）",
        "supports_pagination": True,
    },
    "rlhf_improvement_summary": {
        "name": "RLHF报告-改进点摘要",
        "query": """
            SELECT
                f.id as feedback_id,
                ann.selected_text,
                ann.comment,
                ann.user_name,
                ann.create_time
            FROM rlhf_feedback f
            CROSS JOIN JSON_TABLE(
                f.annotations,
                '$[*]' COLUMNS (
                    selected_text VARCHAR(2000) PATH '$.selected_text',
                    comment VARCHAR(2000) PATH '$.comment',
                    user_name VARCHAR(64) PATH '$.user_name',
                    create_time VARCHAR(32) PATH '$.create_time'
                )
            ) AS ann
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.review_status != 'PENDING'
              AND f.is_deleted = 0
              AND f.annotations IS NOT NULL
              AND JSON_LENGTH(f.annotations) > 0
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            ORDER BY ann.create_time DESC
        """,
        "description": "人工专家反馈报告-改进点摘要列表（从annotations中提取划词评论）",
        "supports_pagination": True,
    },
    "rlhf_feedback_tag_articles": {
        "name": "RLHF报告-反馈词相关文章列表",
        "query": """
            SELECT
                f.id as article_id,
                f.title,
                SUBSTRING(f.content, 1, 200) as content_preview,
                f.created_at as create_time
            FROM rlhf_feedback f
            LEFT JOIN job j ON f.job_id = j.job_id
            WHERE f.review_status != 'PENDING'
              AND f.is_deleted = 0
              AND JSON_CONTAINS(f.issue_tag_ids, CAST({{tag_id}} AS JSON))
              AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
              AND (j.is_deleted IS NULL OR j.is_deleted = 0)
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            ORDER BY f.created_at DESC
        """,
        "description": "根据反馈词（issue_tag_id）获取相关文章列表",
        "supports_pagination": True,
    },
    
    # ==================== 统计学专家组 ====================
    "statistics_expert_stats": {
        "name": "统计学专家组-审核统计",
        "query": """
            SELECT 
                COUNT(*) as total_reviewed_count
            FROM content c
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND JSON_EXTRACT(c.context_list, '$."人设"') IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
        """,
        "description": "统计学专家组审核统计（有人设的文章总数）",
    },
    "statistics_agent_persona_heatmap": {
        "name": "统计学专家组-人群多样性热力图",
        "query": """
            SELECT
                c.agent_code,
                a.agent_name,
                JSON_UNQUOTE(JSON_EXTRACT(c.context_list, '$."人设"')) as persona_name,
                COUNT(*) as content_count
            FROM content c
            LEFT JOIN agent a ON c.agent_code = a.agent_code AND a.is_deleted = 0
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND JSON_EXTRACT(c.context_list, '$."人设"') IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
            GROUP BY c.agent_code, a.agent_name, JSON_UNQUOTE(JSON_EXTRACT(c.context_list, '$."人设"'))
            ORDER BY c.agent_code, content_count DESC
        """,
        "description": "人群多样性热力图数据（横轴Agent，纵轴人设，值为文章数量）",
    },

    # ==================== AI算力成本看板 ====================
    "cost_by_agent": {
        "name": "成本看板-按Agent分布",
        "query": """
            SELECT
                j.agent_code,
                a.agent_name,
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) AS total_cost,
                COUNT(DISTINCT t.job_id) AS job_count,
                COUNT(DISTINCT t.content_id) AS content_count
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            LEFT JOIN agent a ON j.agent_code = a.agent_code AND a.is_deleted = 0
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND j.agent_code IS NOT NULL
              AND a.agent_code IS NOT NULL
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY j.agent_code, a.agent_name, COALESCE(t.currency, 'USD')
            ORDER BY total_cost DESC
        """,
        "description": "按 Agent 粒度的成本分布（用于成本看板扇形图，仅显示未删除的 Agent）",
    },
    "cost_by_job": {
        "name": "成本看板-按Job明细",
        "query": """
            SELECT
                j.job_id,
                j.job_name,
                j.agent_code,
                a.agent_name,
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) AS total_cost,
                COUNT(DISTINCT t.content_id) AS content_count,
                MIN(t.created_at) AS start_time,
                MAX(t.created_at) AS end_time
            FROM expert_call_trace t
            INNER JOIN job j ON t.job_id = j.job_id
            LEFT JOIN agent a ON j.agent_code = a.agent_code AND a.is_deleted = 0
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND a.agent_code IS NOT NULL
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY j.job_id, j.job_name, j.agent_code, a.agent_name, COALESCE(t.currency, 'USD')
            ORDER BY total_cost DESC
        """,
        "description": "按 Job 粒度的成本明细（用于成本看板表格，仅显示未删除 Agent 的 Job）",
        "supports_pagination": True,
    },
    "cost_total_by_currency": {
        "name": "成本看板-总成本汇总",
        "query": """
            SELECT
                COALESCE(t.currency, 'USD') as currency,
                SUM(t.total_cost) AS total_cost,
                COUNT(DISTINCT CASE WHEN a.agent_code IS NOT NULL THEN j.agent_code END) AS agent_count,
                COUNT(DISTINCT t.job_id) AS job_count,
                COUNT(DISTINCT t.content_id) AS content_count
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            LEFT JOIN agent a ON j.agent_code = a.agent_code AND a.is_deleted = 0
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY COALESCE(t.currency, 'USD')
        """,
        "description": "总成本汇总（按币种）",
    },
    
    # ==================== 内容转化漏斗 ====================
    "content_funnel": {
        "name": "内容转化漏斗",
        "query": """
            SELECT
                COUNT(*) as total_count,
                COUNT(CASE WHEN c.is_valid = 1 THEN 1 END) as valid_count,
                COUNT(CASE WHEN c.online_status = 'ONLINE' THEN 1 END) as online_count,
                COUNT(CASE WHEN c.is_used = 1 THEN 1 END) as used_count
            FROM content c
            WHERE c.create_time >= '{{start_date}}' AND c.create_time < '{{end_date}}'
              AND c.is_deleted = 0
              AND c.agent_code IS NOT NULL
              AND (c.tenant_id IS NULL OR {{content_tenant_filter}})
              AND (c.activity_id IS NULL OR {{content_activity_filter}})
              AND ({{content_agent_filter}})
        """,
        "description": "内容转化漏斗统计（文章总数、有效文章数、上线文章数、被使用文章数）",
    },

    # ==================== AIGC生成中心-任务列表 ====================
    "job_task_list": {
        "name": "AIGC生成中心-任务列表",
        "query": """
            SELECT 
                j.job_id,
                j.job_name,
                j.agent_code,
                a.agent_name,
                j.status,
                j.article_count AS target_count,
                COALESCE(stats.content_count, 0) AS content_count,
                stats.first_time AS start_time,
                stats.last_time AS end_time
            FROM job j
            LEFT JOIN agent a ON j.agent_code = a.agent_code
            LEFT JOIN (
                SELECT 
                    sj.job_id,
                    COUNT(DISTINCT sj.content_id) AS content_count,
                    MIN(sj.create_time) AS first_time,
                    MAX(sj.create_time) AS last_time
                FROM sub_job sj
                WHERE sj.is_deleted = 0
                GROUP BY sj.job_id
            ) stats ON j.job_id = stats.job_id
            WHERE j.is_deleted = 0
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
              AND ({{status_filter}})
            ORDER BY j.create_time DESC
        """,
        "description": "AIGC生成中心任务列表（含生成数量和耗时）",
        "supports_pagination": True,
    },
    
    # ==================== 概览统计 ====================
    "dashboard_overview": {
        "name": "Dashboard-概览统计",
        "query": """
            SELECT
                -- 任务统计
                (SELECT COUNT(*) FROM job j WHERE j.create_time >= '{{start_date}}' AND j.create_time < '{{end_date}}'
                    AND j.is_deleted = 0
                    AND ({{tenant_filter}})
                    AND ({{activity_filter}})
                    AND ({{agent_filter}})
                ) as total_jobs,
                -- 内容统计
                (SELECT COUNT(DISTINCT t.content_id) FROM expert_call_trace t
                 LEFT JOIN job j ON t.job_id = j.job_id
                 WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
                    AND t.content_id IS NOT NULL
                    AND (j.is_deleted IS NULL OR j.is_deleted = 0)
                    AND ({{tenant_filter}})
                    AND ({{activity_filter}})
                    AND ({{agent_filter}})
                ) as total_contents,
                -- 总成本 (兼容旧版，直接求和)
                (SELECT COALESCE(SUM(t.total_cost), 0) FROM expert_call_trace t
                 LEFT JOIN job j ON t.job_id = j.job_id
                 WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
                    AND ({{tenant_filter}})
                    AND ({{activity_filter}})
                    AND ({{agent_filter}})
                ) as total_cost,
                -- 多币种明细
                (SELECT GROUP_CONCAT(CONCAT(COALESCE(t.currency, 'USD'), ':', cost) SEPARATOR '|')
                 FROM (
                     SELECT COALESCE(t.currency, 'USD') as currency, SUM(t.total_cost) as cost
                     FROM expert_call_trace t
                     LEFT JOIN job j ON t.job_id = j.job_id
                     WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
                        AND ({{tenant_filter}})
                        AND ({{activity_filter}})
                        AND ({{agent_filter}})
                     GROUP BY COALESCE(t.currency, 'USD')
                 ) t
                ) as total_cost_detail,
                -- 用户采纳率
                (SELECT ROUND(COUNT(CASE WHEN f.adopt_status = 1 THEN 1 END) / NULLIF(COUNT(*), 0) * 100, 2)
                 FROM rlhf_feedback f
                 LEFT JOIN job j ON f.job_id = j.job_id
                 WHERE f.adopt_status != 0
                    AND f.created_at >= '{{start_date}}' AND f.created_at < '{{end_date}}'
                    AND ({{tenant_filter}})
                    AND ({{activity_filter}})
                    AND ({{agent_filter}})
                ) as adopt_rate
        """,
        "description": "Dashboard 概览统计（支持多币种成本明细）",
    },
    "daily_trend": {
        "name": "Dashboard-日趋势",
        "query": """
            SELECT
                DATE(t.created_at) as date,
                COALESCE(t.currency, 'USD') as currency,
                COUNT(DISTINCT t.content_id) as content_count,
                SUM(t.total_cost) as daily_cost,
                AVG(t.duration_ms) as avg_latency_ms
            FROM expert_call_trace t
            LEFT JOIN job j ON t.job_id = j.job_id
            WHERE t.created_at >= '{{start_date}}' AND t.created_at < '{{end_date}}'
              AND ({{tenant_filter}})
              AND ({{activity_filter}})
              AND ({{agent_filter}})
            GROUP BY DATE(t.created_at), COALESCE(t.currency, 'USD')
            ORDER BY date ASC
        """,
        "description": "每日趋势（按日期和币种分组）",
    },
}

# 细粒度的字段级指标定义（用于前端展示和 Tooltip）
METRIC_FIELD_DEFINITIONS = {
    # Dashboard 概览
    "dashboard_overview.total_jobs": {
        "name": "任务总数",
        "description": "选定时间段内创建的任务总数。",
        "category": "Dashboard",
        "unit": "个"
    },
    "dashboard_overview.total_contents": {
        "name": "生成内容数",
        "description": "选定时间段内成功生成的内容总数（去重）。",
        "category": "Dashboard",
        "unit": "篇"
    },
    "dashboard_overview.total_cost": {
        "name": "总成本",
        "description": "选定时间段内所有 Expert 调用产生的总费用。",
        "category": "Dashboard",
        "unit": "$"
    },
    "dashboard_overview.adopt_rate": {
        "name": "采纳率",
        "description": "RLHF 反馈中被用户采纳的内容占比。",
        "category": "Dashboard",
        "unit": "%"
    },
    
    # AG
    "ag_governance_overview.total_checks": {
        "name": "审核总次数",
        "description": "AG 治理模块执行审核的总次数。",
        "category": "AG"
    },
    "ag_governance_overview.total_blocks": {
        "name": "拦截总次数",
        "description": "AG 治理模块判断为不合规并拦截的次数（得分 < 60）。",
        "category": "AG"
    },
    "ag_governance_overview.block_rate": {
        "name": "拦截率",
        "description": "拦截次数占总审核次数的比例。",
        "category": "AG",
        "unit": "%"
    },
    
    # RLHF
    "rlhf_user_like_rate": {
        "name": "用户喜欢率",
        "description": "用户标记为 '喜欢' 的内容比例。",
        "category": "RLHF",
        "unit": "%"
    },
    "rlhf_adopt_rate": {
        "name": "采纳率",
        "description": "用户最终采纳并使用的内容比例。",
        "category": "RLHF",
        "unit": "%"
    },
    "rlhf_edit_after_adopt_rate": {
        "name": "采纳后修改率",
        "description": "内容被采纳后，用户又进行了二次修改的比例（反映生成质量细节）。",
        "category": "RLHF",
        "unit": "%"
    }
}
