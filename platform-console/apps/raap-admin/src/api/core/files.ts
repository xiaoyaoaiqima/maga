/**
 * 文件上传 API
 */
import { requestClient } from '#/api/request';

export namespace FilesApi {
  /** 单个上传结果 */
  export interface UploadResult {
    url: string;
    filename: string;
    size: number;
    content_type: string;
  }

  /** 批量上传结果 */
  export interface BatchUploadResult {
    success_count: number;
    error_count: number;
    results: Array<{
      filename: string;
      index: number;
      url: string;
    }>;
    errors: Array<{
      error: string;
      filename: string;
      index: number;
    }>;
  }
}

/**
 * 上传单个图片
 */
export async function uploadImageApi(file: File) {
  const formData = new FormData();
  formData.append('file', file);

  return requestClient.post<FilesApi.UploadResult>(
    '/v1/files/upload/image',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  );
}

/**
 * 批量上传图片
 */
export async function uploadImagesApi(files: File[]) {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  return requestClient.post<FilesApi.BatchUploadResult>(
    '/v1/files/upload/images',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  );
}
