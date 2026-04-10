CREATE TABLE IF NOT EXISTS `test_case` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `dataset_code` VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '数据集/批次标识（例如 csv_20251215）',

  `title` VARCHAR(512) NULL COMMENT '标题',
  `content` LONGTEXT NOT NULL COMMENT '正文',

  `meta` JSON NULL COMMENT '原始字段/扩展信息（persona/scene/pain_point/selling_point/来源等都放这里）',
  `tags` JSON NULL COMMENT '标签（可选）',

  `content_md5` CHAR(32) NOT NULL COMMENT 'content 的 md5，用于去重',
  `enabled` TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用(1/0)',
  `is_deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '软删(1/0)',

  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_by` VARCHAR(64) NULL COMMENT '创建人',

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_test_case_dataset_md5` (`dataset_code`, `content_md5`),
  KEY `idx_test_case_dataset` (`dataset_code`),
  KEY `idx_test_case_enabled` (`enabled`),
  KEY `idx_test_case_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试用例表';


CREATE TABLE IF NOT EXISTS `expert_eval_run` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `run_code` VARCHAR(64) NOT NULL COMMENT '运行编号（前端生成/后端生成均可）',

  `expert_config_code` VARCHAR(64) NOT NULL COMMENT '专家配置 code',
  `expert_config_snapshot` JSON NULL COMMENT '本次运行使用的 expert_config 快照（强烈建议存）',

  `select_params` JSON NULL COMMENT '本次选样参数（dataset_code/ids/limit 等）',
  `status` VARCHAR(32) NOT NULL DEFAULT 'running' COMMENT 'running/success/failed/cancelled',
  `total_count` INT NOT NULL DEFAULT 0 COMMENT '总数',
  `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功数',
  `failed_count` INT NOT NULL DEFAULT 0 COMMENT '失败数',

  `start_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
  `end_time` DATETIME NULL COMMENT '结束时间',
  `created_by` VARCHAR(64) NULL COMMENT '创建人',

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_expert_eval_run_code` (`run_code`),
  KEY `idx_expert_eval_run_expert` (`expert_config_code`),
  KEY `idx_expert_eval_run_time` (`start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='专家评测运行表';


CREATE TABLE IF NOT EXISTS `expert_eval_result` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `run_id` BIGINT NOT NULL COMMENT '关联 expert_eval_run.id',
  `test_case_id` BIGINT NOT NULL COMMENT '关联 test_case.id',

  `score` INT NULL COMMENT '分数(0-100)',
  `reason` TEXT NULL COMMENT '评语',
  `highlights` TEXT NULL COMMENT '原文摘录',

  `raw_output` JSON NULL COMMENT '模型/专家原始返回（完整保留，便于排查）',
  `rendered_prompt` LONGTEXT NULL COMMENT '实际下发 prompt（建议存，便于复现）',

  `model_code` VARCHAR(128) NULL COMMENT '最终使用模型',
  `provider_code` VARCHAR(64) NULL COMMENT 'provider',
  `token_usage` JSON NULL COMMENT 'token 使用情况',
  `latency_ms` INT NULL COMMENT '耗时(毫秒)',
  `trace_id` VARCHAR(64) NULL COMMENT '链路追踪 trace_id',

  `success` TINYINT NOT NULL DEFAULT 1 COMMENT '是否成功(1/0)',
  `error_message` TEXT NULL COMMENT '失败原因',

  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_run_test_case` (`run_id`, `test_case_id`),
  KEY `idx_eval_result_run` (`run_id`),
  KEY `idx_eval_result_test_case` (`test_case_id`),
  KEY `idx_eval_result_success` (`success`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='专家评测结果表';


SELECT id, role_code, role_name
FROM sys_role
WHERE is_deleted=0
ORDER BY created_at ASC;



-- 目录：专家调试
INSERT INTO sys_menu (
  id, parent_id, menu_name, menu_type, path, component, icon, perm_code,
  sort_order, visible, status, created_at, updated_at, is_deleted
) VALUES (
  'menu_expert', '0', '专家调试', 'M',
  '/expert', NULL, 'lucide:flask-conical', NULL,
  2800, 1, 1, NOW(), NOW(), 0
)
ON DUPLICATE KEY UPDATE
  menu_name=VALUES(menu_name),
  path=VALUES(path),
  icon=VALUES(icon),
  sort_order=VALUES(sort_order),
  visible=VALUES(visible),
  status=VALUES(status),
  updated_at=NOW(),
  is_deleted=0;

-- 菜单：调试面板
INSERT INTO sys_menu (
  id, parent_id, menu_name, menu_type, path, component, icon, perm_code,
  sort_order, visible, status, created_at, updated_at, is_deleted
) VALUES (
  'menu_expert_debug', 'menu_expert', '调试面板', 'C',
  '/expert/debug', 'views/expert/debug/index', NULL, 'expert:debug:view',
  1, 1, 1, NOW(), NOW(), 0
)
ON DUPLICATE KEY UPDATE
  menu_name=VALUES(menu_name),
  path=VALUES(path),
  component=VALUES(component),
  perm_code=VALUES(perm_code),
  sort_order=VALUES(sort_order),
  visible=VALUES(visible),
  status=VALUES(status),
  updated_at=NOW(),
  is_deleted=0;

-- 菜单：批量评分结果
INSERT INTO sys_menu (
  id, parent_id, menu_name, menu_type, path, component, icon, perm_code,
  sort_order, visible, status, created_at, updated_at, is_deleted
) VALUES (
  'menu_expert_eval', 'menu_expert', '批量评分结果', 'C',
  '/expert/eval', 'views/expert/eval/index', NULL, 'expert:eval:view',
  2, 1, 1, NOW(), NOW(), 0
)
ON DUPLICATE KEY UPDATE
  menu_name=VALUES(menu_name),
  path=VALUES(path),
  component=VALUES(component),
  perm_code=VALUES(perm_code),
  sort_order=VALUES(sort_order),
  visible=VALUES(visible),
  status=VALUES(status),
  updated_at=NOW(),
  is_deleted=0;




INSERT INTO sys_role_menu (role_id, menu_id, created_at)
SELECT 'admin', m.id, NOW()
FROM sys_menu m
WHERE m.id IN ('menu_expert', 'menu_expert_debug', 'menu_expert_eval')
AND NOT EXISTS (
  SELECT 1 FROM sys_role_menu rm
  WHERE rm.role_id = 'admin' AND rm.menu_id = m.id
);