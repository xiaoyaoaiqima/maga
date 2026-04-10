import { requestClient } from '#/api/request';

/** RLHF 反馈模型 */
export namespace RLHFApi {
  export interface RLHFFeedback {
    id: number;
    job_id: string;
    sub_job_id: string;
    content_id: string;
    trace_id?: string;
    title?: string;
    content?: string;
    modified_title?: string;
    modified_content?: string;
    ge_expert_code?: string;
    model_code?: string;
    like_status: -1 | 0 | 1;
    like_reason?: string;
    like_user_name?: string;
    adopt_status: -1 | 0 | 1 | 2;
    adopt_reason?: string;
    discard_reason_type?: string;
    improvement_suggestion?: string;
    content_score: number;
    model_score: number;
    issue_tag_ids?: number[];
    custom_issue_tags?: string[];
    is_locked: 0 | 1;
    lock_user_name?: string;
    lock_expire_time?: string;
    review_status:
      | 'COMPLETED'
      | 'IN_INSPECTION'
      | 'IN_PROGRESS'
      | 'INSPECTION_FAILED'
      | 'INSPECTION_PASSED'
      | 'PENDING';
    created_at: string;
    updated_at: string;
    // 审核人信息
    review_user_id?: string;
    review_user_name?: string;
    review_time?: string;
    // 抽检结果相关 (附属字段)
    inspection_comment?: string;
    inspection_user_id?: string;
    inspection_user_name?: string;
    inspection_time?: string;
    // 上下文变量 (从 Content 表关联获取)
    context_list?: Record<string, string>;
    // 划词评论
    annotations?: any[];
  }

  export interface RLHFIssueTag {
    id: number;
    tag_code: string;
    tag_name: string;
    tag_category?: string;
    description?: string;
    enabled: 0 | 1;
    sort_order: number;
  }

  export interface RLHFStatsSummary {
    total_count: number;
    pending_count: number;
    completed_count: number;
    like_rate: number;
    adopt_rate: number;
    avg_content_score: number;
  }
}

/** 获取内容列表 */
export function getRLHFListApi(params: any) {
  return requestClient.get<any>('/v1/rlhf/contents', { params });
}

/** 获取内容详情 */
export function getRLHFDetailApi(id: number) {
  return requestClient.get<RLHFApi.RLHFFeedback>(`/v1/rlhf/contents/${id}`);
}

/** 随机获取待审核内容 */
export function getRandomRLHFContentsApi(count = 1) {
  return requestClient.get<RLHFApi.RLHFFeedback[]>('/v1/rlhf/contents/random', {
    params: { count },
  });
}

/** 锁定内容 */
export function lockContentApi(id: number) {
  return requestClient.post(`/v1/rlhf/contents/${id}/lock`);
}

/** 解锁内容 */
export function unlockContentApi(id: number) {
  return requestClient.post(`/v1/rlhf/contents/${id}/unlock`);
}

/** 解锁当前用户锁定的所有内容 */
export function unlockAllMyContentsApi() {
  return requestClient.post<{ success: boolean; unlocked_count: number }>(
    '/v1/rlhf/contents/unlock-all',
  );
}

/** 批量锁定内容 */
export function batchLockContentsApi(ids: number[]) {
  return requestClient.post<{
    auto_unlocked_count?: number;
    auto_unlocked_ids?: number[];
    failed_count: number;
    failed_ids: number[];
    message?: string;
    success_count: number;
    success_ids: number[];
  }>('/v1/rlhf/contents/batch-lock', { ids });
}

/** 批量解锁内容 */
export function batchUnlockContentsApi(ids: number[]) {
  return requestClient.post<{
    failed_count: number;
    failed_ids: number[];
    success_count: number;
    success_ids: number[];
  }>('/v1/rlhf/contents/batch-unlock', { ids });
}

/** 心跳续锁 - 延长锁定时间 */
export function renewLocksApi(ids: number[]) {
  return requestClient.post<{
    new_expire_time: string;
    renewed_count: number;
    success: boolean;
  }>('/v1/rlhf/contents/renew-locks', { ids });
}

/** 喜欢/不喜欢 */
export function likeContentApi(
  id: number,
  data: { improvement_suggestion?: string; reason: string; status: -1 | 1 },
) {
  return requestClient.post(`/v1/rlhf/contents/${id}/like`, data);
}

/** 采纳/不采纳/废弃 */
export function adoptContentApi(
  id: number,
  data: {
    discard_reason_type?: string;
    improvement_suggestion?: string;
    reason: string;
    status: -1 | 1 | 2;
  },
) {
  return requestClient.post(`/v1/rlhf/contents/${id}/adopt`, data);
}

/** 评分 */
export function scoreContentApi(
  id: number,
  data: {
    content_score: number;
    custom_issue_tags?: string[];
    issue_tag_ids?: number[];
    model_score: number;
    modified_content?: string;
    modified_title?: string;
  },
) {
  return requestClient.post(`/v1/rlhf/contents/${id}/score`, data);
}

/** 抽检 */
export function inspectionContentApi(
  id: number,
  data: {
    comment?: string;
    issue_tag_names?: string[];
    result: 'FAILED' | 'PASSED';
  },
) {
  return requestClient.post<RLHFApi.RLHFFeedback>(
    `/v1/rlhf/contents/${id}/inspection`,
    data,
  );
}

/** AI 建议标签 */
export function suggestRLHFTagsApi(id: number, data: { comment?: string }) {
  return requestClient.post<{ tags: string[] }>(
    `/v1/rlhf/contents/${id}/suggest-tags`,
    data,
  );
}

/** AI 总结意见 - 根据原文和划词评论生成修改意见 */
export function summarizeRLHFCommentApi(
  id: number,
  data: { model_code?: string } = {},
) {
  return requestClient.post<{ comment: string }>(
    `/v1/rlhf/contents/${id}/summarize-comment`,
    data,
  );
}

/** 更新内容（包括 AI 意见和标签） */
export function updateContentApi(
  id: number,
  data: {
    annotations?: unknown[];
    improvement_suggestion?: string;
    issue_tag_names?: string[];
    modified_content?: string;
    modified_title?: string;
  },
) {
  return requestClient.put(`/v1/rlhf/contents/${id}`, data);
}

/** 原文精修 - 保存精修后的标题和内容 */
export function refineContentApi(
  id: number,
  data: {
    refined_content?: string;
    refined_title?: string;
  },
) {
  return requestClient.post<RLHFApi.RLHFFeedback>(
    `/v1/rlhf/contents/${id}/refine`,
    data,
  );
}

/** 获取历史 */
export function getRLHFHistoryApi(id: number) {
  return requestClient.get<any[]>(`/v1/rlhf/contents/${id}/history`);
}

/** 获取标签列表 */
export function getIssueTagsApi() {
  return requestClient.get<RLHFApi.RLHFIssueTag[]>('/v1/rlhf/issue-tags');
}

/** 创建标签 */
export function createIssueTagApi(data: any) {
  return requestClient.post('/v1/rlhf/issue-tags', data);
}

/** 更新标签 */
export function updateIssueTagApi(id: number, data: any) {
  return requestClient.put(`/v1/rlhf/issue-tags/${id}`, data);
}

/** 删除标签 */
export function deleteIssueTagApi(id: number) {
  return requestClient.delete(`/v1/rlhf/issue-tags/${id}`);
}

/** 获取统计摘要 */
export function getRLHFStatsSummaryApi() {
  return requestClient.get<RLHFApi.RLHFStatsSummary>('/v1/rlhf/stats/summary');
}

/** 获取状态选项 */
export function getReviewStatusOptionsApi() {
  return requestClient.get<Array<{ label: string; value: string }>>(
    '/v1/rlhf/review-status-options',
  );
}

/** 获取审核人列表（用于下拉筛选） */
export function getReviewersApi() {
  return requestClient.get<Array<{ label: string; value: string }>>(
    '/v1/rlhf/reviewers',
  );
}

/** 更新审核状态（喜欢/不喜欢） */
export function updateReviewStatusApi(
  id: number,
  data: { comment?: string; issue_tag_names?: string[]; review_status: string },
) {
  return requestClient.put(`/v1/rlhf/contents/${id}/review-status`, data);
}
