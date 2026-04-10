/**
 * Expert Debug 模块类型定义
 */

import type { ExpertDebugApi } from '#/api/core/expert-debug';
import type { LLMApi } from '#/api/core/llm';

/** Expert 配置 */
export interface ExpertConfig {
  id: number;
  expert_config_code: string;
  expert_config_name: string;
  expert_type: string;
  model_code: string;
  model_config: Record<string, any>;
  prompt_template: string;
  plugin_config: Record<string, any>;
  enabled: boolean;
}

/** 对比组配置 */
export interface CompareGroup {
  name: string;
  variables: Array<{
    plugin_code: string;
    variable_mapping: Record<string, string>;
  }>;
  modelOverride: {
    enabled: boolean;
    max_tokens: number;
    model_code: string;
    temperature: number;
  };
}

/** 持久化状态 V1 */
export interface PersistedDebugStateV1 {
  selected_expert: string;
  input_content: string;
  use_prompt_override: boolean;
  prompt_override: string;
  edited_segments: Record<number, string>;
  last_debug_history_id: null | number;
  is_compare_mode: boolean;
  compare_groups: CompareGroup[];
  active_group_index: number;
}

/** 插件颜色配置 */
export interface PluginColor {
  bg: string;
  border: string;
  text: string;
}

/** 批量评分表单 */
export interface BatchEvalForm {
  test_set_code: string;
  max_count: number;
  article_concurrency: number;
}

/** 导出常用的 API 类型别名 */
export type DebugResponse = ExpertDebugApi.DebugResponse;
export type DebugRequest = ExpertDebugApi.DebugRequest;
export type PluginSegment = ExpertDebugApi.PluginSegment;
export type ExpertPluginVariablesResponse =
  ExpertDebugApi.ExpertPluginVariablesResponse;
export type ModelRoute = LLMApi.ModelRoute;
