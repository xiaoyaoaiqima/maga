/**
 * Expert Debug 工具函数
 */

import type { DebugResponse, ModelRoute } from './types';

/**
 * 格式化执行时间
 * 超过 1 秒显示为秒（保留 2 位小数），否则显示毫秒
 */
export function formatExecutionTime(ms: number): string {
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)}s`;
  }
  return `${ms}ms`;
}

/**
 * 健壮的 Token 提取逻辑
 */
export function getEffectiveTokenUsage(result: DebugResponse) {
  const usage = {
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
  };

  if (!result) return usage;

  // 1. 优先检查最外层
  if (result.token_usage) {
    usage.prompt_tokens = result.token_usage.prompt_tokens || 0;
    usage.completion_tokens = result.token_usage.completion_tokens || 0;
    usage.total_tokens = result.token_usage.total_tokens || 0;
  }

  // 2. 如果外层为 0，检查 expert_total_output 内部
  if (usage.total_tokens === 0 && result.expert_total_output) {
    const out = result.expert_total_output as any;
    const nestedUsage = out.token_usage || out.usage;
    if (nestedUsage) {
      usage.prompt_tokens =
        nestedUsage.prompt_tokens || nestedUsage.input_tokens || 0;
      usage.completion_tokens =
        nestedUsage.completion_tokens || nestedUsage.output_tokens || 0;
      usage.total_tokens =
        nestedUsage.total_tokens ||
        usage.prompt_tokens + usage.completion_tokens;
    } else if (
      out.input_tokens !== undefined ||
      out.output_tokens !== undefined
    ) {
      usage.prompt_tokens = out.input_tokens || 0;
      usage.completion_tokens = out.output_tokens || 0;
      usage.total_tokens = usage.prompt_tokens + usage.completion_tokens;
    }
  }

  // 3. 尝试从 output_content 解析 (如果输出是 JSON 字符串且包含 usage)
  if (usage.total_tokens === 0 && result.output_content) {
    try {
      if (result.output_content.trim().startsWith('{')) {
        const parsed = JSON.parse(result.output_content);
        const jsonUsage =
          parsed.token_usage ||
          parsed.usage ||
          (parsed.input_tokens === undefined ? null : parsed);
        if (jsonUsage) {
          usage.prompt_tokens =
            jsonUsage.prompt_tokens || jsonUsage.input_tokens || 0;
          usage.completion_tokens =
            jsonUsage.completion_tokens || jsonUsage.output_tokens || 0;
          usage.total_tokens =
            jsonUsage.total_tokens ||
            usage.prompt_tokens + usage.completion_tokens;
        }
      }
    } catch {
      // 忽略解析错误
    }
  }

  return usage;
}

/**
 * 提取要展示的正文内容
 * 处理结果为 JSON 或 Python 字典的情况
 */
export function getDisplayContent(result: DebugResponse | null): string {
  if (!result) return '';

  // 1. 优先从 expert_total_output 提取已知的内容字段
  if (result.expert_total_output) {
    const out = result.expert_total_output as any;
    const content =
      out.generated_content ??
      out.content ??
      out.text ??
      out.answer ??
      out.result;
    if (content && typeof content === 'string' && content.trim()) {
      return content;
    }
  }

  // 2. 检查 output_content
  const rawContent = result.output_content || '';
  if (!rawContent) return '';

  const trimmed = rawContent.trim();
  // 识别是否可能是 JSON 或 Python 字典格式
  if (
    (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
    (trimmed.startsWith('[') && trimmed.endsWith(']'))
  ) {
    try {
      let parsed;
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        // 尝试兼容 Python 风格
        const normalized = trimmed
          .replaceAll("'", '"')
          .replaceAll('True', 'true')
          .replaceAll('False', 'false')
          .replaceAll('None', 'null');
        parsed = JSON.parse(normalized);
      }

      const content =
        parsed.generated_content ??
        parsed.content ??
        parsed.text ??
        parsed.answer ??
        parsed.result;
      if (content && typeof content === 'string' && content.trim()) {
        return content;
      }
    } catch {
      // 解析或提取失败，维持原样
    }
  }

  return rawContent;
}

/**
 * 计算预估费用 (USD)
 */
export function calculateCost(
  modelCode: string,
  modelRoutes: ModelRoute[],
  result?: DebugResponse,
): string {
  if (!modelCode) return '0.00';

  // 增强匹配逻辑：去掉常见的厂商前缀尝试匹配
  let route = modelRoutes.find((r) => r.model_code === modelCode);
  if (!route) {
    const cleanCode = modelCode.split('-').slice(1).join('-');
    if (cleanCode) {
      route = modelRoutes.find((r) => r.model_code === cleanCode);
    }
  }

  if (!route) return '0.00';

  const usage = result
    ? getEffectiveTokenUsage(result)
    : { prompt_tokens: 0, completion_tokens: 0 };
  const inputRate = Number.parseFloat(route.cost_per_1k_input || '0');
  const outputRate = Number.parseFloat(route.cost_per_1k_output || '0');

  const cost =
    (usage.prompt_tokens / 1000) * inputRate +
    (usage.completion_tokens / 1000) * outputRate;
  return cost.toFixed(6);
}

/**
 * 生成高亮问题词的 HTML
 */
export function highlightProblems(text: string, problems: string[]): string {
  if (!text || problems.length === 0) return text;

  let result = text;
  for (const problem of problems) {
    if (problem && problem.trim()) {
      const escaped = problem.replaceAll(
        /[.*+?^${}()|[\]\\]/g,
        String.raw`\$&`,
      );
      const regex = new RegExp(escaped, 'gi');
      result = result.replace(
        regex,
        `<mark class="problem-highlight">${problem}</mark>`,
      );
    }
  }
  return result;
}

/**
 * 判断是否有变量差异
 */
export function hasVariableDiff(current: any, baseline: any): boolean {
  if (!current || !baseline) return false;
  return current.plugin_config_snapshot?.some((p: any) => {
    const basePlugin = baseline.plugin_config_snapshot?.find(
      (bp: any) => bp.plugin_code === p.plugin_code,
    );
    if (!basePlugin) return true;
    return Object.keys(p.variable_mapping).some(
      (k) => p.variable_mapping[k] !== basePlugin.variable_mapping[k],
    );
  });
}

/**
 * 复制到剪贴板
 */
export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}
