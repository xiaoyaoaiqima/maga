export interface TemplateField {
  key: string;
  label: string;
  type: 'input' | 'select' | 'textarea';
  required: boolean;
  placeholder?: string;
  options?: string[];
}

export interface CorpusTemplate {
  id: number;
  code: string;
  name: string;
  category_type: string;
  fields: TemplateField[];
  description?: string;
  tenant_code: string;
  create_time?: string;
  update_time?: string;
  node_count?: number; // 使用该模板的节点数量
}

export interface TemplateFormData {
  code?: string; // 可选，未传时由前端自动生成（格式：分类类型_名称）或后端自动生成（template-xxx）
  name: string;
  category_type: string;
  description: string;
  tenant_code: string;
  fields: TemplateField[];
}

export interface CategoryTypeOption {
  value: string;
  label: string;
}

export interface TenantOption {
  label: string;
  value: string;
}
