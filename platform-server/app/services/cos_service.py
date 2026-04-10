"""
腾讯云 COS 文件上传服务
"""

import datetime
import logging
import mimetypes
import uuid
from typing import Optional

from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError

from app.core.config import settings

logger = logging.getLogger(__name__)


class CosService:
    """腾讯云 COS 文件服务"""

    def __init__(self):
        self.client = CosS3Client(
            CosConfig(
                Secret_id=settings.COS_SECRET_ID,
                Secret_key=settings.COS_SECRET_KEY,
                Region=settings.COS_REGION,
            )
        )
        self.bucket_name = settings.COS_BUCKET_NAME
        self.domain = settings.COS_DOMAIN

    def _get_content_type(self, file_name: str) -> str:
        """根据文件名获取 Content-Type"""
        content_type, _ = mimetypes.guess_type(file_name)
        if content_type:
            return content_type

        ext = file_name.split(".")[-1].lower() if "." in file_name else ""
        mime_mapping = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
            "svg": "image/svg+xml",
        }
        return mime_mapping.get(ext, "application/octet-stream")

    def _generate_file_path(self, file_name: str, prefix: str = "test-case") -> str:
        """生成文件存储路径"""
        now = datetime.datetime.now()
        date_path = now.strftime("%Y/%m/%d")
        unique_id = uuid.uuid4().hex[:8]
        ext = file_name.split(".")[-1] if "." in file_name else "bin"
        new_name = f"{unique_id}.{ext}"
        return f"raap/{prefix}/{date_path}/{new_name}"

    def upload_file(
        self,
        file_data: bytes,
        file_name: str,
        prefix: str = "test-case",
    ) -> Optional[str]:
        """
        上传文件到 COS

        Args:
            file_data: 文件二进制数据
            file_name: 原始文件名
            prefix: 路径前缀

        Returns:
            成功返回完整 URL，失败返回 None
        """
        try:
            file_path = self._generate_file_path(file_name, prefix)
            content_type = self._get_content_type(file_name)

            upload_params = {
                "Bucket": self.bucket_name,
                "Key": file_path,
                "Body": file_data,
                "ContentType": content_type,
            }

            # 图片设置缓存和内联显示
            if content_type.startswith("image/"):
                upload_params["CacheControl"] = "max-age=31536000"
                upload_params["ContentDisposition"] = "inline"

            self.client.put_object(**upload_params)
            file_url = f"{self.domain}/{file_path}"
            logger.info(f"文件上传成功: {file_url}")
            return file_url

        except CosServiceError as e:
            logger.error(f"COS 服务错误: {e}")
            return None
        except CosClientError as e:
            logger.error(f"COS 客户端错误: {e}")
            return None
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            return None


# 单例
_cos_service: Optional[CosService] = None


def get_cos_service() -> CosService:
    """获取 COS 服务实例"""
    global _cos_service
    if _cos_service is None:
        _cos_service = CosService()
    return _cos_service

