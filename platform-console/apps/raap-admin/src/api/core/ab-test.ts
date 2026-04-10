/**
 * AB测试相关API
 * 统一支持 Expert 维度和 Agent/Job 维度
 */
import { requestClient } from '#/api/request';

export namespace ABTestApi {
  // ========== 类型定义 ==========

  /** 测试类型 */
  export type TestType = 'AGENT_JOB' | 'EXPERT_CONFIG';

  /** 测试状态 */
  export type TestStatus =
    | 'analyzing'
    | 'completed'
    | 'failed'
    | 'pending'
    | 'running';

  /** 对比组信息 */
  export interface ABTestGroup {
    group_name: string;
    description?: string;
    config_snapshot?: Record<string, unknown>;
  }

  /** AB测试指标 */
  export interface ABTestMetrics {
    avg_time_ms: number;
    avg_tokens: number;
    avg_cost: number;
    success_rate: number;
    run_count: number;
    avg_score?: number;
    pass_rate?: number;
  }

  /** Critic 评分明细 */
  export interface CriticScoreDetail {
    expert_func: string;
    expert_config_code: string;
    model_code?: string;
    total_count: number;
    avg_score: number;
    pass_count: number;
    fail_count: number;
    pass_rate: number;
  }

  /** 组指标详情 */
  export interface GroupMetricsDetail {
    group_name: string;
    description?: string;
    job_id?: string;
    metrics: ABTestMetrics;
    sample_ids: Array<number | string>;
    /** Critic 评分明细（Job 类型时有值） */
    critic_details?: CriticScoreDetail[];
  }

  // ========== 请求类型 ==========

  /** 创建 Expert 维度 AB 测试请求 */
  export interface CreateExpertTestRequest {
    test_name: string;
    /** 调试历史关联，key 为组名，value 为 debug_history_id 数组 */
    debug_history_ids: Record<string, number[]>;
    /** 对比组信息（至少2个组） */
    groups: ABTestGroup[];
    remark?: string;
  }

  /** 创建 Job 维度 AB 测试请求 */
  export interface CreateJobTestRequest {
    test_name: string;
    /** Job 关联，key 为组名，value 为 job_id */
    job_ids: Record<string, string>;
    /** 对比组信息（至少2个组） */
    groups: ABTestGroup[];
    remark?: string;
  }

  /** 更新 AB 测试请求 */
  export interface UpdateTestRequest {
    test_name?: string;
    remark?: string;
  }

  /** 添加调试历史请求 */
  export interface AddDebugHistoryRequest {
    group_name: string;
    debug_history_ids: number[];
  }

  // ========== 执行模式请求（保留原有流程）==========

  /** AB测试组配置（用于执行模式） */
  export interface ABTestGroupConfig {
    group_name: string;
    config_code: string;
    config_name?: string;
    variables?: Array<Record<string, unknown>>;
    model_code?: string;
    llm_config?: Record<string, unknown>;
  }

  /** 创建并执行 Expert AB 测试请求 */
  export interface ExecuteExpertTestRequest {
    test_name: string;
    configs: ABTestGroupConfig[];
    traffic_allocation: Record<string, number>;
    test_content?: string;
    execution_count?: number;
    auto_execute?: boolean;
    remark?: string;
  }

  /** 执行响应 */
  export interface ABTestExecuteResponse {
    test_id: string;
    status: string;
    message: string;
    total_runs: number;
    completed_runs: number;
  }

  // ========== 响应类型 ==========

  /** AB测试响应 */
  export interface ABTestResponse {
    id: number;
    test_id: string;
    test_name: string;
    test_type: TestType;
    /** Expert 维度：调试历史关联 */
    debug_history_ids?: Record<string, number[]>;
    /** Job 维度：Job 关联 */
    job_ids?: Record<string, string>;
    /** 对比组信息 */
    groups: ABTestGroup[];
    /** 各组聚合指标 */
    metrics?: Record<string, ABTestMetrics>;
    winner?: string;
    recommendation?: string;
    status: TestStatus;
    start_time?: string;
    end_time?: string;
    create_time: string;
    update_time?: string;
    created_by?: string;
    remark?: string;
  }

  /** AB测试列表响应 */
  export interface ABTestListResponse {
    items: ABTestResponse[];
    total: number;
    page: number;
    page_size: number;
  }

  /** AB测试详情响应 */
  export interface ABTestDetailResponse {
    test: ABTestResponse;
    group_details: GroupMetricsDetail[];
    comparison: {
      recommendation?: string;
      winner?: string;
    };
  }

  /** 分析结果响应 */
  export interface ABTestAnalyzeResponse {
    test_id: string;
    status: string;
    message: string;
    metrics?: Record<string, ABTestMetrics>;
    winner?: string;
    recommendation?: string;
  }

  // ========== API 方法 ==========

  // ========== 执行模式（保留原有流程）==========

  /**
   * 创建并执行 Expert AB 测试
   * - 创建测试，debug_history_ids 初始为空
   * - 后台执行测试，每完成一个 debug 就追加 debug_history_id
   * - 全部执行完成后自动分析
   */
  export async function executeExpertTest(data: ExecuteExpertTestRequest) {
    return requestClient.post<ABTestExecuteResponse>(
      '/v1/ab-tests/execute',
      data,
    );
  }

  // ========== 关联模式 ==========

  /**
   * 创建 Expert 维度 AB 测试
   * 关联已有的调试历史记录进行对比分析
   */
  export async function createExpertTest(data: CreateExpertTestRequest) {
    return requestClient.post<ABTestResponse>('/v1/ab-tests/expert', data);
  }

  /**
   * 创建 Job 维度 AB 测试
   * 关联多个 Job 进行对比分析
   */
  export async function createJobTest(data: CreateJobTestRequest) {
    return requestClient.post<ABTestResponse>('/v1/ab-tests/job', data);
  }

  /**
   * 向 Expert 测试添加调试历史
   * 支持同一组多次执行的场景
   */
  export async function addDebugHistories(
    testId: string,
    data: AddDebugHistoryRequest,
  ) {
    return requestClient.post<ABTestResponse>(
      `/v1/ab-tests/${testId}/debug-histories`,
      data,
    );
  }

  /**
   * 分析测试
   * 聚合关联数据的指标，生成对比结论和推荐
   */
  export async function analyzeTest(testId: string) {
    return requestClient.post<ABTestAnalyzeResponse>(
      `/v1/ab-tests/${testId}/analyze`,
    );
  }

  /**
   * 获取AB测试列表
   */
  export async function listABTests(params?: {
    page?: number;
    page_size?: number;
    status?: TestStatus;
    test_type?: TestType;
  }) {
    return requestClient.get<ABTestListResponse>('/v1/ab-tests', {
      params,
    });
  }

  /**
   * 获取AB测试详情
   */
  export async function getABTestDetail(testId: string) {
    return requestClient.get<ABTestDetailResponse>(`/v1/ab-tests/${testId}`);
  }

  /**
   * 更新AB测试
   */
  export async function updateABTest(testId: string, data: UpdateTestRequest) {
    return requestClient.put<ABTestResponse>(`/v1/ab-tests/${testId}`, data);
  }

  /**
   * 删除AB测试
   */
  export async function deleteABTest(testId: string) {
    return requestClient.delete(`/v1/ab-tests/${testId}`);
  }
}
