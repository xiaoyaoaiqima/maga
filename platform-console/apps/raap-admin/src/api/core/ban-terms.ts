import { requestClient } from '#/api/request';

export namespace BanTermApi {
  export type ListType = 'BLACKLIST' | 'WHITELIST';

  export interface TermItem {
    id: number;
    tenant_code: string;
    term: string;
    list_type: ListType;
    category: string;
    enabled: boolean;
    create_time?: null | string;
    update_time?: null | string;
    created_by?: null | string;
    updated_by?: null | string;
  }

  export interface PageInfo {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  }

  export interface ListResponse {
    items: TermItem[];
    page_info: PageInfo;
  }

  export interface Meta {
    active_version: number;
    whitelist_count: number;
    blacklist_count: number;
  }

  /** 筛选选项（从后端动态获取） */
  export interface Options {
    tenant_codes: string[];
    categories: string[];
    list_types: string[];
  }

  export interface ListParams {
    page?: number;
    page_size?: number;
    tenant_code?: string;
    keyword?: string;
    list_type?: ListType;
    category?: string;
    enabled?: boolean;
  }

  export interface CreatePayload {
    tenant_code: string;
    term: string;
    list_type: ListType;
    category: string;
    enabled: boolean;
  }

  export interface UpdatePayload {
    tenant_code?: string;
    term?: string;
    list_type?: ListType;
    category?: string;
    enabled?: boolean;
  }
}

export async function listBanTermsApi(params?: BanTermApi.ListParams) {
  // requestClient 会自动提取后端 JSON 的 data 字段，因此这里直接拿到 ListResponse
  return requestClient.get<BanTermApi.ListResponse>(
    '/v1/keyword-corpus/ban-terms',
    {
      params,
    },
  );
}

export async function createBanTermApi(payload: BanTermApi.CreatePayload) {
  return requestClient.post<BanTermApi.TermItem>(
    '/v1/keyword-corpus/ban-terms',
    payload,
  );
}

export async function updateBanTermApi(
  term_id: number,
  payload: BanTermApi.UpdatePayload,
) {
  return requestClient.put<BanTermApi.TermItem>(
    `/v1/keyword-corpus/ban-terms/${term_id}`,
    payload,
  );
}

export async function deleteBanTermApi(term_id: number) {
  return requestClient.delete<{ deleted: boolean }>(
    `/v1/keyword-corpus/ban-terms/${term_id}`,
  );
}

export async function getBanTermMetaApi() {
  return requestClient.get<BanTermApi.Meta>(
    '/v1/keyword-corpus/ban-terms/meta',
  );
}

/** 获取筛选选项（分类、名单类型）*/
export async function getBanTermOptionsApi() {
  return requestClient.get<BanTermApi.Options>(
    '/v1/keyword-corpus/ban-terms/options',
  );
}

export async function publishBanTermsApi() {
  return requestClient.post<{ active_version: number }>(
    '/v1/keyword-corpus/ban-terms/publish',
  );
}
