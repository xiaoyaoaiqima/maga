<script setup lang="ts">
import type { Dayjs } from 'dayjs';

import type { EchartsUIType } from '@vben/plugins/echarts';

import type { CriticScoreApi } from '#/api/core/critic-scores';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';
import { usePreferences } from '@vben/preferences';

import * as Antd from 'ant-design-vue';
import * as DayjsLib from 'dayjs';
import gsap from 'gsap';
import * as THREE from 'three';
import SpriteText from 'three-spritetext';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';

import {
  getActivitySimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import {
  getCriticDimensionHeatmapApi,
  getCriticDistributionApi,
  getCriticProblemContextTopApi,
  getCriticReasonWordCloudApi,
  getCriticScatterDataApi,
  getCriticSummaryApi,
  getCriticTrendApi,
  listCriticDatasetsApi,
  listExpertConfigOptionsApi,
} from '#/api/core/critic-scores';
import { getJobListApi } from '#/api/core/job';
import MetricHelp from '#/components/MetricHelp/index.vue';

const loading = ref(false);
const { isDark } = usePreferences();

const dayjs = ((DayjsLib as any).default ?? (DayjsLib as any)) as any;
const { Button, Col, DatePicker, message, Row, Select, Space, Spin, Tooltip } =
  Antd as any;

const RangePicker = DatePicker.RangePicker;

const dateRange = ref<[Dayjs, Dayjs]>([dayjs().subtract(29, 'day'), dayjs()]);

const filters = ref({
  source_type: 'job' as CriticScoreApi.SourceType,
  tenant_id: undefined as number | undefined,
  activity_id: undefined as number | undefined,
  job_id: '' as string,
  dataset_code: '' as string,
  expert_config_code: '' as string,
});

// 下拉选项
const tenantOptions = ref<Array<{ label: string; value: number }>>([]);
// 保存完整租户列表（用于查找 tenant_code）
const allTenants = ref<
  Array<{ id: number; tenant_code: string; tenant_name: string }>
>([]);
const activityOptions = ref<Array<{ label: string; value: number }>>([]);
const allActivities = ref<
  Array<{ activity_name: string; id: number; tenant_id: number }>
>([]);
const jobOptions = ref<Array<{ label: string; value: string }>>([]);
const allJobs = ref<
  Array<{
    activity_id?: null | number;
    job_id: string;
    job_name: string;
    tenant_id?: null | number;
  }>
>([]);
const datasetOptions = ref<Array<{ label: string; value: string }>>([]);

const heatmap3dContainerRef = ref<HTMLDivElement | null>(null);

// expert_config 选项（从后端动态获取）
const expertConfigOptions = ref<
  Array<{
    expert_func: string;
    expert_type: string;
    label: string;
    value: string;
  }>
>([]);

// 根据 tenant_id 获取 tenant_code
function getTenantCode(tenantId: number | undefined): string | undefined {
  if (!tenantId) return undefined;
  const tenant = allTenants.value.find((t) => t.id === tenantId);
  return tenant?.tenant_code;
}

// 根据选中的 expert_config_code 获取对应的 expert_func
function getSelectedExpertFunc(): string | undefined {
  const code = filters.value.expert_config_code;
  if (!code) return undefined;
  const option = expertConfigOptions.value.find((x) => x.value === code);
  return option?.expert_func;
}

// 获取 expert_config 列表（支持按 tenant_code 过滤，只获取 CRITIC 类型）
async function fetchExpertConfigOptions() {
  try {
    const tenantCode = getTenantCode(filters.value.tenant_id);
    const items = await listExpertConfigOptionsApi({
      tenant_code: tenantCode,
      expert_type: 'CRITIC', // 只获取 CRITIC 类型的维度
    });
    expertConfigOptions.value = (items || []).map((x) => ({
      label: x.expert_config_name,
      value: x.expert_config_code,
      expert_type: x.expert_type,
      expert_func: x.expert_func,
    }));
  } catch {
    expertConfigOptions.value = [];
  }
}

const showJobFilters = computed(() => filters.value.source_type === 'job');
const showEvalRunFilters = computed(
  () => filters.value.source_type === 'eval_run',
);

const summary = ref<CriticScoreApi.Summary>({
  avg_duration_ms: 0,
  avg_score: 0,
  max_score: 0,
  min_score: 0,
  pass_rate: 0,
  passed_count: 0,
  total_count: 0,
});

// BAN 类型的汇总数据（合规通过率）
const banSummaryData = ref<CriticScoreApi.Summary>({
  avg_duration_ms: 0,
  avg_score: 0,
  max_score: 0,
  min_score: 0,
  pass_rate: 0,
  passed_count: 0,
  total_count: 0,
});

const compliance = ref({
  // 不合规范 + 违禁词 合并为「内容合规」
  contentCompliance: { total: 0, passed: 0 },
  unreasonable: { total: 0, passed: 0 },
  counterproductive: { total: 0, passed: 0 },
});

const trend = ref<CriticScoreApi.TrendItem[]>([]);
const distribution = ref<CriticScoreApi.DistributionItem[]>([]);
const reasonWordCloud = ref<CriticScoreApi.ReasonWordCloudItem[]>([]);
const topContexts = ref<CriticScoreApi.ProblemContextTopItem[]>([]);
const heatmapData = ref<CriticScoreApi.DimensionHeatmapResponse>({
  dimensions: [],
  score_ranges: [],
  data: [],
});
const scatterData = ref<CriticScoreApi.ScatterDataItem[]>([]);

const trendChartRef = ref<EchartsUIType>();
const distChartRef = ref<EchartsUIType>();
const ctxChartRef = ref<EchartsUIType>();
const heatmapChartRef = ref<EchartsUIType>();
const scatterChartRef = ref<EchartsUIType>();

const { renderEcharts: renderTrend } = useEcharts(trendChartRef);
const { renderEcharts: renderDist } = useEcharts(distChartRef);
const { renderEcharts: renderCtx } = useEcharts(ctxChartRef);
const { renderEcharts: renderHeatmap } = useEcharts(heatmapChartRef);
const { renderEcharts: renderScatter } = useEcharts(scatterChartRef);

const startDate = computed(() => dateRange.value[0].format('YYYY-MM-DD'));
const endDate = computed(() => dateRange.value[1].format('YYYY-MM-DD'));

// 统一配色（与整体前端风格一致，使用 Ant Design 色系，响应主题切换）
const colors = computed(() => ({
  primary: '#1890ff', // 蓝色
  success: '#52c41a', // 绿色
  warning: '#faad14', // 黄色
  danger: '#f5222d', // 红色
  purple: '#722ed1', // 紫色
  cyan: '#13c2c2', // 青色
  pink: '#eb2f96', // 粉色
  gradient1: ['#1890ff', '#722ed1'], // 蓝紫渐变
  gradient2: ['#eb2f96', '#f5222d'], // 粉红渐变
  gradient3: ['#13c2c2', '#1890ff'], // 青蓝渐变
  gradient4: ['#52c41a', '#13c2c2'], // 绿青渐变
  // 主题相关颜色
  background: isDark.value ? '#0a0a0f' : '#ffffff',
  cardBg: isDark.value ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)',
  textPrimary: isDark.value ? '#e2e8f0' : '#1f2937',
  textSecondary: isDark.value ? '#94a3b8' : '#6b7280',
  border: isDark.value ? 'rgba(24, 144, 255, 0.3)' : 'rgba(24, 144, 255, 0.2)',
}));

function formatRate(numerator: number, denominator: number): string {
  if (!denominator) return '0.0%';
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

// ==================== 3D 维度×分数（Three.js） ====================
type ParticleSystem = {
  base_x: number;
  base_z: number;
  max_height: number;
  points: THREE.Points;
  radius: number;
  velocities: Float32Array;
};

type Heatmap3DContext = {
  animation_id: null | number;
  auto_rotate_enabled: boolean;
  bloom_pass: UnrealBloomPass;
  camera: THREE.PerspectiveCamera;
  clock: THREE.Clock;
  composer: EffectComposer;
  controls: OrbitControls;
  halos_group: THREE.Group;
  hover_mesh: null | THREE.Mesh;
  labels_group: THREE.Group;
  max_count: number;
  particle_systems: ParticleSystem[];
  particles_group: THREE.Group;
  pillars_group: THREE.Group;
  raycaster: THREE.Raycaster;
  renderer: THREE.WebGLRenderer;
  resize_observer: ResizeObserver;
  resume_rotate_timer: null | ReturnType<typeof setTimeout>;
  root_el: HTMLDivElement;
  scene: THREE.Scene;
  tooltip_sprite: any;
  user_interacting: boolean;
};

let heatmap3d_ctx: Heatmap3DContext | null = null;

// 3D 热力图调色板（暗色模式）
const heatmap3d_palette_dark = [
  '#1890ff', // 0-9 蓝色（主色）
  '#40a9ff', // 10-19 浅蓝
  '#73d13d', // 20-29 青绿
  '#52c41a', // 30-39 绿色
  '#a0d911', // 40-49 青柠
  '#fadb14', // 50-59 黄色
  '#faad14', // 60-69 橙黄
  '#fa8c16', // 70-79 橙色
  '#f5222d', // 80-89 红色
  '#722ed1', // 90-100 紫色（高亮）
];

// 3D 热力图调色板（亮色模式 - 更饱和更深）
const heatmap3d_palette_light = [
  '#0050b3', // 0-9 深蓝
  '#096dd9', // 10-19 蓝色
  '#237804', // 20-29 深绿
  '#389e0d', // 30-39 绿色
  '#7cb305', // 40-49 青柠
  '#d48806', // 50-59 深黄
  '#d46b08', // 60-69 深橙
  '#cf1322', // 70-79 深红
  '#a8071a', // 80-89 暗红
  '#531dab', // 90-100 深紫
];

// 根据主题获取调色板
function getHeatmap3dPalette(): string[] {
  return isDark.value ? heatmap3d_palette_dark : heatmap3d_palette_light;
}

function is_webgl_supported(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(
      canvas.getContext('webgl') || canvas.getContext('experimental-webgl'),
    );
  } catch {
    return false;
  }
}

function hex_to_rgb(hex: string): { b: number; g: number; r: number } {
  const h = hex.replace('#', '');
  const n = Number.parseInt(
    h.length === 3 ? [...h].map((c) => c + c).join('') : h,
    16,
  );
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function color_from_palette(t: number): THREE.Color {
  const palette = getHeatmap3dPalette();
  const clamped = Math.max(0, Math.min(1, t));
  const idx = clamped * (palette.length - 1);
  const i0 = Math.floor(idx);
  const i1 = Math.min(i0 + 1, palette.length - 1);
  const frac = idx - i0;
  const c0 = hex_to_rgb(palette[i0]!);
  const c1 = hex_to_rgb(palette[i1]!);
  return new THREE.Color(
    lerp(c0.r, c1.r, frac) / 255,
    lerp(c0.g, c1.g, frac) / 255,
    lerp(c0.b, c1.b, frac) / 255,
  );
}

function dispose_heatmap3d(): void {
  if (!heatmap3d_ctx) return;
  const ctx = heatmap3d_ctx;
  if (ctx.animation_id) cancelAnimationFrame(ctx.animation_id);
  if (ctx.resume_rotate_timer) clearTimeout(ctx.resume_rotate_timer);
  ctx.resize_observer.disconnect();
  ctx.root_el.removeEventListener('mousemove', on_heatmap3d_mousemove);
  ctx.root_el.removeEventListener('mouseleave', on_heatmap3d_mouseleave);

  // 清理各组
  clear_group(ctx.pillars_group);
  clear_group(ctx.particles_group);
  clear_group(ctx.halos_group);
  clear_group(ctx.labels_group);
  ctx.particle_systems.length = 0;

  // 清理 three 对象
  ctx.scene.traverse((obj: THREE.Object3D) => {
    const any_obj = obj as any;
    if (any_obj.geometry) any_obj.geometry.dispose?.();
    if (any_obj.material) {
      if (Array.isArray(any_obj.material))
        any_obj.material.forEach((m: any) => m?.dispose?.());
      else any_obj.material.dispose?.();
    }
  });
  ctx.composer.dispose?.();
  ctx.controls.dispose();
  ctx.renderer.dispose();
  ctx.renderer.domElement.remove();
  heatmap3d_ctx = null;
}

function init_heatmap3d(): void {
  const root_el = heatmap3dContainerRef.value;
  if (!root_el) return;

  if (!is_webgl_supported()) {
    message.warning('当前环境不支持 WebGL，3D 光束塔无法显示');
    return;
  }

  dispose_heatmap3d();

  root_el.style.position = 'relative';
  root_el.innerHTML = '';

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ReinhardToneMapping;
  renderer.toneMappingExposure = 1.2;
  // 注意：updateStyle 必须为 true，否则 canvas 只会用默认 300x150 的 CSS 尺寸
  renderer.setSize(root_el.clientWidth, root_el.clientHeight, true);
  renderer.domElement.style.width = '100%';
  renderer.domElement.style.height = '100%';
  renderer.domElement.style.display = 'block';
  root_el.append(renderer.domElement);

  const scene = new THREE.Scene();
  // 根据主题设置背景色（亮色模式用浅灰蓝，增强对比度）
  scene.background = new THREE.Color(isDark.value ? 0x0a_0a_0f : 0xe8_ef_f5);

  const camera = new THREE.PerspectiveCamera(
    45,
    Math.max(root_el.clientWidth, 1) / Math.max(root_el.clientHeight, 1),
    0.1,
    2000,
  );
  camera.position.set(10, 10, 14);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.rotateSpeed = 0.7;
  controls.zoomSpeed = 0.9;
  controls.panSpeed = 0.6;
  // 自动旋转
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5; // 约 10s 一圈

  // Bloom 后处理
  const composer = new EffectComposer(renderer);
  const render_pass = new RenderPass(scene, camera);
  composer.addPass(render_pass);
  // 亮色模式下降低 bloom 强度（防止过曝）
  const bloomStrength = isDark.value ? 0.8 : 0.3;
  const bloomRadius = isDark.value ? 0.4 : 0.2;
  const bloomThreshold = isDark.value ? 0.6 : 0.8;
  const bloom_pass = new UnrealBloomPass(
    new THREE.Vector2(root_el.clientWidth, root_el.clientHeight),
    bloomStrength,
    bloomRadius,
    bloomThreshold,
  );
  composer.addPass(bloom_pass);

  // 灯光（亮色模式下增强亮度）
  const ambientIntensity = isDark.value ? 0.5 : 1.2;
  const dirLightIntensity = isDark.value ? 0.8 : 1.5;
  const sideLightIntensity = isDark.value ? 0.3 : 0.6;
  scene.add(new THREE.AmbientLight(0xff_ff_ff, ambientIntensity));
  const dir_light = new THREE.DirectionalLight(0xff_ff_ff, dirLightIntensity);
  dir_light.position.set(10, 18, 8);
  scene.add(dir_light);
  // 补一盏侧光增加立体感（使用主色蓝）
  const side_light = new THREE.DirectionalLight(0x18_90_ff, sideLightIntensity);
  side_light.position.set(-10, 10, -5);
  scene.add(side_light);

  // 地面网格（提升空间感）- 根据主题调整颜色（亮色模式用更深的线条）
  const gridColor1 = isDark.value ? 0x18_90_ff : 0x40_a9_ff;
  const gridColor2 = isDark.value ? 0x1e_29_3b : 0xb0_c4_de;
  const grid = new THREE.GridHelper(40, 40, gridColor1, gridColor2);
  (grid.material as any).opacity = isDark.value ? 0.18 : 0.5;
  (grid.material as any).transparent = true;
  scene.add(grid);

  // 光束塔相关组
  const pillars_group = new THREE.Group();
  scene.add(pillars_group);

  const particles_group = new THREE.Group();
  scene.add(particles_group);

  const halos_group = new THREE.Group();
  scene.add(halos_group);

  const labels_group = new THREE.Group();
  scene.add(labels_group);

  // 3D tooltip sprite（初始隐藏，响应主题）
  const tooltipTextColor = isDark.value ? '#f1f5f9' : '#1f2937';
  const tooltipBgColor = isDark.value
    ? 'rgba(15, 23, 42, 0.85)'
    : 'rgba(255, 255, 255, 0.95)';
  const tooltip_sprite = new SpriteText('', 0.28, tooltipTextColor) as any;
  tooltip_sprite.backgroundColor = tooltipBgColor;
  tooltip_sprite.padding = 0.2;
  tooltip_sprite.borderRadius = 0.2;
  tooltip_sprite.fontWeight = '400';
  tooltip_sprite.visible = false;
  scene.add(tooltip_sprite);

  const raycaster = new THREE.Raycaster();
  const clock = new THREE.Clock();

  const resize_observer = new ResizeObserver(() => {
    if (!heatmap3d_ctx) return;
    const w = Math.max(root_el.clientWidth, 1);
    const h = Math.max(root_el.clientHeight, 1);
    heatmap3d_ctx.renderer.setSize(w, h, true);
    heatmap3d_ctx.composer.setSize(w, h);
    heatmap3d_ctx.bloom_pass.resolution.set(w, h);
    heatmap3d_ctx.renderer.domElement.style.width = '100%';
    heatmap3d_ctx.renderer.domElement.style.height = '100%';
    heatmap3d_ctx.camera.aspect = w / h;
    heatmap3d_ctx.camera.updateProjectionMatrix();
  });
  resize_observer.observe(root_el);

  heatmap3d_ctx = {
    animation_id: null,
    camera,
    controls,
    raycaster,
    renderer,
    scene,
    root_el,
    pillars_group,
    particles_group,
    halos_group,
    labels_group,
    tooltip_sprite,
    hover_mesh: null,
    particle_systems: [],
    resize_observer,
    composer,
    bloom_pass,
    auto_rotate_enabled: true,
    user_interacting: false,
    resume_rotate_timer: null,
    max_count: 1,
    clock,
  };

  // 用户介入暂停自动旋转
  controls.addEventListener('start', on_user_rotate_start);
  controls.addEventListener('end', on_user_rotate_end);

  root_el.addEventListener('mousemove', on_heatmap3d_mousemove);
  root_el.addEventListener('mouseleave', on_heatmap3d_mouseleave);

  rebuild_heatmap3d_bars();
  tick_heatmap3d();
}

function on_user_rotate_start(): void {
  if (!heatmap3d_ctx) return;
  heatmap3d_ctx.user_interacting = true;
  heatmap3d_ctx.controls.autoRotate = false;
  if (heatmap3d_ctx.resume_rotate_timer) {
    clearTimeout(heatmap3d_ctx.resume_rotate_timer);
    heatmap3d_ctx.resume_rotate_timer = null;
  }
}

function on_user_rotate_end(): void {
  if (!heatmap3d_ctx) return;
  heatmap3d_ctx.user_interacting = false;
  // 3秒后恢复自动旋转
  heatmap3d_ctx.resume_rotate_timer = setTimeout(() => {
    if (
      heatmap3d_ctx &&
      heatmap3d_ctx.auto_rotate_enabled &&
      !heatmap3d_ctx.user_interacting
    ) {
      heatmap3d_ctx.controls.autoRotate = true;
    }
  }, 3000);
}

function clear_group(group: THREE.Group): void {
  while (group.children.length > 0) {
    const child = group.children.pop();
    if (!child) break;
    group.remove(child);
    const any_child = child as any;
    if (any_child.geometry) any_child.geometry.dispose?.();
    if (any_child.material) {
      if (Array.isArray(any_child.material))
        any_child.material.forEach((m: any) => m?.dispose?.());
      else any_child.material.dispose?.();
    }
  }
}

function rebuild_heatmap3d_bars(): void {
  if (!heatmap3d_ctx) return;
  const ctx = heatmap3d_ctx;

  clear_group(ctx.pillars_group);
  clear_group(ctx.particles_group);
  clear_group(ctx.halos_group);
  clear_group(ctx.labels_group);
  ctx.particle_systems.length = 0;

  const x_len = heatmapData.value.score_ranges.length;
  const y_len = heatmapData.value.dimensions.length;
  const points = heatmapData.value.data || [];
  const max_count = Math.max(...points.map((p) => p[2] || 0), 1);
  ctx.max_count = max_count;

  const step = 1.2;
  const x_offset = ((x_len - 1) * step) / 2;
  const z_offset = ((y_len - 1) * step) / 2;

  const pillars: THREE.Mesh[] = [];

  for (const [x_idx, y_idx, count_raw] of points as any) {
    const count = Number(count_raw || 0);
    if (count <= 0) continue;
    const t = count / max_count;
    const target_height = Math.max(1, Math.sqrt(t) * 8);
    const pillar_radius = 0.08 + t * 0.15; // 粗细随数量变化

    const base_x = x_idx * step - x_offset;
    const base_z = y_idx * step - z_offset;
    const base_color = color_from_palette(t);

    // 光柱（圆柱体）
    const pillar_geom = new THREE.CylinderGeometry(
      pillar_radius,
      pillar_radius * 1.2,
      1,
      16,
      1,
      true,
    );
    // 亮色模式下提高不透明度和发光强度
    const pillarOpacity = isDark.value ? 0.4 : 0.85;
    const emissiveIntensity = isDark.value ? 0.8 + t * 0.5 : 0.3 + t * 0.2;
    const pillar_mat = new THREE.MeshStandardMaterial({
      color: base_color,
      emissive: base_color,
      emissiveIntensity,
      transparent: true,
      opacity: pillarOpacity,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const pillar = new THREE.Mesh(pillar_geom, pillar_mat);
    pillar.position.set(base_x, 0, base_z);
    pillar.scale.y = 0.01; // 初始高度为0
    (pillar as any).userData = {
      x_idx,
      y_idx,
      count,
      target_height,
      base_emissive: 0.8 + t * 0.5,
    };
    ctx.pillars_group.add(pillar);
    pillars.push(pillar);

    // 光晕（顶部发光圆环）
    const halo_geom = new THREE.RingGeometry(
      pillar_radius * 0.3,
      pillar_radius * 0.8,
      32,
    );
    // 亮色模式下提高光晕不透明度
    const haloOpacity = isDark.value ? 0.6 : 0.9;
    const halo_mat = new THREE.MeshBasicMaterial({
      color: base_color,
      transparent: true,
      opacity: haloOpacity,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const halo = new THREE.Mesh(halo_geom, halo_mat);
    halo.rotation.x = -Math.PI / 2;
    halo.position.set(base_x, 0.01, base_z);
    (halo as any).userData = { target_height, pillar };
    ctx.halos_group.add(halo);

    // 粒子系统（上升粒子）
    const particle_count = Math.max(20, Math.floor(t * 80));
    const positions = new Float32Array(particle_count * 3);
    const velocities = new Float32Array(particle_count);

    for (let i = 0; i < particle_count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const r = Math.random() * pillar_radius * 0.8;
      positions[i * 3] = base_x + Math.cos(angle) * r;
      positions[i * 3 + 1] = Math.random() * target_height;
      positions[i * 3 + 2] = base_z + Math.sin(angle) * r;
      velocities[i] = 0.5 + Math.random() * 1.5; // 上升速度
    }

    const particle_geom = new THREE.BufferGeometry();
    particle_geom.setAttribute(
      'position',
      new THREE.BufferAttribute(positions, 3),
    );

    // 亮色模式使用 NormalBlending（AdditiveBlending 在白色背景上不可见）
    const particleBlending = isDark.value
      ? THREE.AdditiveBlending
      : THREE.NormalBlending;
    const particle_mat = new THREE.PointsMaterial({
      color: base_color,
      size: 0.06 + t * 0.04,
      transparent: true,
      opacity: isDark.value ? 0.9 : 1,
      depthWrite: false,
      blending: particleBlending,
    });

    const particle_points = new THREE.Points(particle_geom, particle_mat);
    ctx.particles_group.add(particle_points);

    ctx.particle_systems.push({
      points: particle_points,
      velocities,
      max_height: target_height,
      base_x,
      base_z,
      radius: pillar_radius * 0.8,
    });
  }

  // 生长动画：光柱依次升起
  pillars.forEach((pillar, i) => {
    const data = (pillar as any).userData;
    gsap.to(pillar.scale, {
      y: data.target_height,
      duration: 1.2,
      delay: i * 0.02,
      ease: 'power2.out',
      onUpdate: () => {
        pillar.position.y = pillar.scale.y / 2;
      },
    });
  });

  // 光晕同步升起
  ctx.halos_group.children.forEach((halo: any, i: number) => {
    const data = halo.userData;
    gsap.to(halo.position, {
      y: data.target_height + 0.1,
      duration: 1.2,
      delay: i * 0.02,
      ease: 'power2.out',
    });
    // 光晕脉冲动画
    gsap.to(halo.scale, {
      x: 1.3,
      y: 1.3,
      duration: 1.5,
      delay: i * 0.02 + 0.5,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
    });
  });

  // 添加 3D 坐标轴文字
  build_axis_labels(ctx, x_len, y_len, step, x_offset, z_offset);

  // 视角自适应
  const span = Math.max(x_len, y_len, 6);
  ctx.camera.position.set(span * 1, span * 0.9, span * 1.3);
  ctx.controls.target.set(0, 2, 0);
  ctx.controls.update();
}

function build_axis_labels(
  ctx: Heatmap3DContext,
  _x_len: number,
  _y_len: number,
  step: number,
  x_offset: number,
  z_offset: number,
): void {
  // 标签颜色响应主题（亮色模式用深色，提高可读性）
  const label_color = isDark.value ? '#91d5ff' : '#1e3a5f';

  // X 轴标签（分数段）
  heatmapData.value.score_ranges.forEach((label, i) => {
    const sprite = new SpriteText(label, 0.4, label_color) as any;
    sprite.fontWeight = '500';
    sprite.backgroundColor = 'transparent';
    sprite.position.set(i * step - x_offset, -0.5, z_offset + 1.5);
    ctx.labels_group.add(sprite);
  });

  // Z 轴标签（维度名）
  heatmapData.value.dimensions.forEach((label, i) => {
    const sprite = new SpriteText(label, 0.4, label_color) as any;
    sprite.fontWeight = '500';
    sprite.backgroundColor = 'transparent';
    sprite.position.set(-x_offset - 1.5, 0.5, i * step - z_offset);
    ctx.labels_group.add(sprite);
  });
}

function tick_heatmap3d(): void {
  if (!heatmap3d_ctx) return;
  const ctx = heatmap3d_ctx;
  const delta = ctx.clock.getDelta();

  // 更新粒子位置（上升效果）
  for (const ps of ctx.particle_systems) {
    const positionAttribute = ps.points.geometry.attributes.position;
    if (!positionAttribute) continue;

    const positions = positionAttribute.array as Float32Array;
    const count = positions.length / 3;
    for (let i = 0; i < count; i++) {
      // 粒子上升
      const vel = ps.velocities[i] ?? 1;
      const x_idx = i * 3;
      const y_idx = x_idx + 1;
      const z_idx = x_idx + 2;
      (positions as any)[y_idx] += vel * delta;
      // 到达顶部后重置到底部
      if ((positions as any)[y_idx] > ps.max_height) {
        const angle = Math.random() * Math.PI * 2;
        const r = Math.random() * ps.radius;
        (positions as any)[x_idx] = ps.base_x + Math.cos(angle) * r;
        (positions as any)[y_idx] = 0;
        (positions as any)[z_idx] = ps.base_z + Math.sin(angle) * r;
      }
    }
    positionAttribute.needsUpdate = true;
  }

  ctx.controls.update();
  // 使用 Bloom 后处理渲染
  ctx.composer.render();
  ctx.animation_id = requestAnimationFrame(tick_heatmap3d);
}

function pick_heatmap3d(
  event: MouseEvent,
): null | THREE.Intersection<THREE.Object3D> {
  if (!heatmap3d_ctx) return null;
  const ctx = heatmap3d_ctx;
  const rect = ctx.renderer.domElement.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  const y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
  ctx.raycaster.setFromCamera(new THREE.Vector2(x, y), ctx.camera);
  const hits = ctx.raycaster.intersectObjects(
    ctx.pillars_group.children,
    false,
  );
  return hits.length > 0 ? hits[0]! : null;
}

function set_hover_mesh(mesh: null | THREE.Mesh): void {
  if (!heatmap3d_ctx) return;
  const ctx = heatmap3d_ctx;

  // 离开之前的柱子：恢复缩放和发光
  if (ctx.hover_mesh && ctx.hover_mesh !== mesh) {
    const prev_mesh = ctx.hover_mesh;
    const prev_data = (prev_mesh as any).userData || {};
    const prev_mat = prev_mesh.material as any;
    // 恢复原始 emissive 强度
    if (prev_mat?.emissive && prev_data.base_emissive !== undefined) {
      gsap.to(prev_mat, {
        emissiveIntensity: prev_data.base_emissive,
        duration: 0.3,
        ease: 'power2.out',
      });
    }
    // 恢复缩放（去掉弹起效果）
    if (prev_data.target_height) {
      gsap.to(prev_mesh.scale, {
        y: prev_data.target_height,
        duration: 0.3,
        ease: 'power2.out',
        onUpdate: () => {
          prev_mesh.position.y = prev_mesh.scale.y / 2;
        },
      });
    }
  }

  ctx.hover_mesh = mesh;

  // 进入新柱子：弹起 + 发光增强
  if (mesh) {
    const data = (mesh as any).userData || {};
    const mat = mesh.material as any;

    // 增强发光
    if (mat?.emissive) {
      gsap.to(mat, {
        emissiveIntensity: 1, // 最大发光
        duration: 0.2,
        ease: 'power2.out',
      });
    }

    // 弹起效果：Y 缩放增加 15%
    if (data.target_height) {
      gsap.to(mesh.scale, {
        y: data.target_height * 1.15,
        duration: 0.25,
        ease: 'back.out(2)',
        onUpdate: () => {
          mesh.position.y = mesh.scale.y / 2;
        },
      });
    }
  }
}

function on_heatmap3d_mousemove(event: MouseEvent): void {
  if (!heatmap3d_ctx) return;
  const ctx = heatmap3d_ctx;
  const hit = pick_heatmap3d(event);
  if (!hit || !(hit.object instanceof THREE.Mesh)) {
    set_hover_mesh(null);
    ctx.tooltip_sprite.visible = false;
    return;
  }

  const mesh = hit.object as THREE.Mesh;
  set_hover_mesh(mesh);
  const meta = (mesh as any).userData || {};
  const range_label = heatmapData.value.score_ranges[meta.x_idx] ?? '';
  const dim_name = heatmapData.value.dimensions[meta.y_idx] ?? '';
  const count = meta.count ?? 0;

  // 更新 3D tooltip 内容和位置
  ctx.tooltip_sprite.text = `${dim_name}\n分数段: ${range_label}\n文章数: ${count} 篇`;
  ctx.tooltip_sprite.visible = true;
  // 将 tooltip 放在柱子顶部上方
  const bar_top = mesh.position.y + mesh.scale.y / 2 + 0.8;
  ctx.tooltip_sprite.position.set(mesh.position.x, bar_top, mesh.position.z);
}

function on_heatmap3d_mouseleave(): void {
  if (!heatmap3d_ctx) return;
  const ctx = heatmap3d_ctx;
  set_hover_mesh(null);
  ctx.tooltip_sprite.visible = false;
}

// ==================== 数据加载 ====================
async function fetchTenants() {
  try {
    const items = await getTenantSimpleListApi();
    allTenants.value = items || [];
    tenantOptions.value = (items || []).map((x) => ({
      label: `${x.tenant_name}（${x.tenant_code}）`,
      value: x.id,
    }));
  } catch {
    allTenants.value = [];
    tenantOptions.value = [];
  }
}

async function fetchActivities() {
  try {
    const items = await getActivitySimpleListApi();
    allActivities.value = items || [];
    updateActivityOptions();
  } catch {
    allActivities.value = [];
    activityOptions.value = [];
  }
}

function updateActivityOptions() {
  const tid = filters.value.tenant_id;
  const filtered = tid
    ? allActivities.value.filter((a) => a.tenant_id === tid)
    : allActivities.value;
  activityOptions.value = filtered.map((x) => ({
    label: x.activity_name,
    value: x.id,
  }));
}

async function fetchJobs() {
  try {
    const items = await getJobListApi({ limit: 1000 });
    allJobs.value = (items || []).map((j) => ({
      activity_id: (j as any).activity_id ?? null,
      job_id: j.job_id,
      job_name: j.job_name,
      tenant_id: (j as any).tenant_id ?? null,
    }));
    updateJobOptions();
  } catch {
    allJobs.value = [];
    jobOptions.value = [];
  }
}

function updateJobOptions() {
  const tid = filters.value.tenant_id;
  const aid = filters.value.activity_id;
  let filtered = allJobs.value;
  if (tid) filtered = filtered.filter((j) => j.tenant_id === tid);
  if (aid) filtered = filtered.filter((j) => j.activity_id === aid);
  jobOptions.value = filtered.map((x) => ({
    label: x.job_name,
    value: x.job_id,
  }));
}

async function fetchDatasets() {
  const items = await listCriticDatasetsApi({
    source_type: filters.value.source_type,
  });
  datasetOptions.value = (items || []).map((x) => ({
    label: `${x.dataset_code}（${x.total}）`,
    value: x.dataset_code,
  }));
}

function buildParams() {
  const base = {
    end_date: endDate.value,
    expert_func: getSelectedExpertFunc(),
    source_type: filters.value.source_type,
    start_date: startDate.value,
  };
  if (filters.value.source_type === 'job') {
    return {
      ...base,
      activity_id: filters.value.activity_id || undefined,
      job_id: filters.value.job_id || undefined,
      tenant_id: filters.value.tenant_id || undefined,
    };
  }
  if (filters.value.source_type === 'eval_run') {
    return { ...base, dataset_code: filters.value.dataset_code || undefined };
  }
  return base;
}

// ==================== 炫酷图表渲染 ====================
// 图表主题配置（响应暗/亮模式）
function getChartTheme() {
  const dark = isDark.value;
  return {
    textColor: dark ? '#94a3b8' : '#6b7280',
    textColorPrimary: dark ? '#e2e8f0' : '#1f2937',
    axisLineColor: dark ? 'rgba(148,163,184,0.2)' : 'rgba(0,0,0,0.1)',
    tooltipBg: dark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)',
    tooltipBorder: 'rgba(24, 144, 255, 0.3)',
    tooltipText: dark ? '#e2e8f0' : '#1f2937',
  };
}

function renderCharts() {
  const theme = getChartTheme();

  // 趋势图 - 渐变面积图
  renderTrend({
    backgroundColor: 'transparent',
    grid: { bottom: 60, left: 50, right: 50, top: 60 },
    legend: {
      data: ['平均分', '通过率', '评分量'],
      icon: 'roundRect',
      itemGap: 20,
      textStyle: { color: theme.textColor },
      top: 10,
    },
    series: [
      {
        areaStyle: {
          color: {
            colorStops: [
              { color: 'rgba(99, 102, 241, 0.4)', offset: 0 },
              { color: 'rgba(99, 102, 241, 0.05)', offset: 1 },
            ],
            type: 'linear',
            x: 0,
            x2: 0,
            y: 0,
            y2: 1,
          },
        },
        data: trend.value.map((x) => x.avg_score),
        itemStyle: { color: colors.value.primary },
        lineStyle: { color: colors.value.primary, width: 3 },
        name: '平均分',
        showSymbol: false,
        smooth: true,
        type: 'line',
      },
      {
        areaStyle: {
          color: {
            colorStops: [
              { color: 'rgba(16, 185, 129, 0.4)', offset: 0 },
              { color: 'rgba(16, 185, 129, 0.05)', offset: 1 },
            ],
            type: 'linear',
            x: 0,
            x2: 0,
            y: 0,
            y2: 1,
          },
        },
        data: trend.value.map((x) => x.pass_rate),
        itemStyle: { color: colors.value.success },
        lineStyle: { color: colors.value.success, width: 3 },
        name: '通过率',
        showSymbol: false,
        smooth: true,
        type: 'line',
        yAxisIndex: 1,
      },
      {
        barWidth: 12,
        data: trend.value.map((x) => x.total_count),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            colorStops: [
              { color: 'rgba(139, 92, 246, 0.8)', offset: 0 },
              { color: 'rgba(139, 92, 246, 0.3)', offset: 1 },
            ],
            type: 'linear',
            x: 0,
            x2: 0,
            y: 0,
            y2: 1,
          },
        },
        name: '评分量',
        type: 'bar',
        yAxisIndex: 2,
      },
    ],
    tooltip: {
      axisPointer: {
        lineStyle: { color: theme.axisLineColor },
        type: 'cross',
      },
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipText },
      trigger: 'axis',
    },
    xAxis: {
      axisLabel: { color: theme.textColor, fontSize: 11 },
      axisLine: { lineStyle: { color: theme.axisLineColor } },
      boundaryGap: false,
      data: trend.value.map((x) => x.date.slice(5)),
      splitLine: { show: false },
      type: 'category',
    },
    yAxis: [
      {
        axisLabel: { color: theme.textColor, formatter: '{value}' },
        axisLine: { show: false },
        max: 100,
        min: 0,
        name: '分数',
        nameTextStyle: { color: theme.textColor },
        splitLine: { lineStyle: { color: theme.axisLineColor } },
        type: 'value',
      },
      {
        axisLabel: { color: theme.textColor, formatter: '{value}%' },
        axisLine: { show: false },
        max: 100,
        min: 0,
        name: '通过率',
        nameTextStyle: { color: theme.textColor },
        splitLine: { show: false },
        type: 'value',
      },
      {
        axisLabel: { show: false },
        axisLine: { show: false },
        name: '',
        show: false,
        splitLine: { show: false },
        type: 'value',
      },
    ],
  });

  // 分布图 - 环形饼图（按分数段占比，使用 Ant Design 色系）
  const totalCount = distribution.value.reduce((sum, x) => sum + x.count, 0);
  const pieColors = [
    '#f5222d', // 0-9 红
    '#fa541c', // 10-19 火山橙
    '#fa8c16', // 20-29 橙
    '#faad14', // 30-39 黄
    '#a0d911', // 40-49 青柠
    '#52c41a', // 50-59 绿
    '#13c2c2', // 60-69 青
    '#1890ff', // 70-79 蓝
    '#2f54eb', // 80-89 极客蓝
    '#722ed1', // 90-100 紫
  ];
  renderDist({
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipText },
      formatter: (p: any) => {
        const percent =
          totalCount > 0 ? ((p.value / totalCount) * 100).toFixed(1) : '0';
        return `<div style="font-weight:600">${p.name}</div>
                <div>数量：${p.value} 篇</div>
                <div>占比：${percent}%</div>`;
      },
    },
    legend: {
      orient: 'vertical',
      right: 20,
      top: 'center',
      textStyle: { color: theme.textColor, fontSize: 12 },
      itemGap: 8,
      itemWidth: 12,
      itemHeight: 12,
    },
    series: [
      {
        type: 'pie',
        radius: ['45%', '75%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: isDark.value
            ? 'rgba(15, 23, 42, 0.8)'
            : 'rgba(255, 255, 255, 0.9)',
          borderWidth: 2,
        },
        label: {
          show: true,
          position: 'outside',
          color: theme.textColor,
          fontSize: 11,
          formatter: (p: any) => {
            const percent =
              totalCount > 0 ? ((p.value / totalCount) * 100).toFixed(0) : '0';
            return p.value > 0 ? `${percent}%` : '';
          },
        },
        labelLine: {
          show: true,
          lineStyle: { color: 'rgba(148,163,184,0.3)' },
          length: 10,
          length2: 8,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(99, 102, 241, 0.5)',
          },
          label: { show: true, fontSize: 13, fontWeight: 'bold' },
        },
        data: distribution.value.map((x, i) => ({
          name: x.range,
          value: x.count,
          itemStyle: { color: pieColors[i] || colors.value.primary },
        })),
      },
    ],
  });

  // 问题热词 - 水平渐变条
  renderCtx({
    backgroundColor: 'transparent',
    grid: { bottom: 20, left: 130, right: 30, top: 20 },
    series: [
      {
        barWidth: 16,
        data: topContexts.value
          .map((x, i) => ({
            itemStyle: {
              borderRadius: [0, 8, 8, 0],
              color: {
                colorStops: [
                  { color: 'rgba(239,68,68,0.2)', offset: 0 },
                  {
                    color: i < 3 ? colors.value.danger : colors.value.warning,
                    offset: 1,
                  },
                ],
                type: 'linear',
                x: 0,
                x2: 1,
                y: 0,
                y2: 0,
              },
            },
            value: x.count,
          }))
          .toReversed(),
        label: {
          color: '#e2e8f0',
          fontSize: 11,
          position: 'right',
          show: true,
        },
        type: 'bar',
      },
    ],
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipText },
    },
    xAxis: {
      axisLabel: { color: theme.textColor },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: theme.axisLineColor } },
      type: 'value',
    },
    yAxis: {
      axisLabel: { color: theme.textColor, fontSize: 12, width: 120 },
      axisLine: { show: false },
      data: topContexts.value.map((x) => x.key).toReversed(),
      splitLine: { show: false },
      type: 'category',
    },
  } as any);

  // 维度×分数热力图（2D）
  const heatmapMaxValue = Math.max(
    ...heatmapData.value.data.map((d) => d[2] || 0),
    1,
  );
  renderHeatmap({
    backgroundColor: 'transparent',
    grid: { bottom: 80, left: 100, right: 60, top: 30 },
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipText },
      formatter: (p: any) => {
        // 数据格式：[x轴索引(分数段), y轴索引(维度), 数量]
        const rangeLabel = heatmapData.value.score_ranges[p.data[0]] || '';
        const dimName = heatmapData.value.dimensions[p.data[1]] || '';
        const count = p.data[2] || 0;
        return `<div style="font-weight:600">${dimName}</div>
                <div>分数段：${rangeLabel}</div>
                <div>文章数：${count} 篇</div>`;
      },
    },
    xAxis: {
      type: 'category',
      data: heatmapData.value.score_ranges,
      axisLabel: { color: theme.textColor, fontSize: 11 },
      axisLine: { lineStyle: { color: theme.axisLineColor } },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: heatmapData.value.dimensions,
      axisLabel: { color: theme.textColor, fontSize: 12 },
      axisLine: { show: false },
      splitArea: { show: false },
    },
    visualMap: {
      min: 0,
      max: heatmapMaxValue,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 10,
      inRange: {
        color: [
          '#e6f7ff', // 最浅蓝
          '#91d5ff',
          '#69c0ff',
          '#40a9ff',
          '#1890ff', // 主蓝
          '#52c41a', // 绿
          '#fadb14', // 黄
          '#fa8c16', // 橙
          '#f5222d', // 红
          '#722ed1', // 紫（最高）
        ],
      },
      textStyle: { color: theme.textColor },
    },
    series: [
      {
        type: 'heatmap',
        data: heatmapData.value.data,
        label: {
          show: true,
          color: isDark.value ? '#fff' : '#1f2937',
          fontSize: 10,
          formatter: (p: any) => (p.data[2] > 0 ? p.data[2] : ''),
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  } as any);

  // 3D 光束塔（始终初始化）
  nextTick(() => init_heatmap3d());

  // Scatter with Jittering: x=维度, y=分数
  const dimensions = [...new Set(scatterData.value.map((d) => d.dimension))];
  const scatterSeriesData = scatterData.value.map((d) => {
    const dimIndex = dimensions.indexOf(d.dimension);
    // 增大 jittering 范围，让点分布更开阔
    const jitter = (Math.random() - 0.5) * 0.7;
    return [dimIndex + jitter, d.score, d.content_id];
  });

  // 定义渐变色，根据分数映射颜色
  const getPointColor = (score: number) => {
    if (score >= 80) return '#52c41a'; // 优秀 - 绿色
    if (score >= 60) return '#1890ff'; // 良好 - 蓝色
    if (score >= 40) return '#faad14'; // 一般 - 黄色
    return '#f5222d'; // 较差 - 红色
  };

  const coloredData = scatterSeriesData.map((item) => ({
    value: item,
    itemStyle: {
      color: getPointColor(item[1] as number),
    },
  }));

  renderScatter({
    backgroundColor: 'transparent',
    grid: { bottom: 80, left: 70, right: 50, top: 50 },
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipText },
      formatter: (p: any) => {
        const data = p.data.value || p.data;
        const dimName = dimensions[Math.round(data[0])] || '';
        const score = data[1];
        const contentId = data[2] || '';
        let scoreLevel = '较差';
        if (score >= 80) {
          scoreLevel = '优秀';
        } else if (score >= 60) {
          scoreLevel = '良好';
        } else if (score >= 40) {
          scoreLevel = '一般';
        }
        return `<div style="font-weight:600;margin-bottom:4px">${dimName}</div>
              <div>分数：<span style="font-weight:600;color:${getPointColor(score)}">${score}</span> (${scoreLevel})</div>
              <div style="font-size:11px;color:${theme.textColor};margin-top:2px">文章: ${contentId.slice(0, 16)}...</div>`;
      },
    },
    xAxis: {
      type: 'category',
      data: dimensions,
      axisLabel: {
        color: theme.textColor,
        fontSize: 12,
        rotate: 0,
        interval: 0,
      },
      axisLine: { lineStyle: { color: theme.axisLineColor } },
      splitLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '分数',
      nameTextStyle: {
        color: theme.textColor,
        fontSize: 12,
        padding: [0, 40, 0, 0],
      },
      min: 0,
      max: 100,
      interval: 20,
      axisLabel: { color: theme.textColor, fontSize: 12 },
      axisLine: { show: false },
      splitLine: {
        lineStyle: { color: theme.axisLineColor, type: 'dashed' },
      },
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0,
        filterMode: 'none',
      },
      {
        type: 'inside',
        yAxisIndex: 0,
        filterMode: 'none',
      },
    ],
    series: [
      {
        type: 'scatter',
        data: coloredData,
        symbolSize: 10,
        itemStyle: {
          opacity: 0.75,
          shadowBlur: 4,
          shadowColor: 'rgba(0, 0, 0, 0.2)',
        },
        emphasis: {
          scale: 1.8,
          itemStyle: {
            opacity: 1,
            shadowBlur: 12,
            shadowColor: 'rgba(99, 102, 241, 0.6)',
          },
        },
      },
    ],
  } as any);
}

async function fetchAll() {
  loading.value = true;
  try {
    if (filters.value.source_type === 'job') {
      await Promise.all([fetchTenants(), fetchActivities(), fetchJobs()]);
    } else if (filters.value.source_type === 'eval_run') {
      await fetchDatasets();
    }

    // 维度筛选（expert_func）只影响：评分趋势 + 分数分布
    // 其他图表/卡片都使用"全维度"口径（忽略 expert_func）
    const params = buildParams();
    const allDimParams = { ...params } as any;
    delete allDimParams.expert_func;

    // CRITIC 参数（质量评分）
    const criticParams = { ...allDimParams, expert_type: 'CRITIC' as const };
    // BAN 参数（合规封禁）
    const banParams = { ...allDimParams, expert_type: 'BAN' as const };

    // 并行获取 CRITIC 和 BAN 的统计数据
    const [criticSummary, banSummary, criticTrend, banTrend] =
      await Promise.all([
        getCriticSummaryApi(criticParams),
        getCriticSummaryApi(banParams),
        getCriticTrendApi({ ...params, expert_type: 'CRITIC' } as any),
        getCriticTrendApi({ ...params, expert_type: 'BAN' } as any),
      ]);

    // summary 使用 CRITIC 数据（平均分等）
    summary.value = criticSummary;
    // BAN summary 用于展示合规通过率
    banSummaryData.value = banSummary;

    // 趋势数据合并：平均分用 CRITIC，通过率用 BAN
    trend.value = criticTrend.map((item, idx) => {
      const banItem = banTrend[idx];
      return {
        ...item,
        // 通过率用 BAN 数据（合规通过率）
        pass_rate: banItem?.pass_rate ?? 0,
        passed_count: banItem?.passed_count ?? 0,
      };
    });

    // 分数分布只展示 CRITIC 类型
    distribution.value = await getCriticDistributionApi({
      ...params,
      bucket_size: 10,
      expert_type: 'CRITIC',
    });

    // 词云使用 CRITIC 类型
    reasonWordCloud.value = await getCriticReasonWordCloudApi({
      ...criticParams,
      top_n: 120,
      sample_limit: 5000,
      min_len: 2,
    });
    topContexts.value = await getCriticProblemContextTopApi({
      ...criticParams,
      top_n: 10,
    });

    // 热力图只展示 CRITIC 类型（默认）
    heatmapData.value = await getCriticDimensionHeatmapApi({
      ...allDimParams,
      bucket_size: 10,
      expert_type: 'CRITIC',
    });

    // 散点图只展示 CRITIC 类型（默认）
    scatterData.value = await getCriticScatterDataApi({
      ...allDimParams,
      limit: 2000,
      expert_type: 'CRITIC',
    });

    // 合规检查统计：使用 BAN 类型，按 expert_func 分别获取
    // 注：CriticIllegal 和 CriticKeywordFilter 是同一概念，合并为「内容合规」
    const [
      illegalSummary,
      keywordSummary,
      unreasonableSummary,
      counterproductiveSummary,
    ] = await Promise.all([
      getCriticSummaryApi({ ...banParams, expert_func: 'CriticIllegal' }),
      getCriticSummaryApi({ ...banParams, expert_func: 'CriticKeywordFilter' }),
      getCriticSummaryApi({ ...banParams, expert_func: 'CriticUnreasonable' }),
      getCriticSummaryApi({
        ...banParams,
        expert_func: 'CriticCounterproductive',
      }),
    ]);
    // 合并「不合规范」和「违禁词」为「内容合规」
    const illegalTotal = illegalSummary?.total_count ?? 0;
    const illegalPassed = illegalSummary?.passed_count ?? 0;
    const keywordTotal = keywordSummary?.total_count ?? 0;
    const keywordPassed = keywordSummary?.passed_count ?? 0;
    compliance.value.contentCompliance = {
      total: illegalTotal + keywordTotal,
      passed: illegalPassed + keywordPassed,
    };
    compliance.value.unreasonable = {
      total: unreasonableSummary?.total_count ?? 0,
      passed: unreasonableSummary?.passed_count ?? 0,
    };
    compliance.value.counterproductive = {
      total: counterproductiveSummary?.total_count ?? 0,
      passed: counterproductiveSummary?.passed_count ?? 0,
    };

    renderCharts();
  } catch (error: any) {
    message.error(error?.message || '获取评分分析数据失败');
  } finally {
    loading.value = false;
  }
}

function resetFilters() {
  filters.value.tenant_id = undefined;
  filters.value.activity_id = undefined;
  filters.value.job_id = '';
  filters.value.dataset_code = '';
  filters.value.expert_config_code = '';
  updateActivityOptions();
  updateJobOptions();
  fetchAll();
}

onMounted(() => {
  fetchExpertConfigOptions();
  fetchAll();
});

onUnmounted(() => {
  dispose_heatmap3d();
});

// 监听主题变化，更新 3D 场景和图表
watch(isDark, () => {
  // 重新初始化 3D 场景（包含背景、网格、标签等完整主题更新）
  if (heatmap3d_ctx) {
    nextTick(() => init_heatmap3d());
  }
  // 重新渲染所有图表（使用新的主题配色）
  renderCharts();
});

watch(
  () => [
    heatmapData.value.dimensions.length,
    heatmapData.value.score_ranges.length,
    heatmapData.value.data.length,
  ],
  () => {
    // 数据变更时重建柱阵
    rebuild_heatmap3d_bars();
  },
);

let refreshTimer: null | number = null;
watch(
  () => [
    filters.value.source_type,
    filters.value.tenant_id,
    filters.value.activity_id,
    filters.value.job_id,
    filters.value.dataset_code,
    filters.value.expert_config_code,
    dateRange.value?.[0]?.valueOf(),
    dateRange.value?.[1]?.valueOf(),
  ],
  () => {
    if (refreshTimer) window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => fetchAll(), 200);
  },
);

watch(
  () => filters.value.source_type,
  () => {
    filters.value.tenant_id = undefined;
    filters.value.activity_id = undefined;
    filters.value.job_id = '';
    filters.value.dataset_code = '';
  },
);

watch(
  () => filters.value.tenant_id,
  () => {
    filters.value.activity_id = undefined;
    filters.value.job_id = '';
    filters.value.expert_config_code = '';
    updateActivityOptions();
    updateJobOptions();
    fetchExpertConfigOptions();
  },
);

watch(
  () => filters.value.activity_id,
  () => {
    filters.value.job_id = '';
    updateJobOptions();
  },
);
</script>

<template>
  <div class="critic-dashboard" :class="{ 'theme-light': !isDark }">
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          AI评分分析
        </span>
      </div>
      <div class="filter-row">
        <div class="filter-item">
          <Tooltip title="选择要查询的时间范围，默认最近 30 天">
            <span class="filter-label">日期范围</span>
          </Tooltip>
          <RangePicker
            v-model:value="dateRange"
            class="date-picker"
            :allow-clear="false"
          />
        </div>
        <div class="filter-item">
          <Tooltip
            title="数据来源：线上 Job（生产数据）、批量评测（测试数据集）、调试（开发测试）"
          >
            <span class="filter-label">数据来源</span>
          </Tooltip>
          <Select
            v-model:value="filters.source_type"
            :options="[
              { label: '🚀 线上 Job', value: 'job' },
              { label: '🧪 批量评测', value: 'eval_run' },
              { label: '🔧 调试', value: 'debug' },
            ]"
            class="filter-select"
            style="width: 140px"
          />
        </div>
        <template v-if="showJobFilters">
          <div v-if="false" class="filter-item">
            <Tooltip title="按租户/品牌筛选，留空则查询全部租户">
              <span class="filter-label">租户</span>
            </Tooltip>
            <Select
              v-model:value="filters.tenant_id"
              :options="tenantOptions"
              allow-clear
              class="filter-select"
              option-filter-prop="label"
              placeholder="全部"
              show-search
              style="width: 140px"
            />
          </div>
          <div class="filter-item">
            <Tooltip title="按营销活动筛选">
              <span class="filter-label">活动</span>
            </Tooltip>
            <Select
              v-model:value="filters.activity_id"
              :options="activityOptions"
              allow-clear
              class="filter-select"
              option-filter-prop="label"
              placeholder="全部"
              show-search
              style="width: 120px"
            />
          </div>
          <div class="filter-item">
            <Tooltip title="按具体 Job 筛选，一个活动可包含多个 Job">
              <span class="filter-label">Job</span>
            </Tooltip>
            <Select
              v-model:value="filters.job_id"
              :options="jobOptions"
              allow-clear
              class="filter-select"
              option-filter-prop="label"
              placeholder="全部"
              show-search
              style="width: 140px"
            />
          </div>
        </template>
        <div v-if="showEvalRunFilters" class="filter-item">
          <Tooltip title="批量评测时使用的数据集编码">
            <span class="filter-label">数据集</span>
          </Tooltip>
          <Select
            v-model:value="filters.dataset_code"
            :options="datasetOptions"
            allow-clear
            class="filter-select"
            option-filter-prop="label"
            placeholder="全部"
            show-search
            style="width: 180px"
          />
        </div>
        <div class="filter-item">
          <Tooltip title="按评分维度筛选，仅影响「评分趋势」和「分数分布」图表">
            <span class="filter-label">维度</span>
          </Tooltip>
          <Select
            v-model:value="filters.expert_config_code"
            :options="expertConfigOptions"
            allow-clear
            class="filter-select"
            placeholder="全部"
            show-search
            option-filter-prop="label"
            style="width: 160px"
          />
        </div>
        <div class="filter-item">
          <Tooltip placement="bottom">
            <template #title>
              <div class="tooltip-content tooltip-dimensions">
                <div class="tooltip-title">评分维度说明</div>
                <div class="tooltip-dim-grid">
                  <div class="tooltip-dim-group">
                    <div class="tooltip-dim-header">🎯 CRITIC 质量评分</div>
                    <div class="tooltip-dim-item">
                      <b>内容质量</b>：文章整体质量、可读性、信息价值
                    </div>
                    <div class="tooltip-dim-item">
                      <b>品牌匹配</b>：是否契合品牌调性和定位
                    </div>
                    <div class="tooltip-dim-item">
                      <b>创造力</b>：内容的独特性和创新程度
                    </div>
                    <div class="tooltip-dim-item">
                      <b>人设真实感</b>：人设表达是否自然可信
                    </div>
                    <div class="tooltip-dim-item">
                      <b>文章优雅性</b>：文笔流畅度和表达美感
                    </div>
                    <div class="tooltip-dim-item">
                      <b>营销效果</b>：种草/转化潜力评估
                    </div>
                  </div>
                  <div class="tooltip-dim-group">
                    <div class="tooltip-dim-header">🚫 BAN 合规检测</div>
                    <div class="tooltip-dim-item">
                      <b>不合规范</b>：法律法规禁止内容 + 违禁词
                    </div>
                    <div class="tooltip-dim-item">
                      <b>不合理</b>：逻辑矛盾、论据不支持论点
                    </div>
                    <div class="tooltip-dim-item">
                      <b>不合目的</b>：偏离营销目标、产生反效果
                    </div>
                  </div>
                </div>
                <div class="tooltip-dim-footer">
                  维度筛选仅影响「评分趋势」和「分数分布」图表
                </div>
              </div>
            </template>
            <div class="filter-hint filter-hint-clickable">
              <span class="filter-hint-strong">维度筛选</span>
              <span class="filter-hint-text"
                >仅影响「评分趋势」「分数分布」</span
              >
              <span class="filter-hint-icon">ⓘ</span>
            </div>
          </Tooltip>
        </div>
        <div class="filter-actions">
          <Button
            class="btn-glow"
            type="primary"
            :loading="loading"
            @click="fetchAll"
          >
            刷新数据
          </Button>
          <Button @click="resetFilters">重置</Button>
        </div>
      </div>
    </div>

    <Spin :spinning="loading">
      <!-- 统计卡片 -->
      <Row :gutter="16" class="stat-row">
        <Col :span="6">
          <div class="stat-card gradient-1">
            <div class="stat-icon">📊</div>
            <div class="stat-content">
              <div class="stat-value">
                {{ summary.total_count.toLocaleString() }}
              </div>
              <div class="stat-label">
                评分总次数
                <MetricHelp
                  metric-key="critic_total_count"
                  title="所有专家（CRITIC 质量评分 + BAN 合规检测）对文章的评分次数总和。一篇文章可能被多个维度评分。"
                />
              </div>
            </div>
          </div>
        </Col>
        <Col :span="6">
          <div class="stat-card gradient-2">
            <div class="stat-icon">✅</div>
            <div class="stat-content">
              <div class="stat-value">
                {{ banSummaryData.pass_rate.toFixed(1) }}%
              </div>
              <div class="stat-label">
                合规通过率
                <MetricHelp
                  metric-key="ban_pass_rate"
                  title="BAN 类专家检测通过的比例。包含：内容合规（不合规范+违禁词）、逻辑合理性、目的一致性检测。通过率 = 通过次数 / 检测总次数 × 100%"
                />
              </div>
            </div>
          </div>
        </Col>
        <Col :span="6">
          <div class="stat-card gradient-3">
            <div class="stat-icon">⭐</div>
            <div class="stat-content">
              <div class="stat-value">{{ summary.avg_score.toFixed(1) }}</div>
              <div class="stat-label">
                平均分数
                <MetricHelp
                  metric-key="critic_avg_score"
                  title="CRITIC 类专家（内容质量、品牌匹配、创造力等）评分的平均值。满分 100 分，60 分及以上为良好。"
                />
              </div>
            </div>
          </div>
        </Col>
        <Col :span="6">
          <div class="stat-card gradient-4">
            <div class="stat-icon">⚡</div>
            <div class="stat-content">
              <div class="stat-value">
                {{ (summary.avg_duration_ms / 1000).toFixed(2) }}s
              </div>
              <div class="stat-label">
                平均耗时
                <MetricHelp
                  metric-key="critic_avg_duration"
                  title="单次评分的平均处理时间，包含 LLM 推理和后处理。耗时越短，系统性能越好。"
                />
              </div>
            </div>
          </div>
        </Col>
      </Row>

      <!-- 维度筛选仅影响：评分趋势 + 分数分布 -->
      <Row :gutter="16" class="chart-row">
        <Col :span="12">
          <div class="chart-card">
            <div class="chart-header">
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">评分趋势</div>
                    <div class="tooltip-desc">
                      按日期展示评分数据变化：<br />
                      • <b>紫色曲线</b>：CRITIC 专家平均分<br />
                      • <b>绿色曲线</b>：BAN 专家合规通过率<br />
                      • <b>柱状图</b>：当日评分次数
                    </div>
                  </div>
                </template>
                <span class="chart-title chart-title-help">📈 评分趋势 ⓘ</span>
              </Tooltip>
              <span class="chart-subtitle">
                {{
                  filters.expert_config_code
                    ? '受维度筛选影响：当前维度趋势'
                    : '受维度筛选影响：全维度趋势（按记录聚合）'
                }}
              </span>
            </div>
            <EchartsUI
              ref="trendChartRef"
              class="chart-area"
              style="height: 320px"
            />
          </div>
        </Col>
        <Col :span="12">
          <div class="chart-card">
            <div class="chart-header">
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">分数分布</div>
                    <div class="tooltip-desc">
                      CRITIC 专家评分的分数段分布（环形图）：<br />
                      • 每个扇区代表一个分数段<br />
                      • 百分比表示该分数段文章占比<br />
                      • 悬停可查看具体数量
                    </div>
                  </div>
                </template>
                <span class="chart-title chart-title-help">📊 分数分布 ⓘ</span>
              </Tooltip>
              <span class="chart-subtitle">
                {{
                  filters.expert_config_code
                    ? '受维度筛选影响：当前维度分数分布'
                    : '受维度筛选影响：多维度平均分分布（按文章聚合）'
                }}
              </span>
            </div>
            <EchartsUI
              ref="distChartRef"
              class="chart-area"
              style="height: 320px"
            />
          </div>
        </Col>
      </Row>

      <!-- 其他图表：全维度口径（忽略维度筛选） -->
      <Row :gutter="16" class="chart-row">
        <Col :span="12">
          <div class="chart-card">
            <div class="chart-header">
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">高频问题 TOP10</div>
                    <div class="tooltip-desc">
                      CRITIC 专家识别出的常见问题类型：<br />
                      • 条形长度代表出现次数<br />
                      • 帮助定位内容生成的共性问题<br />
                      • 可用于优化 Prompt 或训练数据
                    </div>
                  </div>
                </template>
                <span class="chart-title chart-title-help"
                  >🔥 高频问题 TOP10 ⓘ</span
                >
              </Tooltip>
              <span class="chart-subtitle"
                >全维度口径：问题种类统计（不受维度筛选影响）</span
              >
            </div>
            <EchartsUI
              ref="ctxChartRef"
              class="chart-area"
              style="height: 320px"
            />
          </div>
        </Col>
        <Col :span="12">
          <div class="chart-card">
            <div class="chart-header">
              <span class="chart-title">✅ 合规检查统计</span>
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-desc">
                      BAN 类专家的三大检测维度通过率。<br />
                      通过 = 文章未触发封禁规则
                    </div>
                  </div>
                </template>
                <span class="chart-subtitle chart-subtitle-help"
                  >不合规范 / 不合理 / 不合目的 通过率 ⓘ</span
                >
              </Tooltip>
            </div>
            <div class="compliance-body-3col">
              <!-- 内容合规（合并：不合规范 + 违禁词） -->
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">内容合规检测</div>
                    <div class="tooltip-desc">
                      合并「不合规范」与「违禁词」检测结果。<br />
                      检测内容是否包含：<br />
                      • 法律法规禁止的表述<br />
                      • 敏感词/黑名单词汇<br />
                      • 虚假宣传用语
                    </div>
                  </div>
                </template>
                <div class="compliance-item">
                  <div class="compliance-title">
                    <span>不合规范</span>
                    <span class="compliance-badge">不合规范+违禁词</span>
                  </div>
                  <div class="compliance-metrics">
                    <span class="text-muted-foreground">
                      通过 {{ compliance.contentCompliance.passed }} /
                      {{ compliance.contentCompliance.total }}
                    </span>
                    <span class="compliance-rate">
                      {{
                        formatRate(
                          compliance.contentCompliance.passed,
                          compliance.contentCompliance.total,
                        )
                      }}
                    </span>
                  </div>
                  <div class="compliance-bar">
                    <div
                      class="compliance-bar-fill fill-success"
                      :style="{
                        width: compliance.contentCompliance.total
                          ? `${(compliance.contentCompliance.passed / compliance.contentCompliance.total) * 100}%`
                          : '0%',
                      }"
                    ></div>
                  </div>
                  <div class="compliance-sub text-muted-foreground">
                    不通过
                    {{
                      Math.max(
                        compliance.contentCompliance.total -
                          compliance.contentCompliance.passed,
                        0,
                      )
                    }}
                    篇
                  </div>
                </div>
              </Tooltip>

              <!-- 逻辑合理 -->
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">逻辑合理性检测</div>
                    <div class="tooltip-desc">
                      检测文章逻辑是否通顺：<br />
                      • 论据是否支持论点<br />
                      • 是否存在自相矛盾<br />
                      • 因果关系是否合理
                    </div>
                  </div>
                </template>
                <div class="compliance-item">
                  <div class="compliance-title">不合理</div>
                  <div class="compliance-metrics">
                    <span class="text-muted-foreground">
                      通过 {{ compliance.unreasonable.passed }} /
                      {{ compliance.unreasonable.total }}
                    </span>
                    <span class="compliance-rate">
                      {{
                        formatRate(
                          compliance.unreasonable.passed,
                          compliance.unreasonable.total,
                        )
                      }}
                    </span>
                  </div>
                  <div class="compliance-bar">
                    <div
                      class="compliance-bar-fill fill-cyan"
                      :style="{
                        width: compliance.unreasonable.total
                          ? `${(compliance.unreasonable.passed / compliance.unreasonable.total) * 100}%`
                          : '0%',
                      }"
                    ></div>
                  </div>
                  <div class="compliance-sub text-muted-foreground">
                    不通过
                    {{
                      Math.max(
                        compliance.unreasonable.total -
                          compliance.unreasonable.passed,
                        0,
                      )
                    }}
                    篇
                  </div>
                </div>
              </Tooltip>

              <!-- 目的一致 -->
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">目的一致性检测</div>
                    <div class="tooltip-desc">
                      检测文章是否符合营销目的：<br />
                      • 是否偏离品牌调性<br />
                      • 是否产生反效果<br />
                      • 是否与活动目标一致
                    </div>
                  </div>
                </template>
                <div class="compliance-item">
                  <div class="compliance-title">不合目的</div>
                  <div class="compliance-metrics">
                    <span class="text-muted-foreground">
                      通过 {{ compliance.counterproductive.passed }} /
                      {{ compliance.counterproductive.total }}
                    </span>
                    <span class="compliance-rate">
                      {{
                        formatRate(
                          compliance.counterproductive.passed,
                          compliance.counterproductive.total,
                        )
                      }}
                    </span>
                  </div>
                  <div class="compliance-bar">
                    <div
                      class="compliance-bar-fill fill-purple"
                      :style="{
                        width: compliance.counterproductive.total
                          ? `${(compliance.counterproductive.passed / compliance.counterproductive.total) * 100}%`
                          : '0%',
                      }"
                    ></div>
                  </div>
                  <div class="compliance-sub text-muted-foreground">
                    不通过
                    {{
                      Math.max(
                        compliance.counterproductive.total -
                          compliance.counterproductive.passed,
                        0,
                      )
                    }}
                    篇
                  </div>
                </div>
              </Tooltip>
            </div>
          </div>
        </Col>
      </Row>

      <!-- 2D 热力图 + 散点图 -->
      <Row :gutter="20" class="chart-row">
        <Col :span="12">
          <div class="chart-card">
            <div class="chart-header">
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">分数热力图</div>
                    <div class="tooltip-desc">
                      二维热力图展示评分分布密度：<br />
                      • X轴：分数段（0-9, 10-19, ...）<br />
                      • Y轴：评分维度（内容质量、品牌匹配等）<br />
                      • 颜色深浅：该格子内的文章数量<br />
                      <span class="tooltip-formula"
                        >颜色越红 = 文章越多 = 热点区域</span
                      >
                    </div>
                  </div>
                </template>
                <span class="chart-title chart-title-help"
                  >🗺️ 分数热力图 ⓘ</span
                >
              </Tooltip>
              <span class="chart-subtitle">
                x=分数段，y=评分维度，颜色=文章数
              </span>
            </div>
            <EchartsUI
              ref="heatmapChartRef"
              class="chart-area"
              style="height: 420px"
            />
          </div>
        </Col>
        <Col :span="12">
          <div class="chart-card">
            <div class="chart-header">
              <Tooltip placement="top">
                <template #title>
                  <div class="tooltip-content">
                    <div class="tooltip-title">文章分数散点图</div>
                    <div class="tooltip-desc">
                      每个点代表一篇文章的单次评分：<br />
                      • X轴：评分维度<br />
                      • Y轴：具体分数（0-100）<br />
                      • 点的颜色：分数等级<br />
                      <span class="tooltip-formula"
                        >🟢≥80 优秀 | 🟣≥60 良好 | 🟠≥40 一般 | 🔴＜40
                        较差</span
                      >
                    </div>
                  </div>
                </template>
                <span class="chart-title chart-title-help"
                  >📊 文章分数散点图 ⓘ</span
                >
              </Tooltip>
              <span class="chart-subtitle">
                x=评分维度，y=分数，每个点=一篇文章（带抖动）
              </span>
            </div>
            <EchartsUI
              ref="scatterChartRef"
              class="chart-area"
              style="height: 420px"
            />
          </div>
        </Col>
      </Row>

      <!-- 3D 光束塔（独立全宽卡片，更大展示面积） -->
      <div class="chart-card full-width">
        <div class="chart-header">
          <Tooltip placement="top">
            <template #title>
              <div class="tooltip-content">
                <div class="tooltip-title">3D 光束塔</div>
                <div class="tooltip-desc">
                  三维可视化展示评分分布：<br />
                  • X轴：分数段<br />
                  • Z轴：评分维度<br />
                  • 高度：该区间的文章数量<br />
                  • 颜色：从冷色（少）到暖色（多）<br />
                  <span class="tooltip-formula"
                    >光柱越高越红 = 文章集中区域</span
                  >
                </div>
              </div>
            </template>
            <span class="chart-title chart-title-help">🚀 3D 光束塔 ⓘ</span>
          </Tooltip>
          <span class="chart-subtitle">
            x=分数段，z=评分维度，高度=文章数量 |
            操作：拖拽旋转，滚轮缩放，悬浮查看详情
          </span>
        </div>
        <div
          ref="heatmap3dContainerRef"
          class="heatmap-3d-container"
          style="height: 500px"
        ></div>
      </div>
    </Spin>
  </div>
</template>

<style scoped>
.critic-dashboard {
  min-height: 100vh;
  padding: 20px;
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
  transition: background 0.3s ease;
}

/* 亮色主题 */
.critic-dashboard.theme-light {
  background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f1f5f9 100%);
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  margin-bottom: 20px;
  background: rgb(30 41 59 / 60%);
  border: 1px solid rgb(99 102 241 / 20%);
  border-radius: 16px;
  backdrop-filter: blur(20px);
  transition: all 0.3s ease;
}

.theme-light .filter-bar {
  background: rgb(255 255 255 / 80%);
  border-color: rgb(24 144 255 / 20%);
  box-shadow: 0 4px 16px rgb(0 0 0 / 8%);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

/* 3 列布局：合并后只有 3 个合规项 */
.compliance-body-3col {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  padding: 4px 2px;
}

.compliance-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding: 4px 2px;
}

.compliance-item {
  padding: 12px;
  background: rgb(15 23 42 / 25%);
  border: 1px solid rgb(148 163 184 / 12%);
  border-radius: 14px;
  transition: all 0.3s ease;
}

.theme-light .compliance-item {
  background: rgb(241 245 249 / 80%);
  border-color: rgb(24 144 255 / 15%);
}

.compliance-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 700;
  color: #e2e8f0;
}

.theme-light .compliance-title {
  color: #1f2937;
}

.compliance-badge {
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 500;
  color: #94a3b8;
  background: rgb(99 102 241 / 15%);
  border: 1px solid rgb(99 102 241 / 25%);
  border-radius: 4px;
}

.compliance-metrics {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}

.compliance-rate {
  font-weight: 800;
  color: #e2e8f0;
}

.theme-light .compliance-rate {
  color: #1f2937;
}

.compliance-bar {
  height: 10px;
  overflow: hidden;
  background: rgb(148 163 184 / 12%);
  border: 1px solid rgb(148 163 184 / 18%);
  border-radius: 999px;
}

.compliance-bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.35s ease;
}

.fill-success {
  background: linear-gradient(
    90deg,
    rgb(16 185 129 / 90%),
    rgb(59 130 246 / 90%)
  );
}

.fill-warning {
  background: linear-gradient(
    90deg,
    rgb(245 158 11 / 95%),
    rgb(239 68 68 / 85%)
  );
}

.fill-cyan {
  background: linear-gradient(
    90deg,
    rgb(6 182 212 / 95%),
    rgb(59 130 246 / 90%)
  );
}

.fill-purple {
  background: linear-gradient(
    90deg,
    rgb(139 92 246 / 95%),
    rgb(99 102 241 / 90%)
  );
}

.compliance-sub {
  margin-top: 8px;
  font-size: 12px;
}

.compliance-tip {
  padding: 12px;
  line-height: 1.7;
  background: rgb(30 41 59 / 25%);
  border: 1px dashed rgb(99 102 241 / 25%);
  border-radius: 14px;
}

.filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.filter-item {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-label {
  font-size: 12px;
  font-weight: 500;
  color: #94a3b8;
  cursor: help;
}

.filter-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.filter-label:hover {
  color: #a5b4fc;
}

.theme-light .filter-label {
  color: #6b7280;
}

.theme-light .filter-label:hover {
  color: #1890ff;
}

.filter-hint {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 10px;
  margin-left: 6px;
  font-size: 12px;
  line-height: 1;
  background: rgb(15 23 42 / 18%);
  border: 1px solid rgb(148 163 184 / 14%);
  border-radius: 999px;
  backdrop-filter: blur(10px);
}

.filter-hint-clickable {
  cursor: help;
  transition: all 0.2s ease;
}

.filter-hint-clickable:hover {
  background: rgb(99 102 241 / 15%);
  border-color: rgb(99 102 241 / 30%);
}

.filter-hint-icon {
  color: #1890ff;
  opacity: 0.8;
}

.filter-hint-strong {
  font-weight: 700;
  color: #e2e8f0;
}

.theme-light .filter-hint-strong {
  color: #1f2937;
}

.filter-hint-text {
  color: #94a3b8;
  white-space: nowrap;
}

.theme-light .filter-hint-text {
  color: #6b7280;
}

.filter-hint-sep {
  color: rgb(148 163 184 / 35%);
}

.filter-select :deep(.ant-select-selector) {
  background: rgb(15 23 42 / 80%) !important;
  border-color: rgb(99 102 241 / 30%) !important;
  border-radius: 8px !important;
}

.theme-light .filter-select :deep(.ant-select-selector) {
  color: #1f2937 !important;
  background: rgb(255 255 255 / 90%) !important;
  border-color: rgb(24 144 255 / 30%) !important;
}

.theme-light .filter-select :deep(.ant-select-selection-item),
.theme-light .filter-select :deep(.ant-select-selection-placeholder) {
  color: #1f2937 !important;
}

.date-picker :deep(.ant-picker) {
  background: rgb(15 23 42 / 80%) !important;
  border-color: rgb(99 102 241 / 30%) !important;
  border-radius: 8px !important;
}

.theme-light .date-picker :deep(.ant-picker) {
  color: #1f2937 !important;
  background: rgb(255 255 255 / 90%) !important;
  border-color: rgb(24 144 255 / 30%) !important;
}

.theme-light .date-picker :deep(.ant-picker input) {
  color: #1f2937 !important;
}

.theme-light .date-picker :deep(.ant-picker-suffix),
.theme-light .date-picker :deep(.ant-picker-separator) {
  color: #6b7280 !important;
}

.btn-glow {
  background: linear-gradient(135deg, #1890ff 0%, #722ed1 100%) !important;
  border: none !important;
  box-shadow: 0 4px 15px rgb(24 144 255 / 40%);
  transition: all 0.3s ease;
}

.btn-glow:hover {
  box-shadow: 0 6px 20px rgb(99 102 241 / 60%);
  transform: translateY(-2px);
}

.stat-row {
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 24px;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 16px;
  backdrop-filter: blur(20px);
  transition: all 0.3s ease;
}

.stat-card:hover {
  box-shadow: 0 12px 40px rgb(0 0 0 / 30%);
  transform: translateY(-4px);
}

.theme-light .stat-card {
  border-color: rgb(24 144 255 / 20%);
  box-shadow: 0 4px 16px rgb(0 0 0 / 6%);
}

.theme-light .stat-card:hover {
  box-shadow: 0 8px 32px rgb(0 0 0 / 12%);
}

.gradient-1 {
  background: linear-gradient(
    135deg,
    rgb(99 102 241 / 20%) 0%,
    rgb(139 92 246 / 10%) 100%
  );
  border-color: rgb(99 102 241 / 30%);
}

.gradient-2 {
  background: linear-gradient(
    135deg,
    rgb(16 185 129 / 20%) 0%,
    rgb(52 211 153 / 10%) 100%
  );
  border-color: rgb(16 185 129 / 30%);
}

.gradient-3 {
  background: linear-gradient(
    135deg,
    rgb(245 158 11 / 20%) 0%,
    rgb(251 191 36 / 10%) 100%
  );
  border-color: rgb(245 158 11 / 30%);
}

.gradient-4 {
  background: linear-gradient(
    135deg,
    rgb(6 182 212 / 20%) 0%,
    rgb(34 211 238 / 10%) 100%
  );
  border-color: rgb(6 182 212 / 30%);
}

.stat-icon {
  font-size: 36px;
  filter: drop-shadow(0 4px 8px rgb(0 0 0 / 30%));
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  color: #f1f5f9;
  text-shadow: 0 2px 10px rgb(0 0 0 / 30%);
}

.theme-light .stat-value {
  color: #1f2937;
  text-shadow: none;
}

.stat-label {
  margin-top: 4px;
  font-size: 13px;
  color: #94a3b8;
}

.theme-light .stat-label {
  color: #6b7280;
}

.chart-card {
  padding: 20px;
  margin-bottom: 20px;
  background: rgb(30 41 59 / 50%);
  border: 1px solid rgb(99 102 241 / 15%);
  border-radius: 16px;
  backdrop-filter: blur(20px);
  transition: all 0.3s ease;
}

.chart-card:hover {
  border-color: rgb(99 102 241 / 30%);
  box-shadow: 0 8px 32px rgb(99 102 241 / 10%);
}

.theme-light .chart-card {
  background: rgb(255 255 255 / 85%);
  border-color: rgb(24 144 255 / 15%);
  box-shadow: 0 4px 16px rgb(0 0 0 / 6%);
}

.theme-light .chart-card:hover {
  border-color: rgb(24 144 255 / 30%);
  box-shadow: 0 8px 32px rgb(24 144 255 / 15%);
}

.chart-card.full-width {
  width: 100%;
}

.chart-header {
  display: flex;
  gap: 12px;
  align-items: baseline;
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid rgb(148 163 184 / 10%);
}

.chart-header-actions {
  align-items: center;
  justify-content: space-between;
}

.chart-header-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.chart-hint {
  font-size: 12px;
  color: #94a3b8;
}

.heatmap-wrap {
  position: relative;
}

.heatmap-3d-container {
  width: 100%;
  height: 500px;
  overflow: hidden;
  border-radius: 12px;
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  color: #f1f5f9;
}

.theme-light .chart-title {
  color: #1f2937;
}

.chart-subtitle {
  font-size: 12px;
  color: #64748b;
}

.theme-light .chart-subtitle {
  color: #6b7280;
}

.chart-area {
  width: 100%;
}

.chart-row {
  margin-bottom: 0;
}

:deep(.ant-spin-container) {
  opacity: 1 !important;
}

:deep(.ant-spin-blur) {
  opacity: 0.3 !important;
}

/* Tooltip 内容样式 */
.tooltip-content {
  max-width: 280px;
  padding: 4px 0;
  line-height: 1.6;
}

.tooltip-content.tooltip-dimensions {
  max-width: 420px;
}

.tooltip-dim-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 8px 0;
}

.tooltip-dim-group {
  padding: 8px;
  background: rgb(99 102 241 / 8%);
  border-radius: 6px;
}

.tooltip-dim-header {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #a5b4fc;
}

.tooltip-dim-item {
  margin-bottom: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: #cbd5e1;
}

.tooltip-dim-item b {
  color: #f1f5f9;
}

.tooltip-dim-footer {
  padding-top: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: #94a3b8;
  border-top: 1px solid rgb(148 163 184 / 15%);
}

.tooltip-title {
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
}

.tooltip-desc {
  font-size: 12px;
  color: #cbd5e1;
}

.tooltip-formula {
  display: inline-block;
  padding: 2px 6px;
  margin-top: 6px;
  font-size: 11px;
  color: #a5b4fc;
  background: rgb(99 102 241 / 20%);
  border-radius: 4px;
}

/* 带帮助图标的标题 */
.chart-title-help {
  cursor: help;
}

.chart-subtitle-help {
  cursor: help;
}

/* 覆盖 Ant Design Tooltip 样式 */
:deep(.ant-tooltip-inner) {
  background: rgb(15 23 42 / 95%) !important;
  border: 1px solid rgb(99 102 241 / 30%) !important;
  border-radius: 8px !important;
  box-shadow: 0 8px 32px rgb(0 0 0 / 40%) !important;
}

:deep(.ant-tooltip-arrow::before) {
  background: rgb(15 23 42 / 95%) !important;
}
</style>
