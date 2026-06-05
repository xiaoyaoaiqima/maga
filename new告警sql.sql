WITH article_types AS (
  -- 文章种类来自「产品使用体验」子关键词导出，共 54 个组合。
  SELECT 1 AS sort_order, '0-6个月，3个月内，奶量补充' AS name
  UNION ALL
  SELECT 2, '0-6个月，3-6个月，奶量补充'
  UNION ALL
  SELECT 3, '0-6个月，6个月以上，奶量补充'
  UNION ALL
  SELECT 4, '7-12个月，3个月内，奶量补充'
  UNION ALL
  SELECT 5, '7-12个月，3-6个月，奶量补充'
  UNION ALL
  SELECT 6, '7-12个月，6个月以上，奶量补充'
  UNION ALL
  SELECT 7, '1-3岁，3个月内，奶量补充'
  UNION ALL
  SELECT 8, '1-3岁，3-6个月，奶量补充'
  UNION ALL
  SELECT 9, '1-3岁，6个月以上，奶量补充'
  UNION ALL
  SELECT 10, '0-6个月，3个月内，生长发育'
  UNION ALL
  SELECT 11, '0-6个月，3-6个月，生长发育'
  UNION ALL
  SELECT 12, '0-6个月，6个月以上，生长发育'
  UNION ALL
  SELECT 13, '7-12个月，3个月内，生长发育'
  UNION ALL
  SELECT 14, '7-12个月，3-6个月，生长发育'
  UNION ALL
  SELECT 15, '7-12个月，6个月以上，生长发育'
  UNION ALL
  SELECT 16, '1-3岁，3个月内，生长发育'
  UNION ALL
  SELECT 17, '1-3岁，3-6个月，生长发育'
  UNION ALL
  SELECT 18, '1-3岁，6个月以上，生长发育'
  UNION ALL
  SELECT 19, '0-6个月，3个月内，容易生病'
  UNION ALL
  SELECT 20, '0-6个月，3-6个月，容易生病'
  UNION ALL
  SELECT 21, '0-6个月，6个月以上，容易生病'
  UNION ALL
  SELECT 22, '7-12个月，3个月内，容易生病'
  UNION ALL
  SELECT 23, '7-12个月，3-6个月，容易生病'
  UNION ALL
  SELECT 24, '7-12个月，6个月以上，容易生病'
  UNION ALL
  SELECT 25, '1-3岁，3个月内，容易生病'
  UNION ALL
  SELECT 26, '1-3岁，3-6个月，容易生病'
  UNION ALL
  SELECT 27, '1-3岁，6个月以上，容易生病'
  UNION ALL
  SELECT 28, '0-6个月，3个月内，消化吸收'
  UNION ALL
  SELECT 29, '0-6个月，3-6个月，消化吸收'
  UNION ALL
  SELECT 30, '0-6个月，6个月以上，消化吸收'
  UNION ALL
  SELECT 31, '7-12个月，3个月内，消化吸收'
  UNION ALL
  SELECT 32, '7-12个月，3-6个月，消化吸收'
  UNION ALL
  SELECT 33, '7-12个月，6个月以上，消化吸收'
  UNION ALL
  SELECT 34, '1-3岁，3个月内，消化吸收'
  UNION ALL
  SELECT 35, '1-3岁，3-6个月，消化吸收'
  UNION ALL
  SELECT 36, '1-3岁，6个月以上，消化吸收'
  UNION ALL
  SELECT 37, '0-6个月，3个月内，便便问题'
  UNION ALL
  SELECT 38, '0-6个月，3-6个月，便便问题'
  UNION ALL
  SELECT 39, '0-6个月，6个月以上，便便问题'
  UNION ALL
  SELECT 40, '7-12个月，3个月内，便便问题'
  UNION ALL
  SELECT 41, '7-12个月，3-6个月，便便问题'
  UNION ALL
  SELECT 42, '7-12个月，6个月以上，便便问题'
  UNION ALL
  SELECT 43, '1-3岁，3个月内，便便问题'
  UNION ALL
  SELECT 44, '1-3岁，3-6个月，便便问题'
  UNION ALL
  SELECT 45, '1-3岁，6个月以上，便便问题'
  UNION ALL
  SELECT 46, '0-6个月，3个月内，过敏相关'
  UNION ALL
  SELECT 47, '0-6个月，3-6个月，过敏相关'
  UNION ALL
  SELECT 48, '0-6个月，6个月以上，过敏相关'
  UNION ALL
  SELECT 49, '7-12个月，3个月内，过敏相关'
  UNION ALL
  SELECT 50, '7-12个月，3-6个月，过敏相关'
  UNION ALL
  SELECT 51, '7-12个月，6个月以上，过敏相关'
  UNION ALL
  SELECT 52, '1-3岁，3个月内，过敏相关'
  UNION ALL
  SELECT 53, '1-3岁，3-6个月，过敏相关'
  UNION ALL
  SELECT 54, '1-3岁，6个月以上，过敏相关'
)
SELECT
  article_types.name,
  COUNT(content.id) AS count
FROM
  article_types
  LEFT JOIN content ON content.agent_code = 'agent_260512_yer3'
  AND content.context_list LIKE CONCAT('%', article_types.name, '%')
  AND content.is_valid = 1
  AND content.is_test_case = 0
  AND content.is_deleted = 0
  AND content.online_status = 'ONLINE'
  AND content.is_used = 0
  AND (
    content.is_locked = 0
    OR content.lock_expire_time < NOW()
  )
GROUP BY
  article_types.sort_order,
  article_types.name
ORDER BY
  article_types.sort_order;
