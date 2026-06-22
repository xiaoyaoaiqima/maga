"""Import and sample real-user wording pools for content generation."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from secrets import SystemRandom
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetImportRun, AssetRegistry


REAL_USER_EXAMPLE_POOL_ASSET_TYPE = "real_user_example_pool"
DEFAULT_REAL_USER_EXAMPLE_POOL_ASSET_KEY = "maternal_infant_xhs_real_user_pool"

DEFAULT_NOTE_SAMPLE_COUNT = 5
DEFAULT_COMMENT_SAMPLE_COUNT = 2
MAX_TEXT_CHARS = 260
MAX_TITLE_CHARS = 80

TAG_RULES: dict[str, tuple[str, ...]] = {
    "选奶": ("选奶", "挑奶", "换奶", "转奶", "怎么选", "纠结", "对比", "功课", "攻略", "定了", "入手"),
    "价格": ("贵", "价格", "账单", "蹲活动", "囤", "整箱", "一罐", "一箱", "肉疼"),
    "喝奶接受度": ("爱喝", "好喝", "不喝", "不抗拒", "不排斥", "接受", "奶量", "喝光", "咕咚"),
    "营养": ("营养", "钙", "铁", "锌", "全面", "补充", "跟上", "配方", "成分"),
    "成长": ("长高", "长个", "窜", "长肉", "体重", "身高", "发育", "结实", "壮实"),
    "保护力": ("保护力", "抵抗力", "免疫", "中招", "请假", "不生病", "体质"),
    "挑食": ("挑食", "饭量", "吃饭", "胃口", "嘴刁", "挑嘴"),
    "幼儿园": ("幼儿园", "上学", "放学", "老师", "同学", "集体", "兴趣班"),
    "户外": ("户外", "公园", "露营", "玩水", "运动", "跳绳", "跑", "活动量"),
    "成分": ("成分", "DHA", "乳铁", "HMO", "OPO", "A2", "蛋白", "叶黄素", "燕窝酸"),
}

RISK_TAG_RULES: dict[str, tuple[str, ...]] = {
    "强功效": ("不生病", "免疫力", "抵抗力", "长高", "长个", "窜个", "少请假", "治疗", "改善"),
    "竞品品牌": ("a2", "A2", "爱他美", "至初", "美素佳儿", "皇家", "蓝胖子", "达能", "enfamil", "neuropro", "enspire"),
    "广告口吻": ("推荐", "安利", "育儿师", "行业", "黄金奶源", "值得入手", "闭眼入"),
    "评论口吻": ("姐妹", "求问", "求推荐", "蹲", "同款", "你们", "有货"),
    "产品动作风险": ("奶瓶", "自己冲", "自己泡", "自己舀粉", "自己倒水", "塞书包", "路上喝", "抱着奶瓶"),
}

NOTE_MIN_CHARS = 24
COMMENT_MIN_CHARS = 6
COMMENT_MAX_CHARS = 120
REAL_USER_ROUTE_LAYER = "route"
REAL_USER_DETAIL_LAYER = "detail"
REAL_USER_TITLE_SHAPE_LAYER = "title_shape"
REAL_USER_OPENING_LAYER = "opening_texture"
REAL_USER_TEXTURE_LAYER = "texture"
REAL_USER_ENDING_LAYER = "ending"
REAL_USER_REJECT_LAYER = "reject"
PROMPT_TEXT_DEDUPE_LAYERS = {
    REAL_USER_ROUTE_LAYER,
    REAL_USER_DETAIL_LAYER,
    REAL_USER_TITLE_SHAPE_LAYER,
    REAL_USER_OPENING_LAYER,
    REAL_USER_TEXTURE_LAYER,
    REAL_USER_ENDING_LAYER,
}

REJECT_LAYER_TERMS = (
    "快闪",
    "联名",
    "小黄人",
    "草坪",
    "愚园路",
    "礼盒",
    "对讲机",
    "玩家",
    "打怪",
    "c位出道",
    "乐园",
    "酒店",
    "北京",
    "旅游",
    "旅居",
    "回老家",
    "预产期",
    "父亲节",
    "母亲节",
    "爸爸生日",
    "手机支架",
    "孩子王",
    "母婴店",
    "宝宝",
    "宝妈",
    "宝贝",
    "底气",
    "攻略",
    "一张图",
    "不求人",
    "外国奶粉",
    "bobbie",
    "新加坡",
    "马来西亚",
    "enfamil",
    "neuropro",
    "enspire",
    "德爱",
    "澳爱",
    "佳贝艾特",
    "悦白",
    "铂晶",
    "德版",
    "美国",
    "成分控",
    "tldr",
    "转奶",
    "婴配",
    "3段",
    "三段",
    "奶瓶",
    "自己冲",
    "自己泡",
    "自己舀粉",
    "自己倒水",
    "孩子自己泡",
    "孩子自己冲",
    "塞书包",
    "路上喝",
    "抱着奶瓶",
    "渠道",
    "现货",
    "发货",
    "私信",
    "拉群",
)

ROUTE_LAYER_TERMS = (
    "幼儿园",
    "上学",
    "兴趣班",
    "户外",
    "活动量",
    "疯跑",
    "运动",
    "做功课",
    "选奶",
    "挑奶",
    "对比",
    "账单",
    "肉疼",
    "贵",
    "挑食",
    "吃饭",
    "饭量",
    "胃口",
    "营养",
    "成长",
    "长肉",
    "长个",
    "中招",
    "请假",
    "保护力",
)

TEXTURE_LAYER_TERMS = (
    "不便宜",
    "贵",
    "除了贵",
    "肉疼",
    "没毛病",
    "认了",
    "值得",
    "值了",
    "不懂",
    "不是很懂",
    "先喝",
    "纠结",
    "哈哈",
    "记录",
    "小期待",
    "嘴巴真刁",
    "谁懂",
    "头疼",
    "焦虑",
    "愁",
    "老母亲",
    "试了一圈",
    "终于",
    "简单分享",
    "纯个人",
    "没啥",
    "不吹不黑",
    "有点慌",
    "好烦",
    "比不来",
    "给点建议",
    "非广",
    "普通顾客",
    "有姐妹",
    "纠结不出来",
    "真不错",
    "喝着放心",
    "愿意喝",
)

DETAIL_LAYER_TERMS = (
    "接娃",
    "放学",
    "上学",
    "幼儿园",
    "老师",
    "餐桌",
    "杯子",
    "餐盘",
    "吃饭",
    "饭量",
    "胃口",
    "成分",
    "配料",
    "账单",
    "囤",
    "一罐",
    "一桶",
    "两大杯",
    "一杯",
    "好喝",
    "说好喝",
    "喝得也少",
    "喝得少",
    "户外",
    "活动量",
    "疯跑",
    "运动",
    "衣服",
    "书包",
    "请假",
    "病假",
    "8天假",
    "玩嗨",
    "摸爬滚打",
    "活蹦乱跳",
    "状态",
    "精神",
    "精神头",
)

ENDING_LAYER_TERMS = (
    "没毛病",
    "认了",
    "先喝",
    "先这样",
    "记录",
    "就这样",
    "还行",
    "算了",
    "不吹",
    "不黑",
    "不敢说",
    "不敢讲",
    "值了",
    "缺点",
    "给点建议",
    "欢迎留言",
    "非广",
    "不专业",
    "普通顾客",
    "哈哈",
    "好烦",
    "纠结不出来",
    "也行",
    "挺好",
    "挺稳",
    "少折腾",
)

TITLE_SHAPE_BLOCK_TERMS = (
    "皇家美素佳儿",
    "美素佳儿",
    "旺玥",
    "保护小课堂",
    "课堂",
    "品牌大比较",
    "怎么选",
    "攻略",
    "测评",
    "推荐",
    "安利",
    "指南",
    "科普",
    "闭眼入",
    "一篇看懂",
    "一张图",
    "不踩坑",
    "奶粉哪家好",
    "成分表",
    "配方表",
    "配方",
    "hmo",
    "dha",
    "ara",
    "cpp",
    "opo",
    "乳铁",
    "核苷酸",
    "牛磺酸",
    "免yi",
    "儿童奶粉",
    "儿童成长奶粉",
    "生长激素",
    "补脑",
    "护眼",
    "学生奶粉",
    "小学生",
    "小学",
    "长期喝",
    "港版",
    "新加坡",
    "🇸🇬",
    "牛奶",
    "宠物",
    "人宠",
    "澳洲",
    "澳大利亚",
    "全美",
    "排名",
    "top",
    "污染",
    "安不安全",
    "安全清单",
    "儿童用品",
    "315",
    "致命",
    "毒素",
    "入侵",
    "超市",
    "纸尿布",
    "屁屁",
    "面膜",
    "波咯咯",
    "摇奶器",
    "新手妈妈",
    "海边",
    "动物",
    "猫",
    "狗",
    "幼儿园必备",
    "宝宝",
    "宝妈",
    "几岁",
    "几月",
    "哪里买",
    "私信",
    "不是广",
    "家长",
    "母亲",
    "有沒有",
    "有没有",
    "幾歲",
    "几岁",
    "小孩",
    "孩子体质弱",
    "身体不适",
    "大难题",
    "既要",
    "还要",
    "两者兼得",
    "帮到孩子",
    "肠道",
    "菌群",
    "贪小便宜",
    "买不到",
    "断粮",
    "断奶",
    "等不了了",
    "到货",
    "抢购",
    "同城",
    "救急",
    "官网",
    "社会责任",
    "至熠",
    "能恩",
    "全护",
    "天花板",
    "c位",
    "活动",
    "you need food",
    "cancer",
    "claude",
    "sdk",
    "agent",
)

TITLE_SHAPE_SOURCE_BLOCK_TERMS = (
    "断货",
    "缺货",
    "召回",
    "买不到货",
    "下架",
    "货源",
    "无货",
    "溢价",
    "炒到",
    "清关",
    "质检",
    "a2",
    "至初",
    "紫白金",
    "紫曜",
    "爱他美",
    "启赋",
    "飞鹤",
    "合生元",
    "派星",
    "优博",
    "臻智护",
    "贝拉米",
    "君乐宝",
    "enfamil",
    "neuropro",
    "enspire",
    "转奶",
    "换奶",
    "渠道",
    "现货",
    "发货",
    "私信",
    "拉群",
    "旗舰店",
    "库存",
    "京东",
    "山姆",
    "在哪里买",
    "限时抢购",
    "攻略",
    "一张图",
    "不求人",
    "快闪",
    "联名",
    "礼盒",
    "酒店",
    "旅游",
    "旅居",
    "奶瓶",
    "自己冲",
    "自己泡",
    "自己舀粉",
    "自己倒水",
    "孩子自己泡",
    "孩子自己冲",
    "塞书包",
    "路上喝",
    "抱着奶瓶",
)

OPENING_LAYER_TERMS = (
    "最近",
    "这阵",
    "这段时间",
    "上幼儿园",
    "开学",
    "放学",
    "户外",
    "周末",
    "谁懂",
    "当妈",
    "我家",
    "以前",
    "说实话",
    "记录",
    "纠结",
    "选奶",
    "做功课",
    "挑食",
    "吃饭",
    "活动量",
)

PROMPT_VIEW_BLOCK_TERMS = (
    "预产期",
    "父亲节",
    "母亲节",
    "爸爸生日",
    "手机支架",
    "孩子王",
    "母婴店",
    "宝宝",
    "宝妈",
    "宝贝",
    "底气",
    "小脑瓜",
    "小眼睛",
    "吞金兽",
    "成功人士",
    "婴配",
    "四段",
    "4段",
    "三段",
    "3-6",
    "3－6",
    "3岁",
    "3+",
    "几岁",
    "幾歲",
    "岁半",
    "歲半",
    "两岁",
    "兩歲",
    "三岁",
    "三歲",
    "小学",
    "小一",
    "初中",
    "大班",
    "数理化",
    "晚自习",
    "刷题",
    "难题课",
    "老师思路",
    "上课能",
    "课间",
    "神经酸",
    "蛋白粉",
    "a2",
    "anmum",
    "anmumgold",
    "佳贝艾特",
    "海底小纵队",
    "联名",
    "礼盒",
    "小粉丝",
    "本命快乐",
    "周岁",
    "用量",
    "左边",
    "右边",
    "中间",
    "小朋友",
    "随身携带",
    "野餐篮",
    "公园",
    "风筝",
    "草丛",
    "花路",
    "周末",
    "药剂师",
    "美赞臣",
    "蓝胖子",
    "万宁",
    "get我们",
    "泼天",
    "富贵",
    "深入了解",
    "轻松应对",
    "活力无限",
    "强强联手",
    "不踩坑",
    "各位家长",
    "绝绝子",
    "黄金期",
    "澳洲",
    "新鲜度",
    "营养保留",
    "动物园",
    "公益",
    "签名",
    "小动物",
    "cancer",
    "you need food",
    "港版",
    "长期喝",
    "打开湿湿",
    "湿湿",
    "没我高",
    "那又怎样",
    "欢迎留言",
    "好的建议",
    "相关经验",
    "顶级",
    "頂級",
    "内护力",
    "p磷脂",
    "磷脂酰丝氨酸s",
    "关键营养素",
    "30+种",
    "足足30",
    "省心很多",
    "带娃真的省心",
    "當水喝",
    "当水喝",
    "倒头就睡",
    "睡更香",
    "固定囤",
    "每个月固定",
    "會一直喝下去",
    "会一直喝下去",
    "直接入手",
    "旺玥儿童营养奶粉",
    "这款儿童营养奶粉",
    "這款兒童營養奶粉",
    "超群乳铁蛋白",
    "增强抵抗力",
    "健康成长",
    "[列举具体成分]",
    "协同作用",
    "调节身体",
    "筑牢",
    "免疫防线",
    "坚固的防线",
    "挖到了",
    "挖到",
    "稳稳守护",
    "守护孩子成长",
    "值得信赖的大品牌",
    "普通顾客对比选择后分享出思考过程",
    "非广",
    "少喝奶茶",
    "奶茶",
    "闺女",
    "插管",
    "儿童成长奶粉的话",
    "上面只写",
    "说明书",
    "按规矩",
    "奶瘾",
    "一天喝3",
    "一天喝三",
    "喝多会",
    "hmo",
    "助力成长",
    "成长营养没跟上",
    "根本没保障",
    "新一代",
    "突破性",
    "不额外添加",
    "蔗糖",
    "香精",
    "天然奶香",
    "妈妈的首选",
    "丰富的营养成分",
    "高钙高铁高锌",
    "一杯里面含有",
    "有沒有在喝",
    "有没有在喝",
    "咳嗽",
    "流鼻涕",
    "缺了哪样",
    "缺了哪",
    "简单分享",
    "有姐妹给点建议",
    "专业的儿童奶粉",
    "专业儿童奶粉",
    "多面营养",
    "学龄前",
    "关键期",
    "大脑、视力",
    "大脑视力",
    "快速发育",
    "小红薯",
    "参考一下",
    "纯个人",
    "纯個人",
)


@dataclass(frozen=True)
class RealUserPoolImportResult:
    asset: AssetRegistry | None
    import_run: AssetImportRun | None
    source_hash: str
    summary: dict[str, Any]
    items: list[dict[str, Any]]


async def import_real_user_example_pool_from_export_dir(
    db: AsyncSession,
    export_dir: str | Path,
    *,
    asset_key: str = DEFAULT_REAL_USER_EXAMPLE_POOL_ASSET_KEY,
    display_name: str | None = "母婴小红书真人原句池",
    created_by: str = "real-user-pool-importer",
    dry_run: bool = False,
) -> RealUserPoolImportResult:
    base = Path(export_dir).expanduser()
    if not base.exists() or not base.is_dir():
        raise ValueError(f"export_dir not found: {base}")
    notes_path = base / "xhs_notes_full.csv"
    comments_path = base / "xhs_comments_full.csv"
    if not notes_path.exists() or not comments_path.exists():
        raise ValueError("export_dir must contain xhs_notes_full.csv and xhs_comments_full.csv")

    source_hash = _source_hash(notes_path, comments_path)
    note_items, note_summary = _read_note_items(notes_path)
    comment_items, comment_summary = _read_comment_items(comments_path)
    items = note_items + comment_items
    summary = {
        "source_dir": str(base),
        "source_hash": source_hash,
        "total_items": len(items),
        "note": note_summary,
        "comment": comment_summary,
        "tag_counts": dict(Counter(tag for item in items for tag in item.get("tags") or [])),
        "risk_tag_counts": dict(Counter(tag for item in items for tag in item.get("risk_tags") or [])),
        "layer_counts": dict(Counter(str(item.get("example_layer") or "") for item in items)),
        "prompt_layer_available_counts": _prompt_layer_available_counts(items),
        "title_shape_filter_reason_top": _title_shape_filter_reason_top(items),
    }

    if dry_run:
        return RealUserPoolImportResult(
            asset=None,
            import_run=None,
            source_hash=source_hash,
            summary=summary,
            items=items,
        )

    await db.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type == REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
            AssetRegistry.asset_key == asset_key,
            AssetRegistry.asset_stage == "production",
            AssetRegistry.status == "active",
        )
        .values(status="archived")
    )
    version_no = await _next_asset_version(db, asset_key)
    asset = AssetRegistry(
        asset_type=REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
        asset_key=asset_key,
        display_name=display_name,
        version_no=version_no,
        status="active",
        asset_stage="production",
        source_name=base.name,
        source_uri=str(base),
        source_hash=source_hash,
        content_json={
            "items": items,
            "schema_version": "1.1",
            "source_type": "xhs_crawl_export",
        },
        metadata_json=summary,
        created_by=created_by,
    )
    db.add(asset)
    await db.flush()

    import_run = AssetImportRun(
        source_name=base.name,
        source_uri=str(base),
        source_hash=source_hash,
        status="succeeded",
        imported_assets=1,
        summary_json=summary,
        created_by=created_by,
    )
    db.add(import_run)
    await db.flush()
    return RealUserPoolImportResult(
        asset=asset,
        import_run=import_run,
        source_hash=source_hash,
        summary=summary,
        items=items,
    )


def real_user_pool_import_summary(result: RealUserPoolImportResult) -> dict[str, Any]:
    return result.summary


def infer_real_user_tags(text: str) -> list[str]:
    normalized = _normalize_for_match(text)
    tags = [
        tag
        for tag, words in TAG_RULES.items()
        if any(_normalize_for_match(word) in normalized for word in words)
    ]
    return tags or (["母婴奶粉"] if "奶粉" in normalized or "奶" in normalized else [])


def infer_real_user_risk_tags(text: str, *, source_type: str | None = None) -> list[str]:
    normalized = _normalize_for_match(text)
    tags = [
        tag
        for tag, words in RISK_TAG_RULES.items()
        if any(_normalize_for_match(word) in normalized for word in words)
    ]
    if source_type == "comment" and "评论口吻" not in tags:
        tags.append("评论口吻")
    return tags


def infer_real_user_example_layer(item: dict[str, Any]) -> tuple[str, str]:
    source_type = str(item.get("source_type") or "").strip()
    text = str(item.get("text") or "").strip()
    title = str(item.get("title") or "").strip()
    source_keyword = str(item.get("source_keyword") or "").strip()
    normalized = _normalize_for_match(f"{title} {text} {source_keyword}")
    reject_hit = _first_term_hit(normalized, REJECT_LAYER_TERMS)
    if reject_hit:
        return REAL_USER_REJECT_LAYER, f"reject_term:{reject_hit}"
    if source_type == "comment":
        return REAL_USER_TEXTURE_LAYER, "comment_texture"
    if "广告口吻" in set(item.get("risk_tags") or []):
        return REAL_USER_REJECT_LAYER, "risk_tag:广告口吻"
    texture_hit = _first_term_hit(normalized, TEXTURE_LAYER_TERMS)
    route_hit = _first_term_hit(normalized, ROUTE_LAYER_TERMS)
    strong_route_hit = _first_term_hit(normalized, tuple(term for term in ROUTE_LAYER_TERMS if term not in {"贵", "肉疼"}))
    text_len = len(text)
    if strong_route_hit:
        return REAL_USER_ROUTE_LAYER, f"route_term:{strong_route_hit}"
    if texture_hit and (text_len <= 110 or texture_hit not in {"贵", "肉疼"}):
        return REAL_USER_TEXTURE_LAYER, f"texture_term:{texture_hit}"
    if texture_hit and text_len <= 90:
        return REAL_USER_TEXTURE_LAYER, f"texture_term:{texture_hit}"
    if route_hit:
        return REAL_USER_ROUTE_LAYER, f"route_term:{route_hit}"
    if text_len <= 90:
        return REAL_USER_TEXTURE_LAYER, "short_note_texture"
    return REAL_USER_ROUTE_LAYER, "default_note_route"


def select_real_user_examples(
    items: list[dict[str, Any]],
    *,
    query_text: str,
    note_count: int = DEFAULT_NOTE_SAMPLE_COUNT,
    comment_count: int = DEFAULT_COMMENT_SAMPLE_COUNT,
    route_count: int | None = None,
    detail_count: int | None = None,
    title_shape_count: int | None = None,
    opening_count: int | None = None,
    opening_or_ending_count: int | None = None,
    texture_count: int | None = None,
    ending_count: int | None = None,
    exclude_risk_tags: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    route_family_include: list[str] | None = None,
    route_family_exclude: list[str] | None = None,
    detail_family_include: list[str] | None = None,
    detail_family_exclude: list[str] | None = None,
    route_prompt_include_terms: list[str] | None = None,
    route_prompt_exclude_terms: list[str] | None = None,
    detail_prompt_include_terms: list[str] | None = None,
    detail_prompt_exclude_terms: list[str] | None = None,
    prompt_family_stack_avoid: list[str] | None = None,
    used_dedupe_hashes: set[str] | None = None,
    used_route_families: dict[str, int] | set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query_tags = infer_real_user_tags(query_text)
    normalized_exclude_terms = [_normalize_for_match(term) for term in exclude_terms or [] if str(term).strip()]
    exclude_risk_tag_set = {str(tag).strip() for tag in exclude_risk_tags or [] if str(tag).strip()}
    if any(
        count is not None
        for count in (
            route_count,
            detail_count,
            title_shape_count,
            opening_count,
            opening_or_ending_count,
            texture_count,
            ending_count,
        )
    ):
        return _select_layered_real_user_examples(
            items,
            query_tags=query_tags,
            note_count=note_count,
            comment_count=comment_count,
            route_count=max(0, int(route_count or 0)),
            detail_count=max(0, int(detail_count or 0)),
            title_shape_count=max(0, int(title_shape_count or 0)),
            opening_count=max(0, int(opening_count or 0)),
            opening_or_ending_count=max(0, int(opening_or_ending_count or 0)),
            texture_count=max(0, int(texture_count or 0)),
            ending_count=max(0, int(ending_count or 0)),
            exclude_risk_tags=exclude_risk_tag_set,
            exclude_terms=normalized_exclude_terms,
            route_family_include={str(item).strip() for item in route_family_include or [] if str(item).strip()},
            route_family_exclude={str(item).strip() for item in route_family_exclude or [] if str(item).strip()},
            detail_family_include={str(item).strip() for item in detail_family_include or [] if str(item).strip()},
            detail_family_exclude={str(item).strip() for item in detail_family_exclude or [] if str(item).strip()},
            route_prompt_include_terms={
                _normalize_for_match(item)
                for item in route_prompt_include_terms or []
                if str(item).strip()
            },
            route_prompt_exclude_terms={
                _normalize_for_match(item)
                for item in route_prompt_exclude_terms or []
                if str(item).strip()
            },
            detail_prompt_include_terms={
                _normalize_for_match(item)
                for item in detail_prompt_include_terms or []
                if str(item).strip()
            },
            detail_prompt_exclude_terms={
                _normalize_for_match(item)
                for item in detail_prompt_exclude_terms or []
                if str(item).strip()
            },
            prompt_family_stack_avoid={
                str(item).strip()
                for item in prompt_family_stack_avoid or []
                if str(item).strip()
            },
            original_exclude_terms=[term for term in exclude_terms or [] if str(term).strip()],
            used_dedupe_hashes=used_dedupe_hashes if used_dedupe_hashes is not None else set(),
            used_route_families=used_route_families if used_route_families is not None else set(),
        )
    selected_notes = _select_by_source_type(
        items,
        "note",
        query_tags=query_tags,
        count=note_count,
        exclude_risk_tags=exclude_risk_tag_set,
        exclude_terms=normalized_exclude_terms,
    )
    selected_comments = _select_by_source_type(
        items,
        "comment",
        query_tags=query_tags,
        count=comment_count,
        exclude_risk_tags=exclude_risk_tag_set,
        exclude_terms=normalized_exclude_terms,
    )
    selected = selected_notes + selected_comments
    return selected, {
        "query_tags": query_tags,
        "requested": {"note": note_count, "comment": comment_count},
        "selected": {"note": len(selected_notes), "comment": len(selected_comments)},
        "filters": {
            "exclude_risk_tags": sorted(exclude_risk_tag_set),
            "exclude_terms": [term for term in exclude_terms or [] if str(term).strip()],
        },
        "source_type_counts": dict(Counter(str(item.get("source_type") or "") for item in selected)),
        "tag_counts": dict(Counter(tag for item in selected for tag in item.get("tags") or [])),
        "risk_tag_counts": dict(Counter(tag for item in selected for tag in item.get("risk_tags") or [])),
        "dedupe_hashes": [item.get("dedupe_hash") for item in selected if item.get("dedupe_hash")],
    }


def _select_layered_real_user_examples(
    items: list[dict[str, Any]],
    *,
    query_tags: list[str],
    note_count: int,
    comment_count: int,
    route_count: int,
    detail_count: int,
    title_shape_count: int,
    opening_count: int,
    opening_or_ending_count: int,
    texture_count: int,
    ending_count: int,
    exclude_risk_tags: set[str],
    exclude_terms: list[str],
    route_family_include: set[str],
    route_family_exclude: set[str],
    detail_family_include: set[str],
    detail_family_exclude: set[str],
    route_prompt_include_terms: set[str],
    route_prompt_exclude_terms: set[str],
    detail_prompt_include_terms: set[str],
    detail_prompt_exclude_terms: set[str],
    prompt_family_stack_avoid: set[str],
    original_exclude_terms: list[str],
    used_dedupe_hashes: set[str],
    used_route_families: dict[str, int] | set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_before_selection = set(used_dedupe_hashes)
    selected.extend(
        _select_by_layer(
            items,
            REAL_USER_TITLE_SHAPE_LAYER,
            query_tags=query_tags,
            count=title_shape_count,
            exclude_risk_tags=exclude_risk_tags,
            exclude_terms=exclude_terms,
            used_dedupe_hashes=used_dedupe_hashes,
            used_route_families=set(),
            already_selected_hashes=_selected_layer_dedupe_hashes(selected),
        )
    )
    selected.extend(
        _select_by_layer(
            items,
            REAL_USER_ROUTE_LAYER,
            query_tags=query_tags,
            count=route_count,
            exclude_risk_tags=exclude_risk_tags,
            exclude_terms=exclude_terms,
            route_family_include=route_family_include,
            route_family_exclude=route_family_exclude,
            route_prompt_include_terms=route_prompt_include_terms,
            route_prompt_exclude_terms=route_prompt_exclude_terms,
            used_dedupe_hashes=used_dedupe_hashes,
            used_route_families=used_route_families,
            already_selected_hashes=_selected_layer_dedupe_hashes(selected),
        )
    )
    selected.extend(
        _select_by_layer(
            items,
            REAL_USER_DETAIL_LAYER,
            query_tags=query_tags,
            count=detail_count,
            exclude_risk_tags=exclude_risk_tags,
            exclude_terms=exclude_terms,
            detail_family_include=detail_family_include,
            detail_family_exclude=detail_family_exclude,
            detail_prompt_include_terms=detail_prompt_include_terms,
            detail_prompt_exclude_terms=detail_prompt_exclude_terms,
            used_dedupe_hashes=used_dedupe_hashes,
            used_route_families=set(),
            already_selected_hashes=_selected_layer_dedupe_hashes(selected),
        )
    )
    opening_total = opening_count + opening_or_ending_count
    selected_openings = _select_by_layer(
        items,
        REAL_USER_OPENING_LAYER,
        query_tags=query_tags,
        count=opening_total,
        exclude_risk_tags=exclude_risk_tags,
        exclude_terms=exclude_terms,
        used_dedupe_hashes=used_dedupe_hashes,
        used_route_families=set(),
        already_selected_hashes=_selected_layer_dedupe_hashes(selected),
        prompt_family_exclude=_selected_prompt_families(selected, prompt_family_stack_avoid),
    )
    selected.extend(selected_openings)
    selected.extend(
        _select_by_layer(
            items,
            REAL_USER_TEXTURE_LAYER,
            query_tags=query_tags,
            count=texture_count,
            exclude_risk_tags=exclude_risk_tags,
            exclude_terms=exclude_terms,
            used_dedupe_hashes=used_dedupe_hashes,
            used_route_families=set(),
            already_selected_hashes=_selected_layer_dedupe_hashes(selected),
            prompt_family_exclude=_selected_prompt_families(selected, prompt_family_stack_avoid),
        )
    )
    selected.extend(
        _select_by_layer(
            items,
            REAL_USER_ENDING_LAYER,
            query_tags=query_tags,
            count=ending_count + max(0, opening_or_ending_count - len(selected_openings)),
            exclude_risk_tags=exclude_risk_tags,
            exclude_terms=exclude_terms,
            used_dedupe_hashes=used_dedupe_hashes,
            used_route_families=set(),
            already_selected_hashes=_selected_layer_dedupe_hashes(selected),
            prompt_family_exclude=_selected_prompt_families(selected, prompt_family_stack_avoid),
        )
    )
    if comment_count > 0:
        selected.extend(
            _select_by_source_type(
                items,
                "comment",
                query_tags=query_tags,
                count=comment_count,
                exclude_risk_tags=exclude_risk_tags,
                exclude_terms=exclude_terms,
            )
        )
    for item in selected:
        dedupe_hash = str(item.get("dedupe_hash") or "")
        if dedupe_hash:
            used_dedupe_hashes.add(dedupe_hash)
        prompt_hash = _prompt_dedupe_hash(item, str(item.get("example_layer") or ""))
        if prompt_hash:
            used_dedupe_hashes.add(prompt_hash)
        if item.get("example_layer") == REAL_USER_ROUTE_LAYER and item.get("route_family"):
            _mark_route_family_used(used_route_families, str(item.get("route_family")))
    meta = _selection_meta(
        selected,
        query_tags=query_tags,
        requested={
            "route": route_count,
            "detail": detail_count,
            "title_shape": title_shape_count,
            "opening_texture": opening_count,
            "opening_or_ending": opening_or_ending_count,
            "texture": texture_count,
            "ending": ending_count,
            "note": note_count,
            "comment": comment_count,
        },
        filters={"exclude_risk_tags": sorted(exclude_risk_tags), "exclude_terms": original_exclude_terms},
    )
    if route_family_include:
        meta["route_family_include"] = sorted(route_family_include)
    if route_family_exclude:
        meta["route_family_exclude"] = sorted(route_family_exclude)
    if detail_family_include:
        meta["detail_family_include"] = sorted(detail_family_include)
    if detail_family_exclude:
        meta["detail_family_exclude"] = sorted(detail_family_exclude)
    if route_prompt_include_terms:
        meta["route_prompt_include_terms"] = sorted(route_prompt_include_terms)
    if route_prompt_exclude_terms:
        meta["route_prompt_exclude_terms"] = sorted(route_prompt_exclude_terms)
    if detail_prompt_include_terms:
        meta["detail_prompt_include_terms"] = sorted(detail_prompt_include_terms)
    if detail_prompt_exclude_terms:
        meta["detail_prompt_exclude_terms"] = sorted(detail_prompt_exclude_terms)
    if prompt_family_stack_avoid:
        meta["prompt_family_stack_avoid"] = sorted(prompt_family_stack_avoid)
    meta["fallback_reused_dedupe_hashes"] = [
        dedupe_hash
        for dedupe_hash in meta.get("dedupe_hashes", [])
        if dedupe_hash in used_before_selection
    ]
    return selected, meta


def _selection_meta(
    selected: list[dict[str, Any]],
    *,
    query_tags: list[str],
    requested: dict[str, int],
    filters: dict[str, list[str]],
) -> dict[str, Any]:
    layer_counts = Counter(str(item.get("example_layer") or "") for item in selected)
    source_type_counts = Counter(str(item.get("source_type") or "") for item in selected)
    route_family_counts = Counter(
        str(item.get("route_family") or "")
        for item in selected
        if item.get("example_layer") == REAL_USER_ROUTE_LAYER and item.get("route_family")
    )
    detail_family_counts = Counter(
        str(item.get("detail_family") or "")
        for item in selected
        if item.get("example_layer") == REAL_USER_DETAIL_LAYER and item.get("detail_family")
    )
    return {
        "query_tags": query_tags,
        "requested": requested,
        "selected": {
            "route": layer_counts.get(REAL_USER_ROUTE_LAYER, 0),
            "detail": layer_counts.get(REAL_USER_DETAIL_LAYER, 0),
            "title_shape": layer_counts.get(REAL_USER_TITLE_SHAPE_LAYER, 0),
            "opening_texture": layer_counts.get(REAL_USER_OPENING_LAYER, 0),
            "texture": layer_counts.get(REAL_USER_TEXTURE_LAYER, 0),
            "ending": layer_counts.get(REAL_USER_ENDING_LAYER, 0),
            "note": source_type_counts.get("note", 0),
            "comment": source_type_counts.get("comment", 0),
        },
        "filters": filters,
        "source_type_counts": dict(source_type_counts),
        "layer_counts": dict(layer_counts),
        "tag_counts": dict(Counter(tag for item in selected for tag in item.get("tags") or [])),
        "risk_tag_counts": dict(Counter(tag for item in selected for tag in item.get("risk_tags") or [])),
        "dedupe_hashes": [item.get("dedupe_hash") for item in selected if item.get("dedupe_hash")],
        "prompt_text_by_layer": _prompt_text_by_layer(selected),
        "prompt_family_counts": dict(Counter(family for item in selected for family in _prompt_families(item))),
        "route_family_counts": dict(route_family_counts),
        "route_families": list(route_family_counts.keys()),
        "detail_family_counts": dict(detail_family_counts),
        "detail_families": list(detail_family_counts.keys()),
    }


def _prompt_text_by_layer(selected: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in selected:
        layer = str(item.get("example_layer") or "").strip()
        text = str(item.get("prompt_text") or item.get("text") or "").strip()
        if not layer or not text:
            continue
        result.setdefault(layer, [])
        if text not in result[layer]:
            result[layer].append(text)
    return result


def _prompt_layer_available_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    layers = (
        REAL_USER_ROUTE_LAYER,
        REAL_USER_DETAIL_LAYER,
        REAL_USER_TITLE_SHAPE_LAYER,
        REAL_USER_OPENING_LAYER,
        REAL_USER_TEXTURE_LAYER,
        REAL_USER_ENDING_LAYER,
    )
    return {
        layer: sum(1 for item in items if str(item.get("source_type") or "") == "note" and _item_available_for_layer(item, layer, exclude_terms=[]))
        for layer in layers
    }


def _title_shape_filter_reason_top(items: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for item in items:
        if str(item.get("source_type") or "") != "note":
            continue
        reason = _title_shape_block_reason(str(item.get("title") or ""), exclude_terms=[])
        if reason:
            counter[reason] += 1
    return [{"reason": reason, "count": count} for reason, count in counter.most_common(limit)]


def _select_by_layer(
    items: list[dict[str, Any]],
    layer: str,
    *,
    query_tags: list[str],
    count: int,
    exclude_risk_tags: set[str],
    exclude_terms: list[str],
    used_dedupe_hashes: set[str],
    used_route_families: dict[str, int] | set[str],
    already_selected_hashes: set[str],
    route_family_include: set[str] | None = None,
    route_family_exclude: set[str] | None = None,
    detail_family_include: set[str] | None = None,
    detail_family_exclude: set[str] | None = None,
    route_prompt_include_terms: set[str] | None = None,
    route_prompt_exclude_terms: set[str] | None = None,
    detail_prompt_include_terms: set[str] | None = None,
    detail_prompt_exclude_terms: set[str] | None = None,
    prompt_family_exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    candidates: list[dict[str, Any]] = []
    seen_candidate_hashes: set[str] = set()
    for item in items:
        if (
            not _item_available_for_layer(item, layer, exclude_terms=exclude_terms)
            or str(item.get("source_type") or "") != "note"
            or not str(item.get("text") or "").strip()
            or _excluded_layer_prompt_item(
                item,
                layer,
                exclude_risk_tags=exclude_risk_tags,
                exclude_terms=exclude_terms,
            )
        ):
            continue
        view = _layer_prompt_view(item, layer, exclude_terms=exclude_terms)
        if layer == REAL_USER_ROUTE_LAYER:
            route_family = _route_family(view)
            if route_family_include and route_family not in route_family_include:
                continue
            if route_family_exclude and route_family in route_family_exclude:
                continue
            if route_prompt_include_terms:
                prompt_text = _normalize_for_match(str(view.get("_prompt_text_override") or view.get("prompt_text") or view.get("text") or ""))
                if not any(term and term in prompt_text for term in route_prompt_include_terms):
                    continue
            if route_prompt_exclude_terms:
                prompt_text = _normalize_for_match(str(view.get("_prompt_text_override") or view.get("prompt_text") or view.get("text") or ""))
                if any(term and term in prompt_text for term in route_prompt_exclude_terms):
                    continue
        if layer == REAL_USER_DETAIL_LAYER:
            detail_family = _detail_family(view)
            if detail_family_include and detail_family not in detail_family_include:
                continue
            if detail_family_exclude and detail_family in detail_family_exclude:
                continue
            prompt_text = _normalize_for_match(str(view.get("_prompt_text_override") or view.get("prompt_text") or view.get("text") or ""))
            if detail_prompt_include_terms and not any(term and term in prompt_text for term in detail_prompt_include_terms):
                continue
            if detail_prompt_exclude_terms and any(term and term in prompt_text for term in detail_prompt_exclude_terms):
                continue
        selection_hash = _prompt_dedupe_hash(view, layer)
        if _layer_dedupe_hashes(view, layer) & already_selected_hashes:
            continue
        if selection_hash and selection_hash in seen_candidate_hashes:
            continue
        if selection_hash:
            seen_candidate_hashes.add(selection_hash)
        candidates.append(view)
    if not candidates:
        return []
    candidate_pool = candidates
    curated_preferred_layers = {
        REAL_USER_ROUTE_LAYER,
        REAL_USER_OPENING_LAYER,
        REAL_USER_TEXTURE_LAYER,
        REAL_USER_ENDING_LAYER,
    }
    curated_candidates = (
        [item for item in candidates if _has_curated_prompt_text_for_layer(item, layer)]
        if layer in curated_preferred_layers
        else []
    )
    if used_dedupe_hashes:
        unused_candidates = [
            item
            for item in candidate_pool
            if not (_layer_dedupe_hashes(item, layer) & used_dedupe_hashes)
        ]
        if layer in curated_preferred_layers and curated_candidates:
            unused_curated_candidates = [
                item
                for item in curated_candidates
                if not (_layer_dedupe_hashes(item, layer) & used_dedupe_hashes)
            ]
            if layer == REAL_USER_ROUTE_LAYER:
                candidate_pool = (
                    unused_curated_candidates
                    if len(unused_curated_candidates) >= count
                    else curated_candidates
                )
            else:
                safe_uncurated_candidates = [
                    item for item in unused_candidates if not (set(item.get("risk_tags") or []))
                ]
                candidate_pool = (
                    unused_curated_candidates
                    if len(unused_curated_candidates) >= count
                    else safe_uncurated_candidates
                )
        elif layer in {REAL_USER_DETAIL_LAYER}:
            candidate_pool = unused_candidates
        elif layer in {
            REAL_USER_TITLE_SHAPE_LAYER,
            REAL_USER_OPENING_LAYER,
            REAL_USER_TEXTURE_LAYER,
            REAL_USER_ENDING_LAYER,
        }:
            candidate_pool = unused_candidates
        elif len(unused_candidates) >= count:
            candidate_pool = unused_candidates
        if not candidate_pool:
            return []
    elif curated_candidates:
        candidate_pool = curated_candidates
    if layer == REAL_USER_ROUTE_LAYER and used_route_families:
        if isinstance(used_route_families, dict):
            family_counts = [_route_family_usage_count(used_route_families, _route_family(item)) for item in candidate_pool]
            if family_counts:
                min_family_count = min(family_counts)
                route_family_candidates = [
                    item
                    for item in candidate_pool
                    if _route_family_usage_count(used_route_families, _route_family(item)) == min_family_count
                ]
                if len(route_family_candidates) >= count:
                    candidate_pool = route_family_candidates
        else:
            route_family_candidates = [
                item
                for item in candidate_pool
                if _route_family(item) not in used_route_families
            ]
            if len(route_family_candidates) >= count:
                candidate_pool = route_family_candidates
    if prompt_family_exclude:
        prompt_family_candidates = [
            item for item in candidate_pool if not (_prompt_families(item) & prompt_family_exclude)
        ]
        if len(prompt_family_candidates) >= count:
            candidate_pool = prompt_family_candidates
    query_tag_set = set(query_tags)
    pool = _ranked_layer_pool(candidate_pool, query_tag_set=query_tag_set, layer=layer)
    if layer == REAL_USER_ROUTE_LAYER:
        curated_pool = [item for item in pool if _has_curated_prompt_text_for_layer(item, layer)]
        if len(curated_pool) >= count:
            pool = curated_pool
    top = pool[: max(count * 8, count)]
    if len(top) <= count:
        return [_prompt_item(item, exclude_terms=exclude_terms, forced_layer=layer) for item in top]
    return [
        _prompt_item(item, exclude_terms=exclude_terms, forced_layer=layer)
        for item in sorted(SystemRandom().sample(top, count), key=lambda item: _prompt_dedupe_hash(item, layer))
    ]


def _ranked_layer_pool(items: list[dict[str, Any]], *, query_tag_set: set[str], layer: str) -> list[dict[str, Any]]:
    scored = sorted(
        items,
        key=lambda item: (
            -_item_score(item, query_tag_set),
            str(item.get("dedupe_hash") or ""),
        ),
    )
    if layer == REAL_USER_TITLE_SHAPE_LAYER:
        return scored
    matched = [item for item in scored if set(item.get("tags") or []) & query_tag_set]
    return matched or [item for item in scored if "母婴奶粉" in (item.get("tags") or [])] or scored


def _selected_prompt_families(items: list[dict[str, Any]], enabled_families: set[str]) -> set[str]:
    if not enabled_families:
        return set()
    families: set[str] = set()
    for item in items:
        families.update(_prompt_families(item) & enabled_families)
    return families


def _prompt_families(item: dict[str, Any]) -> set[str]:
    text = _normalize_for_match(
        " ".join(
            str(value or "")
            for value in (
                item.get("_prompt_text_override"),
                item.get("prompt_text"),
                item.get("text"),
                item.get("title"),
            )
        )
    )
    families: set[str] = set()
    if any(
        term in text
        for term in (
            "选奶",
            "挑奶",
            "换奶",
            "对比",
            "做功课",
            "备选",
            "纠结",
            "配方",
            "成分",
            "下手",
            "入手",
            "看了好几",
        )
    ):
        families.add("selection_process")
    if "保护力" in text and any(term in text for term in ("眼脑", "dha", "燕窝酸", "营养")):
        families.add("sellpoint_pairing")
    return families


def _item_available_for_layer(item: dict[str, Any], layer: str, *, exclude_terms: list[str]) -> bool:
    current_layer, _ = _example_layer(item)
    if layer == REAL_USER_TITLE_SHAPE_LAYER:
        snippet, _ = _title_shape_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet) and not _title_shape_source_block_reason(item, exclude_terms=exclude_terms)
    if current_layer == layer and layer == REAL_USER_ROUTE_LAYER:
        snippet, _ = _route_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet)
    if layer == REAL_USER_OPENING_LAYER:
        if current_layer not in {REAL_USER_OPENING_LAYER, REAL_USER_ENDING_LAYER}:
            return False
        snippet, _ = _opening_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet) and current_layer != REAL_USER_REJECT_LAYER
    if layer == REAL_USER_DETAIL_LAYER:
        snippet, _ = _detail_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet) and current_layer != REAL_USER_REJECT_LAYER
    if layer == REAL_USER_ENDING_LAYER:
        snippet, _ = _ending_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet) and current_layer != REAL_USER_REJECT_LAYER
    if layer == REAL_USER_TEXTURE_LAYER:
        snippet, _ = _texture_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet) and current_layer != REAL_USER_REJECT_LAYER
    if layer == REAL_USER_ROUTE_LAYER and current_layer == REAL_USER_REJECT_LAYER:
        snippet, reason = _route_prompt_text(item, exclude_terms=exclude_terms)
        return bool(snippet) and reason.startswith("route_snippet:")
    if current_layer == layer:
        return True
    return False


def _layer_prompt_view(item: dict[str, Any], layer: str, *, exclude_terms: list[str]) -> dict[str, Any]:
    if layer == REAL_USER_ROUTE_LAYER:
        snippet, reason = _route_prompt_text(item, exclude_terms=exclude_terms)
        if not snippet:
            return item
        view = dict(item)
        view["_prompt_text_override"] = snippet
        view["_layer_reason_override"] = reason
        return view
    if layer == REAL_USER_TITLE_SHAPE_LAYER:
        snippet, reason = _title_shape_prompt_text(item, exclude_terms=exclude_terms)
        if not snippet:
            return item
        view = dict(item)
        view["_prompt_text_override"] = snippet
        view["_layer_reason_override"] = reason
        return view
    if layer == REAL_USER_OPENING_LAYER:
        snippet, reason = _opening_prompt_text(item, exclude_terms=exclude_terms)
        if not snippet:
            return item
        view = dict(item)
        view["_prompt_text_override"] = snippet
        view["_layer_reason_override"] = reason
        return view
    if layer == REAL_USER_DETAIL_LAYER:
        snippet, reason = _detail_prompt_text(item, exclude_terms=exclude_terms)
        if not snippet:
            return item
        view = dict(item)
        view["_prompt_text_override"] = snippet
        view["_layer_reason_override"] = reason
        return view
    if layer == REAL_USER_ENDING_LAYER:
        snippet, reason = _ending_prompt_text(item, exclude_terms=exclude_terms)
        if not snippet:
            return item
        view = dict(item)
        view["_prompt_text_override"] = snippet
        view["_layer_reason_override"] = reason
        return view
    if layer != REAL_USER_TEXTURE_LAYER:
        return item
    snippet, reason = _texture_prompt_text(item, exclude_terms=exclude_terms)
    if not snippet:
        return item
    view = dict(item)
    view["_prompt_text_override"] = snippet
    view["_layer_reason_override"] = reason
    return view


def _select_by_source_type(
    items: list[dict[str, Any]],
    source_type: str,
    *,
    query_tags: list[str],
    count: int,
    exclude_risk_tags: set[str],
    exclude_terms: list[str],
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    typed = [
        item
        for item in items
        if item.get("source_type") == source_type
        and _example_layer(item)[0] != REAL_USER_REJECT_LAYER
        and str(item.get("text") or "").strip()
        and not _excluded_prompt_item(item, exclude_risk_tags=exclude_risk_tags, exclude_terms=exclude_terms)
    ]
    if not typed:
        return []
    query_tag_set = set(query_tags)
    scored = sorted(
        typed,
        key=lambda item: (
            -_item_score(item, query_tag_set),
            str(item.get("dedupe_hash") or ""),
        ),
    )
    matched = [item for item in scored if set(item.get("tags") or []) & query_tag_set]
    pool = matched or [item for item in scored if "母婴奶粉" in (item.get("tags") or [])] or scored
    top = pool[: max(count * 8, count)]
    if len(top) <= count:
        return [_prompt_item(item, exclude_terms=exclude_terms) for item in top]
    return [
        _prompt_item(item, exclude_terms=exclude_terms)
        for item in sorted(SystemRandom().sample(top, count), key=lambda item: item.get("dedupe_hash") or "")
    ]


def _excluded_prompt_item(
    item: dict[str, Any],
    *,
    exclude_risk_tags: set[str],
    exclude_terms: list[str],
) -> bool:
    if exclude_risk_tags and set(item.get("risk_tags") or []) & exclude_risk_tags:
        return True
    if exclude_terms:
        return not _safe_prompt_text(item, exclude_terms=exclude_terms)
    return False


def _excluded_layer_prompt_item(
    item: dict[str, Any],
    layer: str,
    *,
    exclude_risk_tags: set[str],
    exclude_terms: list[str],
) -> bool:
    if exclude_risk_tags and set(item.get("risk_tags") or []) & exclude_risk_tags:
        return True
    if layer == REAL_USER_TITLE_SHAPE_LAYER:
        return False
    if exclude_terms:
        return not _safe_prompt_text(item, exclude_terms=exclude_terms)
    return False


def _item_score(item: dict[str, Any], query_tags: set[str]) -> float:
    tags = set(item.get("tags") or [])
    risk_tags = set(item.get("risk_tags") or [])
    overlap = len(tags & query_tags)
    score = float(item.get("quality_score") or 0)
    score += overlap * 10
    if _has_curated_prompt_text(item):
        score += 25
    score -= len(risk_tags & {"广告口吻", "竞品品牌", "产品动作风险"}) * 3
    score -= len(risk_tags & {"强功效", "评论口吻"}) * 1
    return score


def _prompt_item(
    item: dict[str, Any],
    *,
    exclude_terms: list[str] | None = None,
    forced_layer: str | None = None,
) -> dict[str, Any]:
    prompt_text_override = str(item.get("_prompt_text_override") or "").strip()
    curated_prompt_text = _curated_prompt_text(item, exclude_terms=exclude_terms or [])
    prompt_text = (
        prompt_text_override
        or curated_prompt_text
        or (_safe_prompt_text(item, exclude_terms=exclude_terms or []) if exclude_terms else str(item.get("text") or ""))
    )
    layer, reason = _example_layer(item)
    if forced_layer:
        layer = forced_layer
    reason = str(item.get("_layer_reason_override") or item.get("layer_reason") or reason)
    dedupe_hash = item.get("dedupe_hash")
    extra: dict[str, Any] = {}
    if layer == REAL_USER_TITLE_SHAPE_LAYER and prompt_text:
        extra["source_dedupe_hash"] = item.get("source_dedupe_hash") or dedupe_hash
        dedupe_hash = _prompt_dedupe_hash({**item, "_prompt_text_override": prompt_text}, layer)
    return {
        "source_type": item.get("source_type"),
        "text": prompt_text or item.get("text"),
        "prompt_text": prompt_text or item.get("text"),
        "title": "" if exclude_terms else item.get("title"),
        "source_keyword": item.get("source_keyword"),
        "tags": item.get("tags") or [],
        "risk_tags": item.get("risk_tags") or [],
        "dedupe_hash": dedupe_hash,
        "example_layer": layer,
        "layer_reason": reason,
        **extra,
        **({"route_family": _route_family({**item, "prompt_text": prompt_text})} if layer == REAL_USER_ROUTE_LAYER else {}),
        **({"detail_family": _detail_family({**item, "prompt_text": prompt_text})} if layer == REAL_USER_DETAIL_LAYER else {}),
    }


def _prompt_dedupe_hash(item: dict[str, Any], layer: str) -> str:
    if layer in PROMPT_TEXT_DEDUPE_LAYERS:
        prompt_text = str(
            item.get("_prompt_text_override")
            or item.get("prompt_text")
            or item.get("text")
            or item.get("title")
            or ""
        ).strip()
        if prompt_text:
            return _short_hash(layer, _normalize_for_match(prompt_text))
    return str(item.get("dedupe_hash") or "")


def _layer_dedupe_hashes(item: dict[str, Any], layer: str) -> set[str]:
    return {
        value
        for value in (
            str(item.get("dedupe_hash") or ""),
            _prompt_dedupe_hash(item, layer),
        )
        if value
    }


def _selected_layer_dedupe_hashes(items: list[dict[str, Any]]) -> set[str]:
    hashes: set[str] = set()
    for item in items:
        hashes.update(_layer_dedupe_hashes(item, str(item.get("example_layer") or "")))
    return hashes


def _route_family(item: dict[str, Any]) -> str:
    explicit = str(item.get("route_family") or "").strip()
    if explicit:
        return explicit
    family_rules: list[tuple[str, tuple[str, ...]]] = [
        ("school_collective", ("幼儿园", "上学", "放学", "老师", "同学", "兴趣班", "集体")),
        ("outdoor_activity", ("户外", "活动量", "疯跑", "运动", "跳绳", "跑", "玩")),
        ("selection_research", ("选奶", "挑奶", "对比", "功课", "攻略", "成分", "配料")),
        ("price_bill", ("贵", "价格", "账单", "肉疼", "一罐", "一桶", "囤")),
        ("picky_acceptance", ("挑食", "饭量", "吃饭", "胃口", "嘴刁", "挑嘴", "不喝", "愿意喝")),
        ("nutrition_growth", ("营养", "成长", "长肉", "长个", "身高", "体重", "结实", "壮实", "发育")),
        ("protection_sickness", ("保护力", "中招", "请假", "不生病", "少生病")),
        ("routine_record", ("记录", "喝奶", "奶量", "一杯", "早晚", "又开")),
    ]
    body_text = _normalize_for_match(
        " ".join(
            str(value or "")
            for value in (
                item.get("prompt_text"),
                item.get("_prompt_text_override"),
                item.get("text"),
                item.get("title"),
            )
        )
    )
    tag_text = _normalize_for_match(" ".join(str(tag) for tag in item.get("tags") or []))
    for text in (body_text, tag_text):
        if not text:
            continue
        for family, terms in family_rules:
            if any(_normalize_for_match(term) in text for term in terms):
                return family
    return "daily_record"


def _detail_family(item: dict[str, Any]) -> str:
    explicit = str(item.get("detail_family") or "").strip()
    if explicit:
        return explicit
    text = _normalize_for_match(
        " ".join(
            str(value or "")
            for value in (
                item.get("prompt_text"),
                item.get("_prompt_text_override"),
                item.get("text"),
                item.get("title"),
            )
        )
    )
    family_rules: list[tuple[str, tuple[str, ...]]] = [
        ("school_absence", ("请假", "病假", "老师", "幼儿园", "上学", "接触")),
        ("daily_milk_amount", ("两大杯", "一杯", "每天", "日常", "喝奶")),
        ("activity_state", ("活动", "疯跑", "摸爬滚打", "活蹦乱跳", "有劲")),
        ("growth_clothes", ("衣服", "袖子", "裤子", "鞋", "长高", "长个", "长肉")),
        ("plain_nutrition", ("日常营养", "营养补充", "先喝", "接受度")),
    ]
    for family, terms in family_rules:
        if any(_normalize_for_match(term) in text for term in terms):
            return family
    return "daily_detail"


def _route_family_usage_count(used_route_families: dict[str, int] | set[str], family: str) -> int:
    if isinstance(used_route_families, dict):
        return int(used_route_families.get(family, 0) or 0)
    return 1 if family in used_route_families else 0


def _mark_route_family_used(used_route_families: dict[str, int] | set[str], family: str) -> None:
    if isinstance(used_route_families, dict):
        used_route_families[family] = int(used_route_families.get(family, 0) or 0) + 1
    else:
        used_route_families.add(family)


def _safe_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> str:
    text = _strip_prompt_noise(
        str(item.get("_prompt_text_override") or item.get("prompt_text") or item.get("text") or "")
    )
    fragments = [
        fragment.strip(" ，,。！？!?；;、")
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if fragment.strip(" ，,。！？!?；;、")
    ]
    safe_fragments = [
        fragment
        for fragment in fragments
        if 4 <= len(fragment) <= 140
        and not any(term and term in _normalize_for_match(fragment) for term in exclude_terms)
    ]
    if not safe_fragments:
        return ""
    selected: list[str] = []
    total_len = 0
    for fragment in safe_fragments:
        if total_len + len(fragment) > MAX_TEXT_CHARS:
            break
        selected.append(fragment)
        total_len += len(fragment)
        if len(selected) >= 2:
            break
    return " ".join(selected).strip()


def _title_shape_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> tuple[str, str]:
    title = _strip_prompt_noise(str(item.get("title") or ""))
    reason = _title_shape_block_reason(title, exclude_terms=exclude_terms)
    if not reason:
        reason = _title_shape_source_block_reason(item, exclude_terms=exclude_terms)
    if reason:
        return "", ""
    return title, "title_shape:title"


def _title_shape_block_reason(title: str, *, exclude_terms: list[str]) -> str:
    normalized_title = _normalize_for_match(title)
    blocked_terms = [_normalize_for_match(term) for term in (*TITLE_SHAPE_BLOCK_TERMS, *exclude_terms) if term]
    compact_len = len(re.sub(r"\s+", "", title))
    if compact_len < 4 or compact_len > 24:
        return "length"
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", title):
        return "blank_or_symbol"
    if _blocked_prompt_fragment(normalized_title, blocked_terms):
        return "blocked_term_or_format"
    if re.search(r"[\U0001F300-\U0001FAFF]", title):
        return "emoji"
    if re.search(r"[0-9一二三四五六七八九十]+个?月|[0-9一二三四五六七八九十]+岁|[一二三四五六七八九十]段|[1234]段", title):
        return "age_or_stage"
    if re.search(r"[?？]{2,}|[!！]{2,}", title):
        return "punctuation"
    if sum(1 for mark in ("｜", "|", "：", ":", "✅", "❓", "➡") if mark in title) >= 2:
        return "column_like"
    return ""


def _title_shape_source_block_reason(item: dict[str, Any], *, exclude_terms: list[str]) -> str:
    risk_tags = set(item.get("risk_tags") or [])
    if risk_tags & {"竞品品牌", "广告口吻", "评论口吻", "产品动作风险"}:
        return "source_risk_tag"
    normalized_context = _normalize_for_match(
        " ".join(
            str(value or "")
            for value in (
                item.get("text"),
                item.get("prompt_text"),
                item.get("source_keyword"),
            )
        )
    )
    blocked_terms = [_normalize_for_match(term) for term in TITLE_SHAPE_SOURCE_BLOCK_TERMS if term]
    if _blocked_prompt_fragment(normalized_context, blocked_terms):
        return "source_blocked_term"
    return ""


def _opening_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> tuple[str, str]:
    explicit = _curated_prompt_text(item, exclude_terms=exclude_terms, target_layer=REAL_USER_OPENING_LAYER)
    if explicit:
        return explicit, str(item.get("layer_reason") or "opening_curated:prompt_text")
    text = _strip_prompt_noise(str(item.get("text") or ""))
    blocked_terms = [_normalize_for_match(term) for term in (*PROMPT_VIEW_BLOCK_TERMS, *exclude_terms) if term]
    fragments = [
        fragment.strip(" \t，,。！？!?；;、")
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if fragment.strip(" \t，,。！？!?；;、")
    ]
    for fragment in fragments[:3]:
        normalized_fragment = _normalize_for_match(fragment)
        if _blocked_prompt_fragment(normalized_fragment, blocked_terms):
            continue
        if any(mark in fragment for mark in ("✅", "☑", "✔")):
            continue
        fragment_hit = _first_term_hit(normalized_fragment, OPENING_LAYER_TERMS)
        if fragment_hit and 10 <= len(fragment) <= 80:
            return fragment, f"opening_snippet:{fragment_hit}"
        clauses = _route_fragment_clauses(fragment)
        for clause in clauses:
            normalized_clause = _normalize_for_match(clause)
            if _blocked_prompt_fragment(normalized_clause, blocked_terms):
                continue
            hit = _first_term_hit(normalized_clause, OPENING_LAYER_TERMS)
            if hit and 6 <= len(clause) <= 80:
                return clause, f"opening_snippet:{hit}"
        if 10 <= len(fragment) <= 80:
            return fragment, "opening_snippet:first_sentence"
    return "", ""


def _texture_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> tuple[str, str]:
    explicit = _curated_prompt_text(
        item,
        exclude_terms=exclude_terms,
        min_chars=3,
        target_layer=REAL_USER_TEXTURE_LAYER,
    )
    if explicit:
        return explicit, str(item.get("layer_reason") or "texture_curated:prompt_text")
    text = _strip_prompt_noise(str(item.get("text") or ""))
    blocked_terms = [_normalize_for_match(term) for term in (*PROMPT_VIEW_BLOCK_TERMS, *exclude_terms) if term]
    fragments = [
        fragment.strip(" \t，,。！？!?；;、")
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if fragment.strip(" \t，,。！？!?；;、")
    ]
    normalized_exclude_terms = [term for term in exclude_terms if term]
    for fragment in fragments:
        normalized_fragment = _normalize_for_match(fragment)
        if _blocked_prompt_fragment(normalized_fragment, blocked_terms):
            continue
        hit = _first_term_hit(normalized_fragment, TEXTURE_LAYER_TERMS)
        if not hit:
            continue
        if any(term in normalized_fragment for term in normalized_exclude_terms):
            continue
        if any(mark in fragment for mark in ("✅", "☑", "✔")):
            continue
        clauses = [
            clause.strip(" \t，,。！？!?；;、")
            for clause in re.split(r"[，,；;]", fragment)
            if clause.strip(" \t，,。！？!?；;、")
        ]
        for clause in clauses or [fragment]:
            normalized_clause = _normalize_for_match(clause)
            if hit and _normalize_for_match(hit) not in normalized_clause:
                continue
            if 3 <= len(clause) <= 90:
                return clause, f"texture_snippet:{hit}"
        if 3 <= len(fragment) <= 90:
            return fragment, f"texture_snippet:{hit}"
    return "", ""


def _detail_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> tuple[str, str]:
    explicit = _curated_prompt_text(item, exclude_terms=exclude_terms, target_layer=REAL_USER_DETAIL_LAYER)
    if explicit:
        return explicit, str(item.get("layer_reason") or "detail_curated:prompt_text")
    text = _strip_prompt_noise(str(item.get("text") or ""))
    blocked_terms = [_normalize_for_match(term) for term in (*PROMPT_VIEW_BLOCK_TERMS, *exclude_terms) if term]
    fragments = [
        fragment.strip(" \t，,。！？!?；;、")
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if fragment.strip(" \t，,。！？!?；;、")
    ]
    for fragment in fragments:
        for clause in _route_fragment_clauses(fragment):
            normalized_clause = _normalize_for_match(clause)
            if _blocked_prompt_fragment(normalized_clause, blocked_terms):
                continue
            hit = _first_term_hit(normalized_clause, DETAIL_LAYER_TERMS)
            if hit and 8 <= len(clause) <= 90:
                return clause, f"detail_snippet:{hit}"
    return "", ""


def _ending_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> tuple[str, str]:
    explicit = _curated_prompt_text(item, exclude_terms=exclude_terms, target_layer=REAL_USER_ENDING_LAYER)
    if explicit:
        return explicit, str(item.get("layer_reason") or "ending_curated:prompt_text")
    text = _strip_prompt_noise(str(item.get("text") or ""))
    blocked_terms = [_normalize_for_match(term) for term in (*PROMPT_VIEW_BLOCK_TERMS, *exclude_terms) if term]
    fragments = [
        fragment.strip(" \t，,。！？!?；;、")
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if fragment.strip(" \t，,。！？!?；;、")
    ]
    for fragment in reversed(fragments):
        normalized_fragment = _normalize_for_match(fragment)
        if _blocked_prompt_fragment(normalized_fragment, blocked_terms):
            continue
        hit = _first_term_hit(normalized_fragment, ENDING_LAYER_TERMS)
        if not hit:
            continue
        clauses = [
            clause.strip(" \t，,。！？!?；;、")
            for clause in re.split(r"[，,；;]", fragment)
            if clause.strip(" \t，,。！？!?；;、")
        ]
        for clause in reversed(clauses or [fragment]):
            normalized_clause = _normalize_for_match(clause)
            if _normalize_for_match(hit) in normalized_clause and 3 <= len(clause) <= 80:
                return clause, f"ending_snippet:{hit}"
        if 3 <= len(fragment) <= 80:
            return fragment, f"ending_snippet:{hit}"
    return "", ""


def _route_prompt_text(item: dict[str, Any], *, exclude_terms: list[str]) -> tuple[str, str]:
    explicit = _curated_prompt_text(item, exclude_terms=exclude_terms, target_layer=REAL_USER_ROUTE_LAYER)
    if explicit:
        return explicit, str(item.get("layer_reason") or "route_curated:prompt_text")
    text = _strip_prompt_noise(str(item.get("text") or ""))
    blocked_terms = [_normalize_for_match(term) for term in (*PROMPT_VIEW_BLOCK_TERMS, *exclude_terms) if term]
    fragments = [
        fragment.strip(" \t，,。！？!?；;、")
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if fragment.strip(" \t，,。！？!?；;、")
    ]
    candidates: list[tuple[str, str]] = []
    for fragment in fragments:
        normalized_fragment = _normalize_for_match(fragment)
        if not _blocked_prompt_fragment(normalized_fragment, blocked_terms):
            fragment_hit = _first_term_hit(normalized_fragment, ROUTE_LAYER_TERMS)
            if fragment_hit and 12 <= len(fragment) <= 140:
                weakened = _weaken_route_prompt_text(fragment)
                candidates.append((weakened or fragment, f"route_snippet:{fragment_hit}"))
        for clause in _route_fragment_clauses(fragment):
            normalized_clause = _normalize_for_match(clause)
            if _blocked_prompt_fragment(normalized_clause, blocked_terms):
                continue
            hit = _first_term_hit(normalized_clause, ROUTE_LAYER_TERMS)
            if not hit:
                continue
            if 12 <= len(clause) <= 140:
                weakened = _weaken_route_prompt_text(clause)
                candidates.append((weakened or clause, f"route_snippet:{hit}"))
    if candidates:
        return candidates[0]
    return "", ""


def _weaken_route_prompt_text(text: str) -> str:
    normalized = _normalize_for_match(text)
    focus_parts: list[str] = []
    if any(term in normalized for term in ("中招", "请假", "保护力", "抵抗力", "免疫", "不生病", "少生病")):
        focus_parts.append("关注保护力")
    if any(term in normalized for term in ("眼脑", "dha", "ara", "叶黄素", "燕窝酸", "看书", "写字", "画画")):
        focus_parts.append("关注眼脑相关营养")
    if any(term in normalized for term in ("营养", "全面", "基础营养", "补充", "跟上")):
        focus_parts.append("关注日常营养补充")
    if any(term in normalized for term in ("成长", "长身体", "长肉", "长个", "身高", "体重", "发育", "结实")):
        focus_parts.append("关注成长阶段营养")
    focus_parts = _unique_preserving_order(focus_parts)

    parts: list[str] = []

    if any(term in normalized for term in ("兴趣班", "集体活动")):
        parts.append("兴趣班/集体活动接触人多")
    elif any(term in normalized for term in ("幼儿园", "上学", "放学", "老师", "同学", "班里")):
        parts.append("上学后接触人多")
    elif any(term in normalized for term in ("户外", "活动量", "疯跑", "运动", "跳绳", "跑")):
        parts.append("户外活动多、活动量大")
    elif any(term in normalized for term in ("看书", "写字", "画画", "绘本", "用眼", "用脑")):
        parts.append("日常用眼用脑多了")
    elif any(term in normalized for term in ("不是很懂", "不太懂", "不懂", "专业词", "专业名词")):
        parts.append("不太懂专业词")
    elif any(term in normalized for term in ("挑食", "饭量", "吃饭", "胃口", "嘴刁", "挑嘴")):
        parts.append("吃饭挑/饭量不稳")
    elif any(term in normalized for term in ("随手记", "记录", "为什么选", "选旺玥理由")):
        parts.append("随手记选旺玥理由")
    elif any(term in normalized for term in ("见底", "又开", "一罐", "一听", "固定喝奶", "喝奶")):
        parts.append("固定喝奶习惯")
    elif any(term in normalized for term in ("成长", "长身体", "长肉", "长个", "身高", "体重", "发育", "结实")):
        parts.append("成长阶段关注营养")
    elif any(term in normalized for term in ("儿童奶粉", "选奶", "挑奶", "对比", "做功课", "功课", "成分", "配料")):
        parts.append("选儿童奶粉时看成分")
    elif any(term in normalized for term in ("贵", "价格", "肉疼", "账单")):
        parts.append("价格不低，会认真看")

    if "关注保护力" in focus_parts and "关注眼脑相关营养" in focus_parts:
        parts.append("关注眼脑相关营养")
    elif "关注日常营养补充" in focus_parts and "关注成长阶段营养" in focus_parts:
        parts.append("关注日常营养补充")
    elif "关注保护力" in focus_parts:
        parts.append("担心容易中招，关注保护力")
    else:
        parts.extend(focus_parts)

    unique_parts = _unique_preserving_order(parts)
    if unique_parts:
        return "；".join(unique_parts[:2])

    softened = _strip_route_sentence_connectors(text)
    return softened if 8 <= len(softened) <= 60 else ""


def _strip_route_sentence_connectors(text: str) -> str:
    result = _strip_prompt_noise(text)
    result = re.sub(r"(?:我|妈妈|当妈的)?(?:才)?开始(?:认真)?(?:看|研究|选|挑)[^，,。！？!?；;]{0,16}", "", result)
    result = re.sub(r"(?:后来|最后|于是|所以)?(?:就)?(?:选了|选的|选|换了|换成|定了|入手)[^，,。！？!?；;]{0,12}", "", result)
    result = re.sub(r"(?:主要是|就是|其实)?(?:看中|看重|冲着)[^，,。！？!?；;]{0,18}", "", result)
    result = result.replace("旺玥", "儿童奶粉")
    result = re.sub(r"\s+", "", result)
    return result.strip(" ，,。！？!?；;、")


def _unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize_for_match(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _curated_prompt_text(
    item: dict[str, Any],
    *,
    exclude_terms: list[str],
    min_chars: int = 8,
    target_layer: str | None = None,
) -> str:
    if not _has_curated_prompt_text(item):
        return ""
    if target_layer and not _has_curated_prompt_text_for_layer(item, target_layer):
        return ""
    text = _strip_prompt_noise(str(item.get("prompt_text") or ""))
    if not min_chars <= len(text) <= 140:
        return ""
    blocked_terms = [_normalize_for_match(term) for term in (*PROMPT_VIEW_BLOCK_TERMS, *exclude_terms) if term]
    if _blocked_prompt_fragment(_normalize_for_match(text), blocked_terms):
        return ""
    return text


def _has_curated_prompt_text(item: dict[str, Any]) -> bool:
    source = str(item.get("prompt_text_source") or item.get("layer_reason") or "").strip().lower()
    if "curated" in source or "manual" in source:
        return True
    return bool(str(item.get("prompt_text") or "").strip()) and "real_ugc" in source


def _has_curated_prompt_text_for_layer(item: dict[str, Any], layer: str) -> bool:
    if not _has_curated_prompt_text(item):
        return False
    if layer == REAL_USER_ROUTE_LAYER:
        return True
    current_layer, _ = _example_layer(item)
    if layer == REAL_USER_OPENING_LAYER:
        return current_layer in {REAL_USER_OPENING_LAYER, REAL_USER_ENDING_LAYER}
    return current_layer == layer


def _route_fragment_clauses(fragment: str) -> list[str]:
    clauses = [
        clause.strip(" \t，,。！？!?；;、")
        for clause in re.split(r"[，,；;]", fragment)
        if clause.strip(" \t，,。！？!?；;、")
    ]
    if any(12 <= len(clause) <= 140 for clause in clauses):
        return clauses
    return [fragment]


def _blocked_prompt_fragment(normalized_fragment: str, blocked_terms: list[str]) -> bool:
    if any(term and term in normalized_fragment for term in blocked_terms):
        return True
    if re.search(r"\d+\s*[岁歲]|[两兩三四五六七八九十]\s*[岁歲]", normalized_fragment):
        return True
    if any(mark in normalized_fragment for mark in ("✅", "☑", "✔", "1️⃣", "2️⃣", "3️⃣", "mg/100g")):
        return True
    return False


def _example_layer(item: dict[str, Any]) -> tuple[str, str]:
    layer = str(item.get("example_layer") or "").strip()
    reason = str(item.get("layer_reason") or "").strip()
    if layer in {
        REAL_USER_ROUTE_LAYER,
        REAL_USER_DETAIL_LAYER,
        REAL_USER_TITLE_SHAPE_LAYER,
        REAL_USER_OPENING_LAYER,
        REAL_USER_TEXTURE_LAYER,
        REAL_USER_ENDING_LAYER,
        REAL_USER_REJECT_LAYER,
    }:
        return layer, reason
    return infer_real_user_example_layer(item)


def _first_term_hit(normalized_text: str, terms: tuple[str, ...]) -> str | None:
    for term in terms:
        normalized_term = _normalize_for_match(term)
        if normalized_term and normalized_term in normalized_text:
            return term
    return None


def _strip_prompt_noise(text: str) -> str:
    text = re.sub(r"#([^#\[]+?)\[话题\]#", "", text)
    text = re.sub(r"#([^#\[]+?)\[搜索高亮\]#", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _read_note_items(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_note_ids: set[str] = set()
    stats = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stats["read"] += 1
            note_id = str(row.get("note_id") or "").strip()
            if not note_id or note_id in seen_note_ids:
                stats["duplicate"] += 1
                continue
            seen_note_ids.add(note_id)
            title = _clean_text(row.get("title"), limit=MAX_TITLE_CHARS)
            text = _clean_text(row.get("content"), limit=MAX_TEXT_CHARS)
            if not _usable_note_text(title, text):
                stats["filtered"] += 1
                continue
            items.append(
                _build_item(
                    source_type="note",
                    text=text,
                    title=title,
                    source_keyword=row.get("source_keyword") or row.get("search_keywords"),
                    note_id=note_id,
                    comment_id=None,
                    url=row.get("note_url"),
                    extra={"publish_time": row.get("publish_time"), "likes": row.get("likes")},
                )
            )
            stats["kept"] += 1
    return items, dict(stats)


def _read_comment_items(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stats["read"] += 1
            text = _clean_text(row.get("content"), limit=COMMENT_MAX_CHARS)
            comment_id = str(row.get("comment_id") or "").strip()
            dedupe_key = _short_hash(comment_id, text)
            if not text or dedupe_key in seen:
                stats["duplicate"] += 1
                continue
            seen.add(dedupe_key)
            if not _usable_comment_text(text):
                stats["filtered"] += 1
                continue
            items.append(
                _build_item(
                    source_type="comment",
                    text=text,
                    title=_clean_text(row.get("note_title"), limit=MAX_TITLE_CHARS),
                    source_keyword=row.get("note_source_keyword") or row.get("search_keywords"),
                    note_id=row.get("note_id"),
                    comment_id=comment_id,
                    url=row.get("note_url"),
                    extra={"comment_type": row.get("comment_type"), "comment_likes": row.get("comment_likes")},
                )
            )
            stats["kept"] += 1
    return items, dict(stats)


def _build_item(
    *,
    source_type: str,
    text: str,
    title: str,
    source_keyword: str | None,
    note_id: str | None,
    comment_id: str | None,
    url: str | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    source_keyword = _clean_keyword(source_keyword)
    match_text = f"{title} {text} {source_keyword}"
    tags = infer_real_user_tags(match_text)
    risk_tags = infer_real_user_risk_tags(match_text, source_type=source_type)
    layer, layer_reason = infer_real_user_example_layer(
        {
            "source_type": source_type,
            "text": text,
            "title": title,
            "source_keyword": source_keyword,
            "tags": tags,
            "risk_tags": risk_tags,
        }
    )
    return {
        "source_type": source_type,
        "text": text,
        "prompt_text": _strip_prompt_noise(text),
        "title": title,
        "source_keyword": source_keyword,
        "note_id": str(note_id or "").strip(),
        "comment_id": str(comment_id or "").strip(),
        "url": str(url or "").strip(),
        "tags": tags,
        "risk_tags": risk_tags,
        "example_layer": layer,
        "layer_reason": layer_reason,
        "quality_score": _quality_score(text, title=title, source_type=source_type, risk_tags=risk_tags),
        "dedupe_hash": _short_hash(source_type, title, text),
        "extra": {key: value for key, value in extra.items() if value not in (None, "")},
    }


def _usable_note_text(title: str, text: str) -> bool:
    combined = f"{title} {text}".strip()
    if len(text) < NOTE_MIN_CHARS:
        return False
    if _emoji_only(combined):
        return False
    ad_like_hits = sum(word in combined for word in ("育儿师", "深耕奶粉行业", "安利", "值得推荐", "闭眼入"))
    if ad_like_hits >= 2:
        return False
    return True


def _usable_comment_text(text: str) -> bool:
    if len(text) < COMMENT_MIN_CHARS or len(text) > COMMENT_MAX_CHARS:
        return False
    if _emoji_only(text):
        return False
    if re.fullmatch(r"[\W_]+", text):
        return False
    return True


def _quality_score(text: str, *, title: str, source_type: str, risk_tags: list[str]) -> float:
    score = 10.0
    length = len(text)
    if source_type == "note":
        if 60 <= length <= 220:
            score += 4
        if title:
            score += 1
    else:
        if 8 <= length <= 60:
            score += 4
    score += len(infer_real_user_tags(f"{title} {text}")) * 0.6
    score -= len(risk_tags) * 0.8
    return round(score, 2)


def _clean_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    text = re.sub(r"#([^#\[]+?)\[话题\]#", "", text)
    text = re.sub(r"#([^#\[]+?)\[搜索高亮\]#", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def _clean_keyword(value: Any) -> str:
    text = str(value or "").strip()
    parts = [part.strip() for part in re.split(r"[;|,，]", text) if part.strip()]
    return "；".join(dict.fromkeys(parts))


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _emoji_only(text: str) -> bool:
    stripped = re.sub(r"\[[^\]]+R\]", "", str(text or "")).strip()
    stripped = re.sub(r"[\s\W_]+", "", stripped)
    return not stripped


def _source_hash(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(str(path.stat().st_size).encode("utf-8"))
        digest.update(str(int(path.stat().st_mtime)).encode("utf-8"))
    return digest.hexdigest()


def _short_hash(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


async def _next_asset_version(db: AsyncSession, asset_key: str) -> int:
    result = await db.execute(
        select(AssetRegistry.version_no)
        .where(AssetRegistry.asset_type == REAL_USER_EXAMPLE_POOL_ASSET_TYPE, AssetRegistry.asset_key == asset_key)
        .order_by(AssetRegistry.version_no.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1


def dump_import_result(result: RealUserPoolImportResult) -> str:
    return json.dumps(real_user_pool_import_summary(result), ensure_ascii=False, indent=2)
