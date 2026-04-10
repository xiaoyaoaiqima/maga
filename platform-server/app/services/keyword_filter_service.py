"""
KeywordFilterService - 基于精确字符串匹配的违禁词审核服务

核心职责：
- 精确匹配，无 AI 幻觉
- 白名单豁免
- 黑名单拦截
- 使用所有租户的词表（从 ban_term 表加载，不按租户隔离）
- 返回格式与 Critic 一致 (score: 0/1, reason, problem_tags, problem_snippets)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ban_term import BanTerm, BanTermMeta


@dataclass
class TenantTermCache:
    """单个租户的词表缓存"""
    whitelist: Set[str] = field(default_factory=set)
    blacklist: Set[str] = field(default_factory=set)
    whitelist_sorted: List[str] = field(default_factory=list)
    blacklist_sorted: List[str] = field(default_factory=list)


class KeywordFilterService:
    """违禁词精确匹配服务（使用所有租户的词表）"""

    def __init__(self):
        # DB 热更新控制
        self._refresh_lock = asyncio.Lock()
        self._active_version: int | None = None

        # 全局词表缓存（合并所有租户的词表）
        self._global_cache: TenantTermCache = TenantTermCache()

    def _get_global_cache(self) -> TenantTermCache:
        """获取全局词表缓存（包含所有租户的词表）"""
        return self._global_cache

    async def refresh_from_db(self, *, session: AsyncSession) -> bool:
        """从 DB 刷新全局词表（合并所有租户的词表）。

        约定：
        - `ban_term_meta` 单行表，固定 `id=1`
        - 仅当 `active_version` 变化时才会重新拉取全量词条
        - 合并所有租户的词表，不按租户隔离

        Returns:
            True 表示发生了刷新；False 表示无需刷新或刷新失败（沿用旧缓存）
        """
        async with self._refresh_lock:
            try:
                meta = await session.get(BanTermMeta, 1)
                if meta is None:
                    meta = BanTermMeta(id=1, active_version=1)
                    session.add(meta)
                    await session.flush()

                desired_version = int(meta.active_version or 0)
                if self._active_version == desired_version:
                    return False

                # 拉取所有启用的词条（不区分租户）
                stmt = (
                    select(BanTerm.term, BanTerm.list_type)
                    .where(and_(BanTerm.enabled.is_(True), BanTerm.is_deleted == 0))
                )
                result = await session.execute(stmt)
                rows = result.all()

                # 合并所有租户的词表
                global_whitelist: Set[str] = set()
                global_blacklist: Set[str] = set()
                
                for term, list_type in rows:
                    if not term or not list_type:
                        continue

                    list_type_upper = str(list_type).upper()
                    if list_type_upper == "WHITELIST":
                        global_whitelist.add(str(term))
                    elif list_type_upper == "BLACKLIST":
                        global_blacklist.add(str(term))

                # 防御：避免 DB 误操作导致"清空词表"直接放行
                if not global_whitelist and not global_blacklist:
                    logger.warning("[KeywordFilter] DB 词表为空，跳过刷新（沿用旧缓存）")
                    return False

                # 构建全局缓存（合并所有租户的词表）
                new_cache = TenantTermCache(
                    whitelist=global_whitelist,
                    blacklist=global_blacklist,
                    whitelist_sorted=sorted(global_whitelist, key=len, reverse=True),
                    blacklist_sorted=sorted(global_blacklist, key=len, reverse=True),
                )

                # 原子替换
                self._global_cache = new_cache
                self._active_version = desired_version

                logger.info(
                    f"[KeywordFilter] 全局词表已刷新: version={desired_version}, "
                    f"whitelist={len(global_whitelist)}, blacklist={len(global_blacklist)}"
                )
                return True
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[KeywordFilter] 刷新词表失败，沿用旧缓存: {e}")
                return False

    def preprocess_text(self, text: str) -> str:
        """
        Step 1: 文本预处理
        移除干扰符号（空格、特殊字符），但保留 emoji
        """
        noise_pattern = r'[\s\-\/\*\_\|\~\·\.\,\，\。\！\？\!\?\:\：\;\；\"\"\'\'\「\」\『\』\【\】\(\)\（\）\<\>\《\》]'
        cleaned = re.sub(noise_pattern, '', text)
        return cleaned

    def mark_whitelist_positions(
        self, text: str, whitelist_sorted: List[str]
    ) -> tuple[Set[int], Set[str]]:
        """
        Step 2: 标记白名单词覆盖的位置

        白名单词优先保护：覆盖的位置不会被黑名单匹配
        例如："免疫球蛋白" 覆盖后，不会被 "免疫力" 误判

        Returns:
            (protected_positions, matched_whitelist_words)
        """
        protected_positions: Set[int] = set()
        matched_words: Set[str] = set()

        for word in whitelist_sorted:  # 按长度降序，最长优先
            pos = 0
            while True:
                idx = text.find(word, pos)
                if idx == -1:
                    break

                # 标记该词覆盖的所有位置为"受保护"
                for i in range(idx, idx + len(word)):
                    protected_positions.add(i)

                matched_words.add(word)
                pos = idx + 1

        return protected_positions, matched_words

    def check_blacklist(
        self, text: str, protected_positions: Set[int], blacklist_sorted: List[str]
    ) -> List[str]:
        """
        Step 3: 检查黑名单（跳过白名单保护的位置）

        Args:
            text: 预处理后的文本（用于匹配）
            protected_positions: 白名单保护的位置集合
            blacklist_sorted: 按长度降序排列的黑名单

        Returns:
            List[str]: 匹配到的违禁词列表
        """
        violations: List[str] = []
        matched_positions: Set[int] = set()

        for word in blacklist_sorted:  # 按长度降序，最长优先
            pos = 0
            while True:
                idx = text.find(word, pos)
                if idx == -1:
                    break

                word_positions = set(range(idx, idx + len(word)))

                # 检查是否被白名单保护
                if word_positions & protected_positions:
                    pos = idx + 1
                    continue

                # 检查是否已被更长的黑名单词匹配
                if word_positions & matched_positions:
                    pos = idx + 1
                    continue

                # 标记位置为已匹配
                matched_positions.update(word_positions)
                violations.append(word)
                pos = idx + 1

        return violations

    def filter_with_custom_keywords(
        self, content: str, keywords_str: str, tenant_code: str = "default"
    ) -> Dict[str, Any]:
        """
        使用自定义违禁词列表进行过滤（从 prompt 传入）

        Args:
            content: 待审核的文本内容
            keywords_str: 逗号分隔的违禁词字符串，如 "赌博,暴力,色情"
            tenant_code: 租户编码（仅用于日志）

        Returns:
            {
                "score": 1 (合规) / 0 (违规),
                "reason": str,
                "problem_tags": List[str],      # 违规类型标签（此处固定为 ["违禁词"]）
                "problem_snippets": List[str],  # 命中的具体违禁词（用于前端高亮）
            }
        """
        if not content or not content.strip():
            return {
                "score": 1,
                "reason": "空内容，合规",
                "problem_tags": [],
                "problem_snippets": [],
            }

        # 解析自定义关键词列表（支持换行、逗号、空格等分隔符）
        import re
        keywords = re.split(r'[\n,，\s]+', keywords_str.strip()) if keywords_str else []
        keywords = [kw.strip() for kw in keywords if kw.strip()]

        if not keywords:
            logger.warning(f"[KeywordFilter] 自定义关键词列表为空，默认放行")
            return {
                "score": 1,
                "reason": "自定义关键词列表为空，默认放行",
                "problem_tags": [],
                "problem_snippets": [],
            }

        logger.info(f"[KeywordFilter] 使用自定义关键词列表: {keywords}")

        # Step 1: 预处理
        processed_text = self.preprocess_text(content)
        logger.info(
            f"[KeywordFilter] 🔍 开始过滤: tenant_code={tenant_code}, "
            f"原文长度: {len(content)}, "
            f"预处理后: {len(processed_text)}, "
            f"违禁词数量: {len(keywords)}, "
            f"违禁词列表: {keywords}"
        )

        # Step 2: 直接检查关键词（跳过白名单保护，因为自定义关键词通常是绝对红线）
        violations = []
        matched_positions = set()

        # 按长度降序排序，优先匹配更长的词
        keywords_sorted = sorted(keywords, key=len, reverse=True)

        for word in keywords_sorted:
            pos = 0
            while True:
                idx = processed_text.find(word, pos)
                if idx == -1:
                    break

                word_positions = set(range(idx, idx + len(word)))

                # 检查是否已被更长的关键词匹配
                if word_positions & matched_positions:
                    pos = idx + 1
                    continue

                # 标记位置为已匹配
                matched_positions.update(word_positions)
                violations.append(word)
                pos = idx + 1

        if not violations:
            return {
                "score": 1,
                "reason": f"未检测到违禁词（检查了 {len(keywords)} 个关键词），合规",
                "problem_tags": [],
                "problem_snippets": [],
            }

        # 去重
        matched_keywords = list(dict.fromkeys(violations))

        reason = f"检测到 {len(matched_keywords)} 个违禁词: {', '.join(matched_keywords[:5])}"
        if len(matched_keywords) > 5:
            reason += f" 等共 {len(matched_keywords)} 个"

        logger.warning(
            f"[KeywordFilter] ❌ 违规! tenant_code={tenant_code}, "
            f"传入违禁词列表={keywords}, "
            f"命中违禁词={matched_keywords}, "
            f"命中数量={len(matched_keywords)}"
        )

        return {
            "score": 0,
            "reason": reason,
            "problem_tags": ["违禁词"],
            "problem_snippets": matched_keywords,
        }

    def filter(self, content: str, tenant_code: str = "default") -> Dict[str, Any]:
        """
        主入口：执行违禁词过滤（使用所有租户的词表）

        Args:
            content: 待审核的文本内容
            tenant_code: 租户编码（保留参数以兼容 API，但不再使用）

        Returns:
            {
                "score": 1 (合规) / 0 (违规),
                "reason": str,
                "problem_tags": List[str],      # 违规类型标签（此处固定为 ["违禁词"]）
                "problem_snippets": List[str],  # 命中的具体违禁词（用于前端高亮）
            }
        """
        if not content or not content.strip():
            return {
                "score": 1,
                "reason": "空内容，合规",
                "problem_tags": [],
                "problem_snippets": [],
            }

        # 获取全局词表（包含所有租户的词表）
        cache = self._get_global_cache()
        if not cache.whitelist and not cache.blacklist:
            logger.warning("[KeywordFilter] 全局词表为空，默认放行")
            return {
                "score": 1,
                "reason": "全局词表为空，默认放行",
                "problem_tags": [],
                "problem_snippets": [],
            }

        # Step 1: 预处理
        processed_text = self.preprocess_text(content)
        logger.debug(f"[KeywordFilter] tenant_code={tenant_code}, 原文长度: {len(content)}, 预处理后: {len(processed_text)}")

        # Step 2: 白名单位置标记（保护区域，不会被黑名单匹配）
        protected_positions, whitelist_hits = self.mark_whitelist_positions(
            processed_text, cache.whitelist_sorted
        )
        if whitelist_hits:
            logger.debug(f"[KeywordFilter] 命中白名单（受保护）: {whitelist_hits}")

        # Step 3: 黑名单检查（跳过白名单保护的位置）
        violations = self.check_blacklist(
            processed_text, protected_positions, cache.blacklist_sorted
        )

        if not violations:
            reason = "未检测到违禁词，合规"
            if whitelist_hits:
                safe_words = list(whitelist_hits)[:5]
                reason = f"命中安全词（白名单）: {', '.join(safe_words)}，合规"
                if len(whitelist_hits) > 5:
                    reason += f" 等共 {len(whitelist_hits)} 个"
            return {
                "score": 1,
                "reason": reason,
                "problem_tags": [],
                "problem_snippets": [],
            }

        # 去重
        matched_keywords = list(dict.fromkeys(violations))

        reason = f"检测到 {len(matched_keywords)} 个违禁词: {', '.join(matched_keywords[:5])}"
        if len(matched_keywords) > 5:
            reason += f" 等共 {len(matched_keywords)} 个"

        logger.warning(
            f"[KeywordFilter] ❌ 违规! tenant_code={tenant_code}, "
            f"全局黑名单词表大小={len(cache.blacklist)}, "
            f"命中违禁词={matched_keywords}, "
            f"命中数量={len(matched_keywords)}"
        )

        return {
            "score": 0,
            "reason": reason,
            "problem_tags": ["违禁词"],
            "problem_snippets": matched_keywords,
        }


# 全局单例
_keyword_filter_service: KeywordFilterService | None = None


def get_keyword_filter_service() -> KeywordFilterService:
    """获取单例"""
    global _keyword_filter_service
    if _keyword_filter_service is None:
        _keyword_filter_service = KeywordFilterService()
    return _keyword_filter_service
