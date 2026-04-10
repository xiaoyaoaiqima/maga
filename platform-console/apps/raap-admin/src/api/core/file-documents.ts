/**
 * 知识库文件管理 API
 * 用于上传 PDF/Word/PPT 等文档文件，并进行 AI 解析
 */
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

export namespace KnowledgeBaseFilesApi {
  /** 文档类型 */
  export type DocType = 'excel' | 'pdf' | 'ppt' | 'unknown' | 'word';

  /** 文档状态 */
  export type DocStatus = 'completed' | 'failed' | 'parsing' | 'pending';

  /** 知识库文件项 */
  export interface KnowledgeBaseFileItem {
    id: number;
    file_name: string;
    file_type: DocType;
    file_url: string;
    file_size: number;
    knowledge_base_id: number;
    knowledge_base_name: string;
    status: DocStatus;
    parse_result?: null | {
      content?: string;
      keywords?: string[];
      summary?: string;
    };
    error_message?: null | string;
    create_time: string;
    update_time?: string;
  }

  /** 知识库 */
  export interface KnowledgeBase {
    id: number;
    code: string;
    name: string;
    description?: null | string;
    file_count: number;
    enabled: number;
    create_time: string;
    update_time?: string;
  }

  /** 知识库文件列表响应 */
  export interface KnowledgeBaseFileListResponse {
    items: KnowledgeBaseFileItem[];
    total: number;
    page: number;
    page_size: number;
  }

  /** 知识库列表响应 */
  export interface KnowledgeBaseListResponse {
    items: KnowledgeBase[];
    total: number;
  }

  /** 创建知识库请求 */
  export interface CreateKnowledgeBaseRequest {
    code?: string;
    name: string;
    description?: string;
    enabled?: number;
  }

  /** 更新知识库请求 */
  export interface UpdateKnowledgeBaseRequest {
    name?: string;
    description?: string;
    enabled?: number;
  }

  /** 列表查询参数 */
  export interface KnowledgeBaseFileListParams {
    keyword?: string;
    knowledge_base_id?: number;
    file_type?: DocType;
    status?: DocStatus;
    page?: number;
    page_size: number;
  }

  /** 知识库列表查询参数 */
  export interface KnowledgeBaseListParams {
    keyword?: string;
    enabled?: boolean;
  }

  /** AI 解析请求 */
  export interface ParseRequest {
    document_ids: number[];
  }
}

// ==================== Mock 数据（开发环境） ====================

const MOCK_ENABLED = false; // 设置为 false 关闭 mock

// Mock 知识库数据
const mockKnowledgeBases: KnowledgeBaseFilesApi.KnowledgeBase[] = [
  {
    id: 1,
    code: 'marketing_docs',
    name: '营销知识库',
    description: '存放各类营销活动相关的文档资料',
    file_count: 5,
    enabled: 1,
    create_time: '2024-01-15 10:30:00',
    update_time: '2024-01-15 10:30:00',
  },
  {
    id: 2,
    code: 'product_manuals',
    name: '产品手册知识库',
    description: '产品说明、用户手册等技术文档',
    file_count: 3,
    enabled: 1,
    create_time: '2024-01-14 14:20:00',
    update_time: '2024-01-14 14:20:00',
  },
  {
    id: 3,
    code: 'training_materials',
    name: '培训资料知识库',
    description: '员工培训、学习资料等',
    file_count: 0,
    enabled: 0,
    create_time: '2024-01-13 09:15:00',
    update_time: '2024-01-13 09:15:00',
  },
];

// Mock 知识库文件数据
let mockKnowledgeBaseFiles: KnowledgeBaseFilesApi.KnowledgeBaseFileItem[] = [
  {
    id: 1,
    file_name: '2024年度营销计划.pdf',
    file_type: 'pdf',
    file_url: '/files/marketing_plan_2024.pdf',
    file_size: 2_458_000,
    knowledge_base_id: 1,
    knowledge_base_name: '营销知识库',
    status: 'completed',
    parse_result: {
      summary:
        '本文档详细阐述了2024年度的营销计划，包括目标市场分析、营销策略、预算分配和执行时间表。重点聚焦于数字化营销渠道的拓展和品牌影响力的提升。',
      keywords: ['营销计划', '数字化', '品牌', '预算', '市场分析'],
      content:
        '2024年度营销计划\n\n一、目标市场分析\n\n二、营销策略\n\n三、预算分配\n\n四、执行时间表',
    },
    error_message: null,
    create_time: '2024-01-15 10:35:00',
    update_time: '2024-01-15 10:40:00',
  },
  {
    id: 2,
    file_name: '产品介绍PPT.pptx',
    file_type: 'ppt',
    file_url: '/files/product_intro.pptx',
    file_size: 5_670_000,
    knowledge_base_id: 1,
    knowledge_base_name: '营销知识库',
    status: 'completed',
    parse_result: {
      summary:
        '产品介绍演示文稿，包含产品特性、技术参数、应用场景和竞争优势等内容。',
      keywords: ['产品', '介绍', '特性', '竞争优势'],
    },
    error_message: null,
    create_time: '2024-01-15 11:00:00',
    update_time: '2024-01-15 11:05:00',
  },
  {
    id: 3,
    file_name: '用户调研报告.docx',
    file_type: 'word',
    file_url: '/files/user_research.docx',
    file_size: 890_000,
    knowledge_base_id: 1,
    knowledge_base_name: '营销知识库',
    status: 'pending',
    parse_result: null,
    error_message: null,
    create_time: '2024-01-15 14:20:00',
    update_time: '2024-01-15 14:20:00',
  },
  {
    id: 4,
    file_name: '竞品分析表.xlsx',
    file_type: 'excel',
    file_url: '/files/competitor_analysis.xlsx',
    file_size: 125_000,
    knowledge_base_id: 1,
    knowledge_base_name: '营销知识库',
    status: 'failed',
    parse_result: null,
    error_message: '文件格式不支持解析',
    create_time: '2024-01-15 15:10:00',
    update_time: '2024-01-15 15:15:00',
  },
  {
    id: 5,
    file_name: 'Q1活动总结.pdf',
    file_type: 'pdf',
    file_url: '/files/q1_summary.pdf',
    file_size: 1_780_000,
    knowledge_base_id: 1,
    knowledge_base_name: '营销知识库',
    status: 'completed',
    parse_result: {
      summary: '第一季度营销活动总结报告，包含活动数据、效果评估和改进建议。',
      keywords: ['Q1', '活动总结', '数据分析', '效果评估'],
    },
    error_message: null,
    create_time: '2024-01-16 09:30:00',
    update_time: '2024-01-16 09:35:00',
  },
  {
    id: 6,
    file_name: '产品使用手册.pdf',
    file_type: 'pdf',
    file_url: '/files/user_manual.pdf',
    file_size: 3_450_000,
    knowledge_base_id: 2,
    knowledge_base_name: '产品手册知识库',
    status: 'completed',
    parse_result: {
      summary: '产品使用手册，详细介绍了产品的安装、配置和使用方法。',
      keywords: ['使用手册', '安装', '配置', '操作指南'],
    },
    error_message: null,
    create_time: '2024-01-14 15:00:00',
    update_time: '2024-01-14 15:10:00',
  },
  {
    id: 7,
    file_name: '技术规格说明书.docx',
    file_type: 'word',
    file_url: '/files/tech_spec.docx',
    file_size: 1_230_000,
    knowledge_base_id: 2,
    knowledge_base_name: '产品手册知识库',
    status: 'parsing',
    parse_result: null,
    error_message: null,
    create_time: '2024-01-14 16:00:00',
    update_time: '2024-01-14 16:00:00',
  },
  {
    id: 8,
    file_name: '常见问题解答.pdf',
    file_type: 'pdf',
    file_url: '/files/faq.pdf',
    file_size: 890_000,
    knowledge_base_id: 2,
    knowledge_base_name: '产品手册知识库',
    status: 'completed',
    parse_result: {
      summary: '常见问题解答文档，汇总了用户反馈的高频问题及解决方案。',
      keywords: ['FAQ', '常见问题', '解答', '故障排除'],
    },
    error_message: null,
    create_time: '2024-01-14 17:00:00',
    update_time: '2024-01-14 17:05:00',
  },
];

let nextKnowledgeBaseId = 4;
let nextKnowledgeBaseFileId = 9;

// 模拟延迟
function delay(ms: number = 500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ==================== API 函数 ====================

/**
 * 获取知识库列表
 */
export async function listKnowledgeBasesApi(
  params?: KnowledgeBaseFilesApi.KnowledgeBaseListParams,
): Promise<KnowledgeBaseFilesApi.KnowledgeBaseListResponse> {
  if (MOCK_ENABLED) {
    await delay();
    let items = [...mockKnowledgeBases];

    if (params?.keyword) {
      const kw = params.keyword.toLowerCase();
      items = items.filter(
        (p) =>
          p.name.toLowerCase().includes(kw) ||
          p.code.toLowerCase().includes(kw),
      );
    }

    if (params?.enabled !== undefined) {
      items = items.filter((p) => (p.enabled === 1) === params.enabled);
    }

    return { items, total: items.length };
  }

  return requestClient.get<KnowledgeBaseFilesApi.KnowledgeBaseListResponse>(
    '/v1/knowledge-bases',
    { params },
  );
}

/**
 * 获取单个知识库详情
 *
 * 后端返回: {code: 200, data: {pool: {...}, files: [...]}}
 * 前端 requestClient 的 defaultResponseInterceptor 会自动提取 data 字段
 * 所以这里需要从响应中提取 pool 对象
 */
export async function getKnowledgeBaseApi(
  id: number,
): Promise<KnowledgeBaseFilesApi.KnowledgeBase> {
  if (MOCK_ENABLED) {
    await delay();
    const knowledgeBase = mockKnowledgeBases.find((p) => p.id === id);
    if (!knowledgeBase) {
      throw new Error('知识库不存在');
    }
    return knowledgeBase;
  }

  // 后端返回 {code: 200, data: {pool: {...}, files: [...]}}
  // requestClient 会自动提取 data，所以得到 {pool: {...}, files: [...]}
  const response = await requestClient.get<{
    files: any[];
    pool: KnowledgeBaseFilesApi.KnowledgeBase;
  }>(`/v1/knowledge-bases/${id}`);
  // 从响应中提取 pool 对象（注意后端字段名是 pool 不是 knowledge_base）
  return response.pool;
}

/**
 * 创建知识库
 */
export async function createKnowledgeBaseApi(
  data: KnowledgeBaseFilesApi.CreateKnowledgeBaseRequest,
): Promise<KnowledgeBaseFilesApi.KnowledgeBase> {
  if (MOCK_ENABLED) {
    await delay();
    const newKnowledgeBase: KnowledgeBaseFilesApi.KnowledgeBase = {
      id: nextKnowledgeBaseId++,
      code: data.code || `knowledge_base_${Date.now()}`,
      name: data.name,
      description: data.description || null,
      file_count: 0,
      enabled: data.enabled ?? 1,
      create_time: new Date()
        .toLocaleString('zh-CN', {
          hour12: false,
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
        .replaceAll('/', '-'),
      update_time: new Date()
        .toLocaleString('zh-CN', {
          hour12: false,
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
        .replaceAll('/', '-'),
    };
    mockKnowledgeBases.push(newKnowledgeBase);
    return newKnowledgeBase;
  }

  return requestClient.post<KnowledgeBaseFilesApi.KnowledgeBase>(
    '/v1/knowledge-bases',
    data,
  );
}

/**
 * 更新知识库
 */
export async function updateKnowledgeBaseApi(
  id: number,
  data: KnowledgeBaseFilesApi.UpdateKnowledgeBaseRequest,
): Promise<KnowledgeBaseFilesApi.KnowledgeBase> {
  if (MOCK_ENABLED) {
    await delay();
    const knowledgeBase = mockKnowledgeBases.find((p) => p.id === id);
    if (!knowledgeBase) {
      throw new Error('知识库不存在');
    }
    if (data.name !== undefined) knowledgeBase.name = data.name;
    if (data.description !== undefined)
      knowledgeBase.description = data.description;
    if (data.enabled !== undefined) knowledgeBase.enabled = data.enabled;
    knowledgeBase.update_time = new Date()
      .toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
      .replaceAll('/', '-');
    return knowledgeBase;
  }

  return requestClient.put<KnowledgeBaseFilesApi.KnowledgeBase>(
    `/v1/knowledge-bases/${id}`,
    data,
  );
}

/**
 * 删除知识库
 */
export async function deleteKnowledgeBaseApi(
  id: number,
): Promise<{ deleted: boolean }> {
  if (MOCK_ENABLED) {
    await delay();
    const idx = mockKnowledgeBases.findIndex((p) => p.id === id);
    if (idx === -1) {
      throw new Error('知识库不存在');
    }
    mockKnowledgeBases.splice(idx, 1);
    // 同时删除该知识库下的所有文件
    mockKnowledgeBaseFiles = mockKnowledgeBaseFiles.filter(
      (d) => d.knowledge_base_id !== id,
    );
    return { deleted: true };
  }

  return requestClient.delete<{ deleted: boolean }>(
    `/v1/knowledge-bases/${id}`,
  );
}

/**
 * 切换知识库启用状态
 */
export async function toggleKnowledgeBaseEnabledApi(
  id: number,
): Promise<KnowledgeBaseFilesApi.KnowledgeBase> {
  if (MOCK_ENABLED) {
    await delay();
    const knowledgeBase = mockKnowledgeBases.find((p) => p.id === id);
    if (!knowledgeBase) {
      throw new Error('知识库不存在');
    }
    knowledgeBase.enabled = knowledgeBase.enabled === 1 ? 0 : 1;
    knowledgeBase.update_time = new Date()
      .toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
      .replaceAll('/', '-');
    return knowledgeBase;
  }

  return requestClient.put<KnowledgeBaseFilesApi.KnowledgeBase>(
    `/v1/knowledge-bases/${id}/toggle`,
  );
}

/**
 * 获取知识库文件列表
 */
export async function listKnowledgeBaseFilesApi(
  knowledgeBaseId: number,
  params: KnowledgeBaseFilesApi.KnowledgeBaseFileListParams,
): Promise<KnowledgeBaseFilesApi.KnowledgeBaseFileListResponse> {
  if (MOCK_ENABLED) {
    await delay();
    let items = mockKnowledgeBaseFiles.filter(
      (d) => d.knowledge_base_id === knowledgeBaseId,
    );

    if (params.keyword) {
      const kw = params.keyword.toLowerCase();
      items = items.filter((d) => d.file_name.toLowerCase().includes(kw));
    }

    if (params.file_type) {
      items = items.filter((d) => d.file_type === params.file_type);
    }

    if (params.status) {
      items = items.filter((d) => d.status === params.status);
    }

    const total = items.length;
    const page = params.page ?? 1;
    const pageSize = params.page_size;
    const start = (page - 1) * pageSize;
    const pagedItems = items.slice(start, start + pageSize);

    return {
      items: pagedItems,
      total,
      page,
      page_size: pageSize,
    };
  }

  return requestClient.get<KnowledgeBaseFilesApi.KnowledgeBaseFileListResponse>(
    `/v1/knowledge-bases/${knowledgeBaseId}/files`,
    { params },
  );
}

/**
 * 上传知识库文件
 */
export async function uploadKnowledgeBaseFileApi(
  knowledgeBaseId: number,
  file: File,
): Promise<KnowledgeBaseFilesApi.KnowledgeBaseFileItem> {
  if (MOCK_ENABLED) {
    await delay(1000);
    const knowledgeBase = mockKnowledgeBases.find(
      (p) => p.id === knowledgeBaseId,
    );
    if (!knowledgeBase) {
      throw new Error('知识库不存在');
    }

    // 根据文件扩展名判断类型
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    let fileType: KnowledgeBaseFilesApi.DocType = 'unknown';
    if (ext === 'pdf') fileType = 'pdf';
    else if (['doc', 'docx'].includes(ext)) fileType = 'word';
    else if (['ppt', 'pptx'].includes(ext)) fileType = 'ppt';
    else if (['xls', 'xlsx'].includes(ext)) fileType = 'excel';

    const newFile: KnowledgeBaseFilesApi.KnowledgeBaseFileItem = {
      id: nextKnowledgeBaseFileId++,
      file_name: file.name,
      file_type: fileType,
      file_url: `/files/${file.name}`,
      file_size: file.size,
      knowledge_base_id: knowledgeBaseId,
      knowledge_base_name: knowledgeBase.name,
      status: 'pending',
      parse_result: null,
      error_message: null,
      create_time: new Date()
        .toLocaleString('zh-CN', {
          hour12: false,
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
        .replaceAll('/', '-'),
      update_time: new Date()
        .toLocaleString('zh-CN', {
          hour12: false,
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
        .replaceAll('/', '-'),
    };

    mockKnowledgeBaseFiles.push(newFile);
    knowledgeBase.file_count++;

    return newFile;
  }

  const formData = new FormData();
  formData.append('file', file);

  // 后端路由是 /v1/knowledge-bases/{base_id}/upload
  return requestClient.post<KnowledgeBaseFilesApi.KnowledgeBaseFileItem>(
    `/v1/knowledge-bases/${knowledgeBaseId}/upload`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  );
}

/**
 * 批量上传知识库文件
 */
export async function uploadKnowledgeBaseFilesApi(
  knowledgeBaseId: number,
  files: File[],
): Promise<{
  error_count: number;
  results: KnowledgeBaseFilesApi.KnowledgeBaseFileItem[];
  success_count: number;
}> {
  if (MOCK_ENABLED) {
    await delay(1000 * files.length);
    const results: KnowledgeBaseFilesApi.KnowledgeBaseFileItem[] = [];
    let success_count = 0;
    let error_count = 0;

    for (const file of files) {
      try {
        const fileItem = await uploadKnowledgeBaseFileApi(
          knowledgeBaseId,
          file,
        );
        results.push(fileItem);
        success_count++;
      } catch {
        error_count++;
      }
    }

    return { success_count, error_count, results };
  }

  // 后端没有批量上传接口，循环调用单个上传
  const results: KnowledgeBaseFilesApi.KnowledgeBaseFileItem[] = [];
  let success_count = 0;
  let error_count = 0;

  for (const file of files) {
    try {
      const result = await uploadKnowledgeBaseFileApi(knowledgeBaseId, file);
      results.push(result);
      success_count++;
    } catch {
      error_count++;
    }
  }

  return { success_count, error_count, results };
}

/**
 * 删除知识库文件
 */
export async function deleteKnowledgeBaseFileApi(
  fileId: number,
): Promise<{ deleted: boolean }> {
  if (MOCK_ENABLED) {
    await delay();
    const idx = mockKnowledgeBaseFiles.findIndex((d) => d.id === fileId);
    if (idx === -1) {
      throw new Error('文件不存在');
    }

    const file = mockKnowledgeBaseFiles[idx];
    const knowledgeBase = mockKnowledgeBases.find(
      (p) => p.id === file?.knowledge_base_id,
    );
    if (knowledgeBase && knowledgeBase.file_count > 0) {
      knowledgeBase.file_count--;
    }

    mockKnowledgeBaseFiles.splice(idx, 1);
    return { deleted: true };
  }

  return requestClient.delete<{ deleted: boolean }>(
    `/v1/knowledge-base-files/${fileId}`,
  );
}

/**
 * AI 解析知识库文件
 */
export async function parseKnowledgeBaseFilesApi(
  data: KnowledgeBaseFilesApi.ParseRequest,
): Promise<{ failed: number; success: number }> {
  if (MOCK_ENABLED) {
    await delay(2000);
    let success = 0;
    let failed = 0;

    for (const id of data.document_ids) {
      const file = mockKnowledgeBaseFiles.find((d) => d.id === id);
      if (file && (file.status === 'pending' || file.status === 'failed')) {
        // 模拟解析结果
        file.status = 'completed';
        file.parse_result = {
          summary: `AI 自动解析结果：${file.file_name} 是一份关于${file.file_type}格式的文件。`,
          keywords: ['关键词1', '关键词2', '关键词3'],
          content: '解析后的文本内容将在这里显示...',
        };
        file.error_message = null;
        file.update_time = new Date()
          .toLocaleString('zh-CN', {
            hour12: false,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })
          .replaceAll('/', '-');
        success++;
      } else {
        failed++;
      }
    }

    return { success, failed };
  }

  return requestClient.post<{ failed: number; success: number }>(
    '/v1/knowledge-base-files/parse/batch',
    data,
  );
}

/**
 * 重新解析单个知识库文件
 */
export async function reparseKnowledgeBaseFileApi(
  fileId: number,
): Promise<KnowledgeBaseFilesApi.KnowledgeBaseFileItem> {
  if (MOCK_ENABLED) {
    await delay(2000);
    const file = mockKnowledgeBaseFiles.find((d) => d.id === fileId);
    if (!file) {
      throw new Error('文件不存在');
    }

    file.status = 'completed';
    file.parse_result = {
      summary: `重新解析结果：${file.file_name}`,
      keywords: ['新关键词1', '新关键词2'],
      content: '重新解析后的内容...',
    };
    file.error_message = null;
    file.update_time = new Date()
      .toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
      .replaceAll('/', '-');

    return file;
  }

  return requestClient.post<KnowledgeBaseFilesApi.KnowledgeBaseFileItem>(
    `/v1/knowledge-base-files/${fileId}/parse`,
  );
}
