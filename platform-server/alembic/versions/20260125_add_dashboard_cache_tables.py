"""add dashboard cache tables

Revision ID: 011_add_dashboard_cache
Revises: 010_add_content_pool_fields
Create Date: 2026-01-25

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260125_add_dashboard_cache"
down_revision: Union[str, Sequence[str], None] = "20260121_add_logic_expert"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 Dashboard 数据缓存系统的 6 张表"""

    # 1. 缓存主表
    op.execute("""
        CREATE TABLE IF NOT EXISTS `raap_dashboard_data_cache_response` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
            `cache_key` VARCHAR(255) NOT NULL COMMENT 'Physical key (MD5)',
            `logical_key` VARCHAR(500) NOT NULL COMMENT 'Logical key (semantic, e.g., "metric_cost:2025-01-01:2025-01-31")',
            `cache_group` VARCHAR(100) NOT NULL COMMENT 'Cache group (e.g., "dashboard_summary", "metric_query")',
            `response_data` JSON DEFAULT NULL COMMENT 'Uncompressed (small data, <100KB)',
            `response_compressed` LONGBLOB DEFAULT NULL COMMENT 'gzip compressed (>100KB)',
            `response_data_size` INT UNSIGNED DEFAULT NULL COMMENT 'Response size in bytes',
            `request_params` JSON DEFAULT NULL COMMENT 'Request parameters (for debugging)',
            `tenant_id` BIGINT UNSIGNED DEFAULT NULL COMMENT 'Tenant ID',
            `cache_watermark` DATETIME NOT NULL COMMENT 'Cache generation timestamp (replaces MAX(updated_at))',
            `ttl_seconds` INT UNSIGNED DEFAULT 300 COMMENT 'Cache TTL (seconds)',
            `expires_at` DATETIME NOT NULL COMMENT 'Cache expiration time',
            `is_expired` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether cache is expired (0=valid, 1=expired)',
            `hit_count` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Cache hit count',
            `last_hit_at` DATETIME DEFAULT NULL COMMENT 'Last hit timestamp',
            `auto_refresh_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether auto-refresh is enabled',
            `auto_refresh_interval` INT UNSIGNED DEFAULT NULL COMMENT 'Auto-refresh interval (seconds)',
            `next_refresh_at` DATETIME DEFAULT NULL COMMENT 'Next refresh time (with jitter)',
            `refresh_status` VARCHAR(20) NOT NULL DEFAULT 'idle' COMMENT 'idle/pending/processing/failed/timeout',
            `last_refresh_at` DATETIME DEFAULT NULL COMMENT 'Last refresh timestamp',
            `last_refresh_status` VARCHAR(20) DEFAULT NULL COMMENT 'Last refresh status (success/failed/timeout)',
            `last_refresh_error` TEXT DEFAULT NULL COMMENT 'Last refresh error message',
            `claimed_at` DATETIME DEFAULT NULL COMMENT 'Cache claim timestamp (for state machine)',
            `claimed_by` VARCHAR(100) DEFAULT NULL COMMENT 'Pod name that claimed this cache',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_cache_key_group` (`cache_key`, `cache_group`),
            KEY `idx_logical_key` (`logical_key`),
            KEY `idx_cache_group` (`cache_group`),
            KEY `idx_tenant_id` (`tenant_id`),
            KEY `idx_expires_at` (`expires_at`),
            KEY `idx_is_expired` (`is_expired`),
            KEY `idx_refresh_status` (`refresh_status`, `next_refresh_at`),
            KEY `idx_auto_refresh` (`auto_refresh_enabled`, `next_refresh_at`),
            KEY `idx_created_at` (`created_at`),
            KEY `idx_hit_count` (`hit_count`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dashboard 数据缓存主表'
    """)

    # 2. 刷新配置表
    op.execute("""
        CREATE TABLE IF NOT EXISTS `raap_dashboard_data_cache_refresh_config` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
            `cache_key` VARCHAR(255) NOT NULL COMMENT 'Physical key (MD5)',
            `logical_key` VARCHAR(500) NOT NULL COMMENT 'Logical key (semantic)',
            `cache_group` VARCHAR(100) NOT NULL COMMENT 'Cache group',
            `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether refresh is enabled',
            `refresh_interval` INT UNSIGNED DEFAULT 300 COMMENT 'Refresh interval (seconds)',
            `backoff_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether backoff is enabled',
            `max_backoff_interval` INT UNSIGNED DEFAULT 3600 COMMENT 'Max backoff interval (seconds)',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_cache_key` (`cache_key`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='缓存刷新配置表'
    """)

    # 3. 刷新历史表
    op.execute("""
        CREATE TABLE IF NOT EXISTS `raap_dashboard_data_cache_refresh_history` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
            `logical_key` VARCHAR(500) NOT NULL COMMENT 'Logical key (semantic)',
            `refresh_status` VARCHAR(20) NOT NULL COMMENT 'idle/pending/processing/failed/timeout',
            `started_at` DATETIME NOT NULL COMMENT 'Refresh start time',
            `completed_at` DATETIME DEFAULT NULL COMMENT 'Refresh completion time',
            `duration_seconds` INT UNSIGNED DEFAULT NULL COMMENT 'Refresh duration (seconds)',
            `error_message` TEXT DEFAULT NULL COMMENT 'Error message (if failed)',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
            PRIMARY KEY (`id`),
            KEY `idx_logical_key` (`logical_key`),
            KEY `idx_refresh_status` (`refresh_status`),
            KEY `idx_started_at` (`started_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='缓存刷新历史表'
    """)

    # 4. 演示配置表
    op.execute("""
        CREATE TABLE IF NOT EXISTS `raap_dashboard_data_cache_demo_config` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
            `demo_key` VARCHAR(255) NOT NULL COMMENT 'Demo data key',
            `data_type` ENUM('static', 'increment', 'range', 'function') NOT NULL COMMENT 'Demo data type',
            `config_json` JSON NOT NULL COMMENT 'Configuration JSON',
            `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether enabled',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_demo_key` (`demo_key`),
            KEY `idx_data_type` (`data_type`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='演示数据配置表'
    """)

    # 5. 分布式锁表
    op.execute("""
        CREATE TABLE IF NOT EXISTS `raap_dashboard_data_cache_distributed_lock` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
            `lock_key` VARCHAR(255) NOT NULL COMMENT 'Lock key (e.g., "cache_warmup:dashboard_stats")',
            `lock_token` VARCHAR(36) NOT NULL COMMENT 'Unique lock token (UUID)',
            `locked_at` DATETIME NOT NULL COMMENT 'Lock acquisition time',
            `expires_at` DATETIME NOT NULL COMMENT 'Lock expiration time',
            `locked_by` VARCHAR(100) DEFAULT NULL COMMENT 'Pod name that acquired the lock',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_lock_key` (`lock_key`),
            KEY `idx_expires_at` (`expires_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分布式锁表'
    """)

    # 6. 预热配置表
    op.execute("""
        CREATE TABLE IF NOT EXISTS `raap_dashboard_data_cache_warmup_config` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
            `cache_key` VARCHAR(255) NOT NULL COMMENT 'Physical key (MD5)',
            `logical_key` VARCHAR(500) NOT NULL COMMENT 'Logical key (semantic)',
            `cache_group` VARCHAR(100) NOT NULL COMMENT 'Cache group',
            `priority` INT UNSIGNED DEFAULT 0 COMMENT 'Warmup priority (0=highest)',
            `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether enabled',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_cache_key` (`cache_key`),
            KEY `idx_priority` (`priority`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='缓存预热配置表'
    """)


def downgrade() -> None:
    """删除 Dashboard 数据缓存系统的 6 张表"""

    # 按依赖顺序逆序删除
    op.execute("DROP TABLE IF EXISTS `raap_dashboard_data_cache_warmup_config`")
    op.execute("DROP TABLE IF EXISTS `raap_dashboard_data_cache_distributed_lock`")
    op.execute("DROP TABLE IF EXISTS `raap_dashboard_data_cache_demo_config`")
    op.execute("DROP TABLE IF EXISTS `raap_dashboard_data_cache_refresh_history`")
    op.execute("DROP TABLE IF EXISTS `raap_dashboard_data_cache_refresh_config`")
    op.execute("DROP TABLE IF EXISTS `raap_dashboard_data_cache_response`")
