<script setup lang="ts">
import type {
  CalibrationRecordCreate,
  CalibrationRecordResponse,
} from '#/api/core/calibration';
import type { ContentCriticSummary } from '#/api/core/job-execution';
import type { RLHFApi } from '#/api/core/rlhf';

import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Button, Input, message, Modal } from 'ant-design-vue';

import {
  createCalibrationRecordsApi,
  getCalibrationRecordsApi,
} from '#/api/core/calibration';
import { getRLHFListApi } from '#/api/core/rlhf';

type HumanJudgement = 'correct' | 'incorrect' | null;

interface CalibrationArticle {
  id: number;
  title: string;
  content: string;
  ai_passed: boolean | null;
  human_judgement: HumanJudgement;
  remark: string;
}

interface RLHFListResponse {
  items?: RLHFApi.RLHFFeedback[];
  total?: number;
}

const articlesLoading = ref(false);

const route = useRoute();
const router = useRouter();

const rlhf_articles = ref<CalibrationArticle[]>([]);

type CalibrationExpertType = 'BAN' | 'CRITIC';

interface CalibrationExpertPayload {
  name: string;
  expert_code: string;
  expert_type: CalibrationExpertType;
  expert_func: string;
}

interface CalibrationArticlePayload {
  id: number;
  job_id?: string;
  sub_job_id?: string;
  content_id: string;
  title: string;
  content: string;
  critic_summary: ContentCriticSummary | null;
}

interface CalibrationPayload {
  experts: CalibrationExpertPayload[];
  articles: CalibrationArticlePayload[];
  source: 'article_pool';
  created_at: string;
}

type HumanScoreValue = boolean | null | number;

interface CalibrationWorkbenchArticle {
  id: number;
  job_id?: string;
  sub_job_id?: string;
  content_id: string;
  title: string;
  content: string;
  critic_summary: ContentCriticSummary | null;
  human_scores: Record<string, HumanScoreValue>;
  remark: string;
}

const calibration_experts = ref<CalibrationExpertPayload[]>([]);
const calibration_all_articles = ref<CalibrationWorkbenchArticle[]>([]);
const calibration_task_id = ref<null | number>(null);
const calibration_records_loading = ref(false);
const calibration_saving = ref(false);
const BATCH_SIZE = 15;
const current_batch_index = ref(0);

const has_payload = computed(() => calibration_experts.value.length > 0);
const header_expert_name = computed(() => {
  const expert = calibration_experts.value[0];
  if (!expert) return '校准';
  return expert.name || expert.expert_code;
});
const primary_expert = computed(() => calibration_experts.value[0] ?? null);
const current_batch_articles = computed(() => {
  const start = current_batch_index.value * BATCH_SIZE;
  return calibration_all_articles.value.slice(start, start + BATCH_SIZE);
});
const batch_total_count = computed(() => {
  if (has_payload.value) {
    return current_batch_articles.value.length;
  }
  return rlhf_articles.value.length;
});
const is_article_scored = (article: CalibrationWorkbenchArticle) =>
  calibration_experts.value.every((expert) => {
    const value = article.human_scores[expert.expert_code];
    if (expert.expert_type === 'BAN') {
      return typeof value === 'boolean';
    }
    return typeof value === 'number';
  });
const batch_remaining_count = computed(() => {
  if (!has_payload.value) return batch_total_count.value;
  return current_batch_articles.value.filter((item) => !is_article_scored(item))
    .length;
});

const set_ai_result = (item: CalibrationArticle, value: boolean) => {
  item.ai_passed = value;
};

const set_human_result = (item: CalibrationArticle, value: HumanJudgement) => {
  item.human_judgement = value;
};

const is_remark_required = (item: CalibrationArticle) =>
  item.human_judgement === 'incorrect';

const is_record_remark_required = (
  article: CalibrationWorkbenchArticle,
  expert: CalibrationExpertPayload,
) => {
  const human_value = article.human_scores[expert.expert_code] ?? null;
  if (expert.expert_type === 'BAN') {
    return human_value === false;
  }
  const ai_score = get_ai_critic_score(article, expert);
  if (typeof ai_score !== 'number' || typeof human_value !== 'number') {
    return false;
  }
  return Math.abs(ai_score - human_value) > 40;
};

const build_human_score_map = (experts: CalibrationExpertPayload[]) => {
  const map: Record<string, HumanScoreValue> = {};
  experts.forEach((expert) => {
    map[expert.expert_code] = null;
  });
  return map;
};

const find_expert_score = (
  article: CalibrationWorkbenchArticle,
  expert: CalibrationExpertPayload,
) => {
  const scores = article.critic_summary?.scores ?? [];
  return scores.find((item) => item.expert_func === expert.expert_func);
};

const get_ai_ban_result = (
  article: CalibrationWorkbenchArticle,
  expert: CalibrationExpertPayload,
) => {
  const score_item = find_expert_score(article, expert);
  if (typeof score_item?.passed === 'boolean') {
    return score_item.passed;
  }
  return null;
};

const get_ai_critic_score = (
  article: CalibrationWorkbenchArticle,
  expert: CalibrationExpertPayload,
) => {
  const score_item = find_expert_score(article, expert);
  if (typeof score_item?.score === 'number') {
    return score_item.score;
  }
  return null;
};

const set_human_ban_result = (
  article: CalibrationWorkbenchArticle,
  expert: CalibrationExpertPayload,
  value: boolean,
) => {
  article.human_scores[expert.expert_code] = value;
};

const set_human_critic_score = (
  article: CalibrationWorkbenchArticle,
  expert: CalibrationExpertPayload,
  value: number,
) => {
  article.human_scores[expert.expert_code] = value;
};

const get_critic_score_class = (value: null | number) => {
  if (typeof value !== 'number') {
    return 'ai-score-value--default';
  }
  if (value > 80) {
    return 'ai-score-value--high';
  }
  if (value < 60) {
    return 'ai-score-value--low';
  }
  return 'ai-score-value--default';
};

const build_calibration_records = (): CalibrationRecordCreate[] => {
  const task_id = calibration_task_id.value;
  if (!task_id) {
    return [];
  }
  const records: CalibrationRecordCreate[] = [];
  current_batch_articles.value.forEach((article) => {
    if (!article.content_id) return;
    const normalized_remark = article.remark.trim() || undefined;
    calibration_experts.value.forEach((expert) => {
      const score_value = article.human_scores[expert.expert_code];
      if (expert.expert_type === 'BAN') {
        if (typeof score_value !== 'boolean') return;
        records.push({
          calibration_task_id: task_id,
          content_row_id: article.id,
          content_id: article.content_id,
          job_id: article.job_id,
          sub_job_id: article.sub_job_id,
          expert_config_code: expert.expert_code,
          expert_func: expert.expert_func,
          expert_type: expert.expert_type,
          human_passed: score_value,
          remark: normalized_remark,
        });
        return;
      }
      if (typeof score_value !== 'number') return;
      records.push({
        calibration_task_id: task_id,
        content_row_id: article.id,
        content_id: article.content_id,
        job_id: article.job_id,
        sub_job_id: article.sub_job_id,
        expert_config_code: expert.expert_code,
        expert_func: expert.expert_func,
        expert_type: expert.expert_type,
        human_score_value: score_value,
        remark: normalized_remark,
      });
    });
  });
  return records;
};

const apply_calibration_records = (records: CalibrationRecordResponse[]) => {
  const article_map = new Map<string, CalibrationWorkbenchArticle>();
  current_batch_articles.value.forEach((article) => {
    article_map.set(article.content_id, article);
  });
  const filled = new Set<string>();
  records.forEach((record) => {
    const article = article_map.get(record.content_id);
    if (!article) return;
    const key = `${record.content_id}:${record.expert_config_code}`;
    if (filled.has(key)) return;
    if (record.expert_type === 'BAN') {
      if (typeof record.human_passed === 'boolean') {
        article.human_scores[record.expert_config_code] = record.human_passed;
      }
    } else if (
      record.expert_type === 'CRITIC' &&
      typeof record.human_score_value === 'number'
    ) {
      article.human_scores[record.expert_config_code] =
        record.human_score_value;
    }
    if (!article.remark && record.remark) {
      article.remark = record.remark;
    }
    filled.add(key);
  });
};

const load_calibration_records = async () => {
  if (!calibration_task_id.value) {
    return;
  }
  const content_ids = current_batch_articles.value
    .map((item) => item.content_id)
    .filter(Boolean);
  const expert_config_codes = calibration_experts.value.map(
    (expert) => expert.expert_code,
  );
  if (content_ids.length === 0 || expert_config_codes.length === 0) return;

  calibration_records_loading.value = true;
  try {
    const records =
      (await getCalibrationRecordsApi({
        calibration_task_id: calibration_task_id.value,
        content_ids,
        expert_config_codes,
      })) ?? [];
    apply_calibration_records(records);
  } catch (error) {
    console.error('获取校准记录失败:', error);
    message.error('获取校准记录失败');
  } finally {
    calibration_records_loading.value = false;
  }
};

const handle_save_calibration = async () => {
  // 校验备注必填
  if (primary_expert.value) {
    for (const article of current_batch_articles.value) {
      if (!is_article_scored(article)) continue;
      if (
        is_record_remark_required(article, primary_expert.value) &&
        (!article.remark || article.remark.trim() === '')
      ) {
        message.warning(
          `文章《${article.title}》的备注为必填项，请填写后再提交`,
        );
        return;
      }
    }
  }

  const records = build_calibration_records();
  if (records.length === 0) {
    message.warning('请先完成评分后再保存');
    return;
  }
  calibration_saving.value = true;
  try {
    await createCalibrationRecordsApi(records);
    message.success('校准记录已保存');
    const next_index = current_batch_index.value + 1;
    const next_start = next_index * BATCH_SIZE;
    if (next_start < calibration_all_articles.value.length) {
      current_batch_index.value = next_index;
      await load_calibration_records();
      // 滚动到顶部
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      await load_calibration_records();
      // 显示完成弹窗
      show_completion_modal();
    }
  } catch (error) {
    console.error('保存校准记录失败:', error);
    message.error('保存校准记录失败');
  } finally {
    calibration_saving.value = false;
  }
};

const show_completion_modal = () => {
  Modal.info({
    title: '校准完成',
    content: '所有文章校准完成,请重新勾选文章进行校准。',
    okText: '返回到文章池',
    onOk: () => {
      return_to_article_pool();
    },
  });
};

const return_to_article_pool = () => {
  const expert = calibration_experts.value[0];
  if (!expert) {
    router.push({ path: '/analysis/article-pool' });
    return;
  }
  router.push({
    path: '/analysis/article-pool',
    query: {
      expert_config_code: expert.expert_code,
      expert_config_name: expert.name,
    },
  });
};

const parse_calibration_payload = (raw: string): CalibrationPayload | null => {
  try {
    const parsed = JSON.parse(raw) as CalibrationPayload;
    if (!Array.isArray(parsed?.experts) || !Array.isArray(parsed?.articles)) {
      return null;
    }
    return parsed;
  } catch (error) {
    console.error('解析校准数据失败:', error);
    return null;
  }
};

const init_payload_data = () => {
  const key = route.query.calibration_key;
  if (typeof key !== 'string' || !key) return false;
  const task_id_raw = route.query.calibration_task_id;
  const task_id =
    typeof task_id_raw === 'string' ? Number(task_id_raw) : Number(task_id_raw);
  if (!task_id || Number.isNaN(task_id)) {
    message.error('校准任务缺失，请重新进入');
    return false;
  }
  const raw = sessionStorage.getItem(key);
  if (!raw) return false;
  const payload = parse_calibration_payload(raw);
  if (!payload) return false;
  calibration_task_id.value = task_id;
  calibration_experts.value = payload.experts;
  calibration_all_articles.value = payload.articles.map((item) => ({
    id: item.id,
    job_id: item.job_id,
    sub_job_id: item.sub_job_id,
    content_id: item.content_id,
    title: item.title,
    content: item.content,
    critic_summary: item.critic_summary,
    remark: '',
    human_scores: build_human_score_map(payload.experts),
  }));
  current_batch_index.value = 0;
  return true;
};

const content_panel_width = ref<null | number>(null);
const MIN_CONTENT_WIDTH = 420;
const MAX_CONTENT_WIDTH = 960;

const clamp_content_width = (value: number) =>
  Math.min(MAX_CONTENT_WIDTH, Math.max(MIN_CONTENT_WIDTH, value));

const handle_resize_start = (event: MouseEvent) => {
  event.preventDefault();
  const panel = (event.currentTarget as HTMLElement | null)?.parentElement;
  const start_width = panel?.getBoundingClientRect().width ?? 0;
  content_panel_width.value = start_width;
  const start_x = event.clientX;

  const handle_move = (move_event: MouseEvent) => {
    const next_width = start_width + (move_event.clientX - start_x);
    content_panel_width.value = clamp_content_width(next_width);
  };

  const handle_up = () => {
    window.removeEventListener('mousemove', handle_move);
    window.removeEventListener('mouseup', handle_up);
  };

  window.addEventListener('mousemove', handle_move);
  window.addEventListener('mouseup', handle_up);
};

const buildArticle = (item: RLHFApi.RLHFFeedback): CalibrationArticle => ({
  id: item.id,
  title: item.modified_title || item.title || '',
  content: item.modified_content || item.content || '',
  ai_passed: null,
  human_judgement: null,
  remark: item.inspection_comment ?? '',
});

const loadArticles = async () => {
  articlesLoading.value = true;
  try {
    const params: { page: number; page_size: number } = {
      page: 1,
      page_size: 20,
    };
    const res = (await getRLHFListApi(params)) as RLHFListResponse;
    const items = res.items ?? [];
    rlhf_articles.value = items.map((item) => buildArticle(item));
  } catch (error) {
    console.error('获取校准文章失败:', error);
    rlhf_articles.value = [];
    message.error('获取校准文章失败');
  } finally {
    articlesLoading.value = false;
  }
};

onMounted(async () => {
  if (init_payload_data()) {
    await load_calibration_records();
    return;
  }
  loadArticles();
});
</script>

<template>
  <div class="calibration-workbench">
    <div class="filter-bar">
      <div class="filter-title">
        <div class="title-group">
          <span class="title-text">{{ header_expert_name }} · 校准工作台</span>
          <span class="subtitle-text">用于对AI专家判断结果进行人工校准</span>
        </div>
        <div class="batch-count">
          本批次剩余：{{ batch_remaining_count }} / {{ batch_total_count }}
        </div>
      </div>
    </div>

    <div class="workbench-list">
      <template v-if="has_payload">
        <div
          v-for="item in current_batch_articles"
          :key="item.id"
          class="workbench-card"
        >
          <div
            class="content-panel"
            :style="
              content_panel_width
                ? {
                    width: `${content_panel_width}px`,
                    flex: `0 0 ${content_panel_width}px`,
                  }
                : undefined
            "
          >
            <div class="field-block">
              <div class="field-label">标题</div>
              <div class="field-value">
                <span>{{ item.title }}</span>
                <span class="length-hint">({{ item.title.length }}/20)</span>
              </div>
            </div>
            <div class="field-block">
              <div class="field-label">正文</div>
              <div class="field-value content-text">
                {{ item.content }}
              </div>
              <div class="word-count">{{ item.content.length }}字</div>
            </div>
            <div
              class="resize-handle"
              role="separator"
              aria-label="调整文章内容宽度"
              @mousedown="handle_resize_start"
            ></div>
          </div>

          <div class="score-panel">
            <div
              v-for="expert in calibration_experts"
              :key="expert.expert_code"
              class="score-section"
            >
              <div class="ai-score-card">
                <template v-if="expert.expert_type === 'BAN'">
                  <div class="ai-score-title">{{ expert.name }}专家评分</div>
                  <div class="ai-score-content ai-score-content--split">
                    <span class="ai-score-value">判断结果：</span>
                    <span
                      v-if="get_ai_ban_result(item, expert) === true"
                      class="ai-score-value ai-score-value--ban ai-score-value--high"
                    >
                      通过
                    </span>
                    <span
                      v-else-if="get_ai_ban_result(item, expert) === false"
                      class="ai-score-value ai-score-value--ban ai-score-value--low"
                    >
                      不通过
                    </span>
                    <span v-else class="text-muted">-</span>
                  </div>
                </template>
                <template v-else>
                  <div class="ai-score-title">AI专家评分</div>
                  <div class="ai-score-content ai-score-content--split">
                    <span class="ai-score-value">AI专家评分</span>
                    <span
                      class="ai-score-value ai-score-value--large"
                      :class="
                        get_critic_score_class(
                          get_ai_critic_score(item, expert),
                        )
                      "
                    >
                      {{ get_ai_critic_score(item, expert) ?? '-' }}
                    </span>
                  </div>
                </template>
              </div>
              <div class="score-row">
                <div class="score-label required">人工专家评分</div>
                <div class="score-content">
                  <template v-if="expert.expert_type === 'BAN'">
                    <div class="rating-group">
                      <button
                        type="button"
                        class="rating-button"
                        :class="{
                          'rating-button--active':
                            item.human_scores[expert.expert_code] === true,
                        }"
                        @click="set_human_ban_result(item, expert, true)"
                      >
                        AI正确
                      </button>
                      <button
                        type="button"
                        class="rating-button"
                        :class="{
                          'rating-button--active rating-button--fail':
                            item.human_scores[expert.expert_code] === false,
                        }"
                        @click="set_human_ban_result(item, expert, false)"
                      >
                        AI不正确
                      </button>
                    </div>
                  </template>
                  <template v-else>
                    <div class="rating-group">
                      <button
                        v-for="score in [0, 20, 40, 60, 80, 100]"
                        :key="score"
                        type="button"
                        class="rating-button"
                        :class="{
                          'rating-button--active':
                            item.human_scores[expert.expert_code] === score,
                        }"
                        @click="set_human_critic_score(item, expert, score)"
                      >
                        {{ score }}
                      </button>
                    </div>
                  </template>
                </div>
              </div>
            </div>

            <div
              v-if="
                primary_expert &&
                is_record_remark_required(item, primary_expert)
              "
              class="score-section remark-section"
            >
              <div class="section-title required">备注说明</div>
              <Input.TextArea
                v-model:value="item.remark"
                :rows="5"
                placeholder="请输入校准理由，用于说明AI判断不正确的原因"
              />
              <div class="remark-hint required">
                AI 判断不正确或与人工评分差值超过 40 时为必填
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div
          v-for="item in rlhf_articles"
          :key="item.id"
          class="workbench-card"
        >
          <div
            class="content-panel"
            :style="
              content_panel_width
                ? {
                    width: `${content_panel_width}px`,
                    flex: `0 0 ${content_panel_width}px`,
                  }
                : undefined
            "
          >
            <div class="panel-title">文章内容</div>
            <div class="field-block">
              <div class="field-label">标题</div>
              <div class="field-value">
                <span>{{ item.title }}</span>
                <span class="length-hint">({{ item.title.length }}/20)</span>
              </div>
            </div>
            <div class="field-block">
              <div class="field-label">正文</div>
              <div class="field-value content-text">
                {{ item.content }}
              </div>
              <div class="word-count">{{ item.content.length }}字</div>
            </div>
            <div
              class="resize-handle"
              role="separator"
              aria-label="调整文章内容宽度"
              @mousedown="handle_resize_start"
            ></div>
          </div>

          <div class="score-panel">
            <div class="score-section">
              <div class="section-title">AI专家评分</div>
              <div class="button-group">
                <Button
                  type="primary"
                  :ghost="item.ai_passed !== true"
                  @click="set_ai_result(item, true)"
                >
                  通过
                </Button>
                <Button
                  type="primary"
                  :ghost="item.ai_passed !== false"
                  @click="set_ai_result(item, false)"
                >
                  不通过
                </Button>
              </div>
            </div>

            <div class="score-section">
              <div class="section-title">人工专家评分</div>
              <div class="button-group">
                <Button
                  type="primary"
                  :ghost="item.human_judgement !== 'correct'"
                  @click="set_human_result(item, 'correct')"
                >
                  AI正确
                </Button>
                <Button
                  type="primary"
                  :ghost="item.human_judgement !== 'incorrect'"
                  @click="set_human_result(item, 'incorrect')"
                >
                  AI不正确
                </Button>
              </div>
            </div>

            <div class="score-section remark-section">
              <div class="section-title">备注</div>
              <Input.TextArea
                v-model:value="item.remark"
                :rows="5"
                placeholder="请填写备注"
              />
              <div
                class="remark-hint"
                :class="{ required: is_remark_required(item) }"
              >
                跟 AI 意见不一致时，备注必填
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div v-if="has_payload" class="batch-submit-bar">
      <Button
        type="primary"
        :loading="calibration_saving"
        @click="handle_save_calibration"
      >
        提交本批次并加载下一批
      </Button>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 1024px) {
  .workbench-card {
    flex-direction: column;
  }

  .content-panel {
    width: 100% !important;
  }

  .resize-handle {
    display: none;
  }
}

.calibration-workbench {
  min-height: 100%;
  padding: 12px 24px 32px;
  color: hsl(var(--foreground));
  background: hsl(var(--muted));
}

/* 顶部标题 + 筛选区域（与专家校准中心一致） */
.filter-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 12px 24px 16px;
  margin: -12px -24px 24px;
  background: hsl(var(--background) / 92%);
  border-bottom: 1px solid hsl(var(--border));
  box-shadow:
    0 12px 24px hsl(var(--background) / 30%),
    0 1px 0 hsl(var(--border));
  backdrop-filter: blur(8px);
}

.filter-title {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 12px;
}

.title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-actions {
  margin-left: 0;
}

.title-text {
  font-size: 18px;
  font-weight: 700;
  color: transparent;
  background-image: linear-gradient(
    90deg,
    hsl(var(--primary)),
    hsl(var(--success))
  );
  background-clip: text;
}

.subtitle-text {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.update-time {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.batch-count {
  margin-left: auto;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.workbench-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 96px;
}

.batch-submit-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  z-index: 200;
  display: flex;
  justify-content: center;
  width: 100%;
  padding: 16px 24px 20px;
  background: hsl(var(--background) / 92%);
  border-top: 1px solid hsl(var(--border));
  box-shadow:
    0 -12px 24px hsl(var(--background) / 30%),
    0 -1px 0 hsl(var(--border));
  backdrop-filter: blur(8px);
}

.workbench-card {
  display: flex;
  gap: 24px;
  padding: 20px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  box-shadow:
    0 10px 24px hsl(var(--background) / 35%),
    0 2px 6px hsl(var(--border) / 40%);
}

.content-panel,
.score-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.content-panel {
  position: relative;
  flex: 1 1 0;
  min-width: 320px;
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.score-panel {
  flex: 1 1 0;
  min-width: 280px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.field-value {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
}

.field-value > span:first-child {
  font-weight: 600;
}

.length-hint {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.content-text {
  line-height: 1.7;
  color: hsl(var(--foreground));
}

.word-count {
  margin-top: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-align: right;
}

.resize-handle {
  position: absolute;
  top: 12px;
  right: -6px;
  bottom: 12px;
  width: 12px;
  cursor: col-resize;
}

.resize-handle::before {
  position: absolute;
  top: 0;
  left: 50%;
  width: 2px;
  height: 100%;
  content: '';
  background: hsl(var(--border));
  border-radius: 999px;
  transform: translateX(-50%);
}

.score-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ai-score-card {
  padding: 12px 16px;
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.ai-score-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.ai-score-content {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ai-score-content--split {
  justify-content: space-between;
}

.ai-score-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.ai-score-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  font-size: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
}

.ai-score-value {
  font-size: 20px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.ai-score-value--large {
  font-size: 36px;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.ai-score-value--ban {
  font-size: 28px;
  font-weight: 700;
}

.ai-score-value--default {
  color: hsl(var(--primary));
}

.ai-score-value--high {
  color: hsl(var(--success));
}

.ai-score-value--low {
  color: hsl(var(--destructive));
}

.ai-score-pass {
  color: hsl(var(--success));
  background: hsl(var(--success) / 15%);
  border-color: hsl(var(--success));
}

.ai-score-fail {
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 15%);
  border-color: hsl(var(--destructive));
}

.ai-score-neutral {
  color: hsl(var(--foreground));
  background: hsl(var(--background));
}

.section-title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
}

.score-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.score-label {
  min-width: 100px;
  color: hsl(var(--muted-foreground));
}

.score-label.required::after,
.section-title.required::after {
  margin-left: 4px;
  color: hsl(var(--destructive));
  content: '*';
}

.score-content {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.expert-title {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.expert-type-badge,
.expert-code-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
}

.ai-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  font-size: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
}

.ai-pill-pass {
  color: hsl(var(--success));
  background: hsl(var(--success) / 15%);
  border-color: hsl(var(--success));
}

.ai-pill-fail {
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 15%);
  border-color: hsl(var(--destructive));
}

.ai-score {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.rating-group {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.rating-button {
  padding: 14px 28px;
  font-size: 18px;
  color: hsl(var(--foreground));
  cursor: pointer;
  background: hsl(var(--background));
  border: none;
  border-right: 1px solid hsl(var(--border));
  transition:
    background 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}

.rating-button:last-child {
  border-right: none;
}

.rating-button:hover {
  background: hsl(var(--muted));
}

.rating-button--active {
  color: hsl(var(--success));
  background: hsl(var(--success) / 12%);
  box-shadow: inset 0 0 0 1px hsl(var(--success));
}

.rating-button--fail.rating-button--active {
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 15%);
  box-shadow: inset 0 0 0 1px hsl(var(--destructive));
}

.button-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.remark-section :deep(.ant-input) {
  color: hsl(var(--foreground));
  background: hsl(var(--background-deep));
  border-color: hsl(var(--border));
}

.remark-hint {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.remark-hint.required {
  color: hsl(var(--destructive));
}
</style>
