/**
 * AI Dashboard 专家组评分流程动画
 *
 * 管理评分粒子动画、分数桶、专家激活状态等
 */

import type {
  ActiveExperts,
  CriticExpertScoreDistribution,
  QualityDimension,
  ScoreBucketsData,
  ScoreParticle,
  ScoringExpertMeta,
} from '../types';

import { onUnmounted, ref } from 'vue';

import { getScoreRange } from '../constants';

// ==================== 类型定义 ====================

/** 评分专家元数据映射 */
type ScoringExpertMetaMap = Record<string, ScoringExpertMeta>;

/** 专家区间分布数据 */
type ExpertRangeDistribution = Record<string, Record<string, number>>;

// ==================== Composable ====================

export function useScoringFlowAnimation(
  scoringExperts: { value: ScoringExpertMeta[] },
  scoringExpertMetaMap: { value: ScoringExpertMetaMap },
  criticQualityDimensions: { value: QualityDimension[] },
) {
  // 粒子 ID 计数器
  let particleIdCounter = 0;

  // 动画定时器
  let flowAnimationTimer: null | ReturnType<typeof setInterval> = null;

  // 分数桶数据
  const scoreBucketsData = ref<ScoreBucketsData>({
    r5: 0,
    r4: 0,
    r3: 0,
    r2: 0,
    r1: 0,
  });

  // 当前活跃的专家
  const activeExperts = ref<ActiveExperts>({});

  // 粒子列表
  const scoreParticles = ref<ScoreParticle[]>([]);

  // 当前高亮的雷达图维度
  const highlightedRadarDimension = ref<null | string>(null);

  // 专家区间分布数据
  const expertRangeDistribution = ref<ExpertRangeDistribution>({
    r5: {},
    r4: {},
    r3: {},
    r2: {},
    r1: {},
  });

  /** 初始化专家激活状态 */
  function initActiveExperts(): void {
    activeExperts.value = Object.fromEntries(
      scoringExperts.value.map((expert) => [expert.expert_func, false]),
    );
  }

  /** 生成一个评分粒子 */
  function createScoreParticle(expertKey: string): void {
    const expert = scoringExpertMetaMap.value[expertKey];
    if (!expert) {
      console.warn('[AI-Dashboard] 未找到专家:', expertKey);
      return;
    }

    // 获取该专家的真实平均分数
    const qualityData = criticQualityDimensions.value.find(
      (item) => item.expert_func === expertKey,
    );

    // 确保 avg_score 是有效数字
    const rawScore = qualityData?.avg_score;
    let avgScore = 70;
    if (typeof rawScore === 'number' && !Number.isNaN(rawScore)) {
      avgScore = rawScore;
    } else if (typeof rawScore === 'string' && rawScore !== '') {
      avgScore = Number(rawScore);
    }

    // 基于平均分生成随机分数（在平均分附近浮动）
    const variance = 15;
    const score = Math.max(
      0,
      Math.min(100, avgScore + (Math.random() * variance * 2 - variance)),
    );

    const targetRange = getScoreRange(score);
    if (!targetRange) return;

    // 激活专家动画效果
    activeExperts.value[expertKey] = true;
    highlightedRadarDimension.value = expertKey;

    setTimeout(() => {
      activeExperts.value[expertKey] = false;
    }, 600);

    setTimeout(() => {
      if (highlightedRadarDimension.value === expertKey) {
        highlightedRadarDimension.value = null;
      }
    }, 1200);

    // 创建粒子
    const particleId = ++particleIdCounter;
    const particle: ScoreParticle = {
      id: particleId,
      expertKey,
      startX: 0,
      startY: 0,
      endX: 0,
      endY: 0,
      color: expert.color,
      targetBucketId: targetRange.id,
      score: Math.round(score),
    };

    scoreParticles.value.push(particle);

    // 粒子动画完成后更新分数桶
    setTimeout(() => {
      scoreParticles.value = scoreParticles.value.filter(
        (p) => p.id !== particleId,
      );
      scoreBucketsData.value[targetRange.id]++;
    }, 800);
  }

  /** 启动评分流程动画 */
  function start(): void {
    // 先停止可能存在的旧定时器
    stop();

    // 初始化分数桶数据
    initScoreBucketsFromRealData();

    flowAnimationTimer = setInterval(() => {
      const expertKeys = scoringExperts.value.map(
        (expert) => expert.expert_func,
      );
      if (expertKeys.length === 0) return;
      const shuffledExperts = [...expertKeys].toSorted(
        () => 0.5 - Math.random(),
      );

      // 只取第一个专家，减少粒子数量
      const firstExpert = shuffledExperts[0];
      if (firstExpert) {
        createScoreParticle(firstExpert);
      }
    }, 3000);
  }

  /** 停止评分流程动画 */
  function stop(): void {
    if (flowAnimationTimer) {
      clearInterval(flowAnimationTimer);
      flowAnimationTimer = null;
    }
  }

  /** 基于真实数据初始化分数桶 */
  function initScoreBucketsFromRealData(): void {
    const scores = criticQualityDimensions.value.map(
      (item) => item.avg_score || 0,
    );
    const avgScore =
      scores.length > 0
        ? scores.reduce((a, b) => a + b, 0) / scores.length
        : 70;

    // 基于平均分生成合理的分布
    if (avgScore >= 80) {
      scoreBucketsData.value = { r5: 45, r4: 30, r3: 15, r2: 7, r1: 3 };
    } else if (avgScore >= 70) {
      scoreBucketsData.value = { r5: 25, r4: 40, r3: 20, r2: 10, r1: 5 };
    } else if (avgScore >= 60) {
      scoreBucketsData.value = { r5: 15, r4: 30, r3: 35, r2: 15, r1: 5 };
    } else {
      scoreBucketsData.value = { r5: 10, r4: 20, r3: 30, r2: 25, r1: 15 };
    }
  }

  /** 获取某专家在某分值区间的占比百分比 */
  function getExpertRangePercent(rangeId: string, expertKey: string): number {
    const rangeData = expertRangeDistribution.value[rangeId];
    if (!rangeData) return 16.67;

    const total = Object.values(rangeData).reduce((a, b) => a + b, 0);
    if (total === 0) return 16.67;

    return ((rangeData[expertKey] || 0) / total) * 100;
  }

  /** 从后端指标数据更新评分专家分数区间分布 */
  function updateExpertRangeDistribution(
    data: CriticExpertScoreDistribution[],
  ): void {
    if (!data || data.length === 0) return;

    const newDistribution: ExpertRangeDistribution = {
      r5: {},
      r4: {},
      r3: {},
      r2: {},
      r1: {},
    };

    const expertKeys =
      scoringExperts.value.length > 0
        ? scoringExperts.value.map((expert) => expert.expert_func)
        : [...new Set(data.map((item) => item.expert_func))];

    expertKeys.forEach((expertKey) => {
      ['r5', 'r4', 'r3', 'r2', 'r1'].forEach((rangeId) => {
        newDistribution[rangeId][expertKey] = 0;
      });
    });

    data.forEach((item) => {
      const { expert_func, score_range, content_count } = item;
      if (expert_func && score_range && expertKeys.includes(expert_func)) {
        newDistribution[score_range][expert_func] = content_count;
      }
    });

    expertRangeDistribution.value = newDistribution;
  }

  /** 手动触发专家评分 */
  function triggerExpertScore(expertKey: string): void {
    createScoreParticle(expertKey);
  }

  // 组件卸载时清理
  onUnmounted(() => {
    stop();
  });

  return {
    // 状态
    scoreBucketsData,
    activeExperts,
    scoreParticles,
    highlightedRadarDimension,
    expertRangeDistribution,

    // 方法
    initActiveExperts,
    start,
    stop,
    getExpertRangePercent,
    updateExpertRangeDistribution,
    triggerExpertScore,
  };
}
