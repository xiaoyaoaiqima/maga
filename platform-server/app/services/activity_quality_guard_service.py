"""Activity-scoped quality guard profiles for generated batch content."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


A2_SENTIMENT_COMMENT_PROFILE_KEY = "a2_sentiment_comment_202606"
A2_SENTIMENT_POST_PROFILE_KEY = "a2_sentiment_post_202606"
A2_NEGATIVE_POST_COMMENT_PROFILE_KEY = "a2_negative_post_comment_202606"
A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY = "a2_plot_discussion_comment_202606"
A2_COMMENT_PROFILE_KEYS = {
    A2_SENTIMENT_COMMENT_PROFILE_KEY,
    A2_NEGATIVE_POST_COMMENT_PROFILE_KEY,
    A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY,
}


@dataclass(frozen=True)
class QualityGuardProfile:
    profile_key: str
    label: str
    forbidden_terms: tuple[str, ...] = ()
    context_required_fields: tuple[str, ...] = ()
    context_keyword_allowlist: tuple[str, ...] = ()
    keyword_markers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    default_keyword: str | None = None
    body_must_include_any_by_keyword: dict[str, tuple[str, ...]] = field(default_factory=dict)
    body_replacements: dict[str, str] = field(default_factory=dict)
    context_replacements: dict[str, str] = field(default_factory=dict)
    export_profile: str | None = None


A2_SENTIMENT_COMMENT_FORBIDDEN_TERMS = (
    # A2 活动硬禁词只拦负向传播、绝对承诺和条文式检测写法；常见口语先走替换修复。
    "断货",
    "缺货",
    "断粮",
    "断档",
    "焦虑",
    "恐慌",
    "慌",
    "急",
    "担心",
    "不确定",
    "悬念",
    "猜",
    "抱娃",
    "睡不着",
    "直接着喝",
    "愿意喝着",
    "愿意喝上",
    "专家",
    "专业指标",
    "盲信",
    "绝对安全",
    "保证没问题",
    "无风险",
    "治疗",
    "截图",
    "群聊",
    "26年",
    "2月后",
    "旧批次",
    "μg/kg",
    "ug/kg",
    "高于中国标准",
    "全球最严格",
)

A2_NEGATIVE_POST_COMMENT_FORBIDDEN_TERMS = (
    "断货",
    "缺货",
    "焦虑",
    "恐慌",
    "犹豫",
    "纠结",
    "慌",
    "急",
    "担心",
    "不确定",
    "屁粮",
    "投资",
    "职场",
    "租房",
    "上学",
    "硬数据",
    "检测单",
    "记一下",
    "记了一下",
    "留意下",
    "留意一下",
    "省得再跑一趟",
    "给需要的妈妈说一声",
    "愿意喝着",
    "要不要换",
    "要不要再换",
    "要不要转",
    "要不要再转",
    "官方公告",
    "公告",
    "客服通知",
    "教程",
    "步骤",
    "半勺",
    "一勺",
    "两勺",
    "一两勺",
    "勺",
    "绝对",
    "保证没问题",
    "无风险",
    "治疗",
    "马上适应",
    "立刻适应",
)
A2_NEGATIVE_POST_KEYWORDS = ("到货安抚", "转奶安抚")
A2_NEGATIVE_POST_ARRIVAL_MARKERS = (
    "有货",
    "到货",
    "补货",
    "门店",
    "母婴店",
    "店里",
    "店员",
    "导购",
    "新批次",
    "新到",
    "刚到",
    "到了",
    "到店",
    "上架",
    "货架",
    "摆出来",
    "买到",
    "能买",
    "补到",
    "能补到",
    "快喝完",
    "续上",
    "补上",
    "问问",
)
A2_NEGATIVE_POST_TRANSFER_MARKERS = (
    "转奶",
    "换奶",
    "转回来",
    "转回",
    "拉回来",
    "拉回来了",
    "不转",
    "不转了",
    "换回来",
    "换回",
    "回到a2",
    "回a2",
    "过渡",
    "慢慢来",
    "慢慢加",
    "慢慢换",
    "慢慢转",
    "一步步来",
    "一点一点来",
    "一点点来",
    "混着来",
    "混着",
    "先试",
    "试一罐",
    "一罐试试",
    "一罐让宝宝试试看",
    "一罐试试看",
    "买罐试试看",
    "拿一罐",
    "接一罐看看",
    "喝喝看",
    "换着喝",
    "换一小罐",
    "先补一罐",
    "老客",
    "一直喝",
    "继续喝",
    "喝至初",
    "先喝至初",
    "继续至初",
    "继续喝至初",
    "续罐",
    "续着",
    "先看批次",
    "批次信息",
    "批次报告",
    "批次问题",
    "检测报告",
    "看报告",
    "报告能查",
    "报告",
    "自己这罐",
    "自己手上这罐",
    "自己家这罐",
    "这罐情况",
    "相信a2",
    "继续a2",
    "换别的",
    "转别的",
    "不转别的",
    "换牌子",
    "不换牌子",
    "换别的牌子",
    "试下别的牌子",
    "先不换",
    "不换了",
    "不太想换",
    "能续上",
    "又能续上",
    "接着喝",
    "质量一直挺稳",
    "质量挺稳",
    "不想折腾",
    "不折腾",
    "少换一次",
    "少换牌子",
    "喝得好好的",
    "喝得好好",
    "不用急着换",
    "自家节奏",
    "被带偏",
    "被带跑",
    "先别急着换",
    "别急着换",
    "跟着评论走",
    "跟风换",
    "马上换",
    "别跟风转",
    "跟风转",
    "不急着换",
    "不急着转",
    "别乱换",
    "不用乱换",
)
A2_NEGATIVE_POST_NOTE_LIKE_DAILY_PURCHASE_PATTERN = re.compile(
    r"(?:今天|刚才|昨天)[^，。！？；;]{0,12}(?:买|囤|挑|补)[^，。！？；;]{0,12}(?:宝宝|娃|辅食|沐浴露|磨牙|果泥|袜子)[^，。！？；;]{0,18}(?:发现|瞥见|看到|瞅见)a2",
    re.IGNORECASE,
)
A2_NEGATIVE_POST_BAD_BATCH_CHECK_ATTRIBUTION_PATTERN = re.compile(
    r"(?:带批批检的姐妹|批批检的姐妹|带批批检的宝妈|批批检的宝妈)"
)
A2_COMBO_KEYWORDS = ("有货+批批检", "批批检+转奶", "有货+转奶")
A2_BATCH_REPORT_REQUIRED_KEYWORDS = ("有货+批批检", "批批检+转奶")
A2_COMPETITOR_GROUPS: dict[str, tuple[str, ...]] = {
    "达能组": ("爱他美", "达能"),
    "雀巢组": ("雀巢", "超启能恩"),
    "美素组": ("美素", "皇家美素", "皇美"),
}
A2_OUT_OF_SCOPE_COMPETITOR_TERMS = (
    "美赞臣",
    "飞鹤",
    "星飞帆",
    "惠氏",
    "启赋",
    "雅培",
    "君乐宝",
    "贝因美",
    "合生元",
    "诺优能",
)
A2_UNCONFIRMED_COMPETITOR_VALUE_PATTERN = re.compile(
    r"(?:雀巢|超启能恩)(?:也)?(?:的|那边)?0\.03|(?:雀巢|超启能恩)和a2的0\.03"
)
A2_AMBIGUOUS_COMPETITOR_003_PATTERN = re.compile(
    r"(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩)(?:和|跟)a2的0\.03"
    r"|(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩)和0\.03"
    r"|(?:拿|把)(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩)和0\.03"
    r"|(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩)(?:那边|这边|这里)(?:蜡样检测)?0\.03"
    r"|(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩)[^，。！？；;]{0,12}报告里那项0\.03"
)
A2_BAD_003_PAIN_POINT_PATTERN = re.compile(
    r"0\.03(?:一起)?(?:对比|比)(?:肚肚|便便|奶量|适应|喝奶|反应)"
)
A2_BAD_003_COMPETITOR_COMPARISON_PATTERN = re.compile(
    r"0\.03(?:这条线|这点|这个数值|这项)?(?:比|对比)(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩|0\.2)"
    r"|(?:爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩|0\.2)(?:比|对比)0\.03"
)
A2_UNCONFIRMED_COMPETITOR_BATCH_REPORT_PATTERN = re.compile(
    r"(?:爱他美|达能|皇家美素|皇美|(?<!皇家)美素)[^，。！？；;]{0,8}每批(?:报告|检测|检)"
)
A2_UNCONFIRMED_COMPETITOR_SAMPLE_BATCH_PATTERN = re.compile(
    r"(?:雀巢|超启能恩)[^，。！？；;]{0,8}样批"
)
A2_VAGUE_APTAMIL_COMPARISON_PATTERN = re.compile(
    r"爱他美[^，。！？；;]{0,18}(?:也)?(?:看|问|研究|对比|比|参考|查|翻)"
    r"|(?:看|问|研究|对比|比|参考|查|翻)[^，。！？；;]{0,18}爱他美"
)
A2_ZHICHU_PRODUCT_SPLIT_PATTERN = re.compile(
    # a2至初是完整产品名；“至初这边有a2现货”会把产品名拆成两个对象，交付前直接拦截。
    r"(?<!a2)至初(?:这边|那边|这儿|那儿|这里|那里|店里|门店|母婴店|导购|柜上|货架)?"
    r"[^，。！？；;]{0,8}a2[^，。！？；;]{0,8}"
    r"(?:现货|有货|到货|补货|新到|上架|调货|能买|买到|到了|来货)",
    re.IGNORECASE,
)
A2_STOCK_OVERCLAIM_PATTERN = re.compile(
    r"官方(?:公告|通知)|客服通知|(?:全网|全国)(?:有货|补货|到货)|保证(?:能)?买到|现货充足"
)
A2_SUPPLY_TREND_CLAIM_PATTERN = re.compile(
    r"货源[^，。！？；;]{0,10}(?:慢慢)?(?:动起来|在动)"
    r"|(?:陆续|慢慢)(?:有货|到货|补货|回货|到)"
    r"|(?:会|还会|应该|估计|感觉)[^，。！？；;]{0,12}(?:陆续到|陆续补|补货|有货|回货)"
    r"|(?:有点|开始|正在)?回货|放货"
)
A2_PERSONAL_SUPPLY_TREND_CONTEXT_PATTERN = re.compile(
    # 确认真人 demo 里会用“问了几家店/导购说快了/抱点希望”表达个人问到的供货感。
    # 这类保留为个人来源，不等同于官方补货或品牌承诺。
    r"问了几家店(?:[，,]\s*)?(?:说)?[^，。！？；;]{0,10}(?:陆续有货|有货)"
    r"|导购[^，。！？；;]{0,12}(?:说|跟我说)[^，。！？；;]{0,12}(?:快了|过两天回来货|回来货)"
    r"|我这边导购[^，。！？；;]{0,12}说快了"
    r"|对放货抱点希望"
)
A2_BRAND_BAD_STOCK_WORDING_PATTERN = re.compile(
    r"赶紧来报个信|付款不犹豫|后面再说后面"
    r"|闭眼冲|可以冲了|直接冲|先冲"
    r"|调货|能调到|能调货|帮忙留货|帮.*留(?:一罐|这罐)|能留(?:一罐|这罐)|留(?:一罐|这罐)"
    # “囤几罐”是正常用户表达，只拦“囤这罐”这类生硬指代。
    r"|囤这罐"
    r"|多跑[一二两三四五六七八九十\d几]?家店|跑[一二两三四五六七八九十\d几]?家店|跑店"
    r"|(?:我这边|我们这边|我这里|我们这里)[^，。！？；;]{0,8}(?:还没消息|还没看到有?a2|没看到有?a2)"
)
A2_TRANSFER_TUTORIAL_PATTERN = re.compile(
    r"半勺|一勺|两勺|一两勺|按比例|(?:第[一二三四五六七八九十\d]+天|[一二三四五六七八九十\d]+天后)[^，。！？；;]{0,6}(?:全换|全转)"
    r"|直接换|马上适应|立刻适应"
)
A2_BRAND_BAD_TRANSFER_FRAMING_PATTERN = re.compile(
    r"本来[^，。！？；;]{0,12}(?:想换|准备换|说服自己换)"
    r"|(?:看到|看见)[^，。！？；;]{0,8}(?:有货|可下单)[^，。！？；;]{0,8}(?:立刻|马上)?打消念头"
    r"|转奶[^，。！？；;]{0,12}(?:够乱|乱了|乱)"
    r"|转来转去"
    r"|(?:买到|买了|补到)(?:a2至初|至初|a2)[^，。！？；;]{0,8}回去"
)
A2_AI_TEMPLATE_CONDITIONAL_QUESTION_PATTERN = re.compile(
    # 拦截“能买到a2的话，是不是先继续原来的就行”这类把规则拼成条件问句的模板腔。
    r"(?:如果|要是)?(?:(?:a2|A2|至初)[^，。！？；;]{0,6}(?:能买到|能补到|能拍到|能下单|有货)"
    r"|(?:能买到|能补到|能拍到|能下单)[^，。！？；;]{0,6}(?:a2|A2|至初))的话[，,]?(?:我)?是不是"
    r"|(?:如果|要是)(?:a2|A2|至初)[^，。！？；;]{0,6}(?:能买到|能补到|能拍到|能下单|有货)[，,]?(?:我)?是不是"
    r"|(?:如果|要是)(?:能买到|能补到|能拍到|能下单)[^，。！？；;]{0,6}(?:a2|A2|至初)[，,]?(?:我)?是不是"
    r"[^，。！？；;]{0,18}(?:继续原来的|先拍|先买|不换|不转|就行|比较稳|比较好|没必要急着换)"
)
A2_PRODUCT_EFFECT_CLAIM_PATTERN = re.compile(
    r"(?:喝|换|转|用了|试了)?(?:a2至初|A2至初|a2|A2|至初)[^，。！？；;]{0,8}(?:后|以后|之后)"
    r"[^，。！？；;]{0,12}(?:便便|肚肚|过敏|奶量|长肉|体重)[^，。！？；;]{0,8}"
    r"(?:好|好了|改善|稳了|规律|顺了|涨|上来|长)"
)
A2_REPORT_OVERCLAIM_PATTERN = re.compile(
    r"(?:报告|检测报告|检测单)[^，。！？；;]{0,10}(?:证明|保证|代表|说明)[^，。！？；;]{0,12}(?:安全|没问题|放心喝|可以放心)"
    r"|未检出[^，。！？；;]{0,8}(?:所以|就)[^，。！？；;]{0,8}(?:放心喝|安全|没问题)"
    r"|每批[^，。！？；;]{0,8}过检"
    r"|批批[^，。！？；;]{0,8}过检"
)
A2_SCAN_BEFORE_CAN_IN_HAND_PATTERN = re.compile(
    r"(?:下单后|付款后|拍下后)[^，。！？；;]{0,12}(?:扫|扫码|扫一下)[^，。！？；;]{0,12}(?:物流码|罐底码|罐底)"
)
A2_SUPPLY_PRESSURE_TRANSFER_PATTERN = re.compile(
    # 拦截“过往供应压力 -> 被动转/换奶 -> 现在有货又稳住”的回忆链路，
    # 避免有货+转奶评论重新勾起货少、买不到等负面记忆。
    r"(?:被)?(?:缺货|断货|断粮|货少|没货|买不到|不好买|难买|等货|抢货)"
    r"[^，。！？；;]{0,20}(?:逼|想转|想换|换奶|转奶|做功课|看别[家个的]?|看其他|备选|先不看|稳住|踏实)"
    r"|(?:逼|想转|想换|换奶|转奶|做功课|看别[家个的]?|看其他|备选)"
    r"[^，。！？；;]{0,20}(?:缺货|断货|断粮|货少|没货|买不到|不好买|难买|等货|抢货)"
    r"|(?:调货|有货|到货|补货)[^，。！？；;]{0,12}(?:又稳住|稳住了|又踏实|踏实了|转回来|换回来|先不看了)"
)
A2_HOUSEHOLD_STOCK_MARKERS = ("家里", "家中", "家里的", "手里", "手上", "手头", "那罐", "这罐")
A2_FEEDING_ANXIETY_STOCK_PATTERN = re.compile(r"断顿|没奶喝|没奶粉喝|奶粉接不上|口粮接不上|接不上奶")
A2_003_CONTEXT_PATTERN = re.compile(
    r"蜡样|蜡毒|那个检测|那项检测|报告里那项|报告里的那项|报告里那条|检测数值|检测这条线|检测线|检测那条线"
)
A2_BATCH_REPORT_MARKERS = ("物流码", "报告", "批次", "批批检", "每批", "检测", "蜡样", "质检", "这批", "检测数据", "质检数据")
A2_SPECIFIC_ADVANTAGE_MARKERS = (
    "a2批次信息更清楚",
    "a2每批",
    "a2批批检",
    "a2罐底扫码",
    "a2罐底",
    "a2物流码",
    "a2报告",
    "a2能查",
    "a2能扫",
    "a2能看到",
    "a2能看",
    "a2那边能",
    "a2这边能",
    "a2自己手里",
    "a2手里",
    "a2那罐",
    "a2这罐",
    "a2的批次信息",
    "a2的物流码",
            "a2的报告入口",
            "a2的报告",
            "a2有批次报告",
            "a2有检测报告",
            "a2有报告",
            "a2报告里那项0.03",
    "a2自己扫",
    "a2能自己扫",
    "a2自己能扫",
    "a2能扫物流码",
    "a2能扫罐底物流码",
    "a2可以扫物流码",
    "a2可以扫罐底物流码",
    "a2罐底物流码",
    "a2每批报告",
    "a2每批检测",
    "a2每批都有检测",
    "a2每批的信息",
    "a2对应批次报告",
    "a2自己这罐报告",
    "自己扫a2",
    "自己扫出来",
    "蜡样检测0.03",
    "那个检测0.03",
    "报告里那项0.03",
)
A2_DIRECTION_MARKER_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "有货+批批检": {
        "有货信息": ("有货", "到货", "补货", "问货", "快喝完", "新到", "店里"),
        "批批检信息": ("批批检", "物流码", "报告", "批次", "质检", "蜡样", "检测", "0.03"),
    },
    "批批检+转奶": {
        "批批检信息": ("批批检", "物流码", "报告", "批次", "质检", "蜡样", "检测", "0.03"),
        "转奶动作": ("转奶", "刚转", "想转", "准备转", "转过来", "慢慢转", "换奶", "过渡", "适应"),
    },
    "有货+转奶": {
        "有货信息": ("有货", "到货", "补货", "问货", "快喝完", "新到", "店里"),
        "转奶动作": ("转奶", "刚转", "想转", "准备转", "转过来", "慢慢转", "换奶", "过渡", "适应"),
        "批次报告": ("物流码", "报告", "批次", "检测", "0.03"),
    },
}
A2_LAB_NOTATION_TERMS = ("μg/kg", "ug/kg")
A2_INCOMPLETE_COMMENT_SUFFIXES = (
    "和",
    "跟",
    "把",
    "再",
    "先",
    "顺手",
    "心里",
    "宝宝",
    "能",
    "a2",
    "A2",
    "0",
    "0.",
)
A2_DIRECT_KEYWORD_MARKERS = {
    "有货+批批检": ("有货+批批检", "有货 批批检", "补货 批批检"),
    "批批检+转奶": ("批批检+转奶", "批批检 转奶", "报告 转奶"),
    "有货+转奶": ("有货+转奶", "有货 转奶", "补货 转奶"),
}
A2_PLOT_DISCUSSION_KEYWORD = "剧情讨论+门店引流"
A2_PLOT_DISCUSSION_PLOT_MARKERS = (
    "奶宝",
    "小奶宝",
    "妈妈",
    "找妈妈",
    "团聚",
    "第3集",
    "第三集",
    "山洞",
    "求援",
    "通讯",
    "呼叫",
    "寻宝",
    "巴克队长",
    "艾尔博士",
    "A2型奶牛",
    "奶牛群",
)
A2_PLOT_DISCUSSION_ACTIVITY_MARKERS = (
    "门店",
    "母婴店",
    "店里",
    "到店",
    "店员",
    "活动",
    "补货",
    "续奶粉",
    "续奶",
    "续上",
    "囤奶",
    "买4罐",
    "四罐",
    "4罐",
    "带够",
    "领到",
    "加赠",
    "对讲机",
    "周边",
)
A2_PLOT_DISCUSSION_MIN_CHARS = 21
A2_PLOT_DISCUSSION_MAX_CHARS = 50
A2_PLOT_DISCUSSION_CHILD_ACTIVITY_PATTERN = re.compile(
    r"(?:娃|孩子|小朋友|宝宝)[^，。！？；;]{0,12}(?:知道|听说|问|催|要|想要|想去|要去|吵着要|念叨)"
    r"[^，。！？；;]{0,12}(?:门店|店里|到店|买4罐|四罐|4罐|加赠|赠品|活动|催买奶粉)"
)
A2_PLOT_DISCUSSION_CHILD_STORE_DESIRE_PATTERN = re.compile(
    r"(?:娃|孩子|小朋友|宝宝)[^，。！？；;]{0,24}(?:说|喊|闹|念叨)"
    r"[^，。！？；;]{0,8}(?:想去|要去)[^，。！？；;]{0,8}(?:门店|店里|母婴店)"
    r"[^，。！？；;]{0,16}(?:对讲机|活动|周边)"
)
A2_PLOT_DISCUSSION_ODD_PLAY_PHRASES = (
    "愿意喝着演",
    "喝着演",
)
A2_PLOT_DISCUSSION_INVALID_WORDING_TERMS = (
    "A2牛牛",
    "A2稀有体质",
    "所有奶粉都叫A2型",
    "宝宝走散",
    "宝宝找妈妈",
    "宝宝找到妈妈",
    "打A1怪兽",
    "打A1大怪兽",
    "艾尔博士打A1",
    "汪汪队",
)
A2_PLOT_DISCUSSION_UNSUPPORTED_PLOT_TERMS = (
    "第6集",
    "第六集",
    "热气球",
    "雪地救援",
    "隧道救援",
    "洞穴救援",
    "营救企鹅",
    "最新一集",
    "奶宝救援队",
)
A2_PLOT_DISCUSSION_ACTIVITY_MISSTATEMENT_TERMS = (
    "超市买奶粉",
    "小礼品",
    "小礼物",
    "盲盒",
    "补两罐",
)
A2_POST_AI_TITLE_PATTERN = re.compile(
    r"(?:妈妈|宝妈|姐妹|转奶期)[^，。！？；;]{0,8}(?:别|不用|不要|不必|少点)(?:焦虑|纠结|慌)"
    r"|(?:别|不用|不要|不必|少点)(?:焦虑|纠结|慌)[^，。！？；;]{0,8}(?:妈妈|宝妈|姐妹)"
    r"|(?:别|不用|不要|不必|少点)(?:再)?(?:焦虑|纠结|慌)[^，。！？；;]{0,8}(?:转奶|换奶|报告|扫码|罐底)"
    r"|(?:转奶|换奶|报告|扫码|罐底)[^，。！？；;]{0,8}(?:别|不用|不要|不必|少点)(?:再)?(?:焦虑|纠结|慌)"
    r"|(?:扫|看|查)(?:一下|下)?(?:罐底|报告|码|物流码)[^，。！？；;]{0,8}(?:就行|就够|就安心|才安心)"
    r"|(?:攻略|指南|教程|科普|避坑|必看|收藏|一篇搞懂|看完就懂)"
)
A2_POST_JSON_LEAK_PATTERN = re.compile(
    r'^\s*[{[]\s*$|["“]?(?:title|标题|body|正文)["”]?\s*[:：]',
    re.IGNORECASE,
)
A2_POST_TRANSFER_DECISION_PATTERN = re.compile(
    r"(?:我该|该不该|要不要|适合不|合适不|合不合适)[^，。！？；;]{0,12}(?:转|换|试)(?:a2|A2|奶)"
    r"|(?:转|换|试)(?:a2|A2|奶)[^，。！？；;]{0,12}(?:适合不|合适不|合不合适)"
)
A2_POST_REPORT_SAFETY_DECISION_PATTERN = re.compile(
    r"(?:报告|检测|蜡样|质检)[^。！？；;]{0,32}(?:没问题|安全|放心喝)"
    r"|(?:没问题|安全|放心喝)[^。！？；;]{0,32}(?:报告|检测|蜡样|质检)"
)
A2_POST_REPORT_MARKERS = ("报告", "检测", "蜡样", "质检")
A2_POST_REPORT_SAFETY_DECISION_TERMS = ("没问题", "这样就行", "放心喝", "安不安全", "安全吗")
A2_POST_FEEDING_DECISION_PATTERN = re.compile(
    r"(?:会不会|会|能不能|可不可以|可以|该不该)[^。！？；;]{0,12}(?:给)?(?:宝宝|娃)[^。！？；;]{0,8}(?:喝|转|换)"
    r"|(?:给)?(?:宝宝|娃)[^。！？；;]{0,8}(?:能不能|可不可以|可以|该不该)[^。！？；;]{0,8}(?:喝|转|换)"
    r"|(?:给)?(?:宝宝|娃)?[^。！？；;]{0,8}喝这款吗"
)


QUALITY_GUARD_PROFILES: dict[str, QualityGuardProfile] = {
    A2_SENTIMENT_COMMENT_PROFILE_KEY: QualityGuardProfile(
        profile_key=A2_SENTIMENT_COMMENT_PROFILE_KEY,
        label="A2舆情改善评论专项守卫",
        forbidden_terms=A2_SENTIMENT_COMMENT_FORBIDDEN_TERMS,
        context_required_fields=("人设", "关键词", "扰动规则", "生文指令", "业务规则", "生文输出格式"),
        context_keyword_allowlist=A2_COMBO_KEYWORDS,
        keyword_markers={
            "有货+批批检": ("有货", "到货", "补货", "问货", "按需补", "快喝完", "物流码", "报告", "批次"),
            "批批检+转奶": ("批批检", "物流码", "报告", "批次", "质检", "蜡样", "转奶", "换奶", "过渡", "适应"),
            "有货+转奶": ("有货", "到货", "补货", "问货", "快喝完", "转奶", "换奶", "过渡", "适应"),
        },
        default_keyword="有货+批批检",
        body_replacements={
            "μg/kg": "",
            "ug/kg": "",
            "＜0.03": "<0.03",
            "＜ 0.03": "<0.03",
            "新西兰报告标准": "报告里",
            "高于中国标准": "标准细节更值得看",
            "全球最严格": "标准看着更细",
            "0.03报告": "蜡样检测0.03报告",
            "爱他美0.03": "爱他美样批也看，a2报告里那项0.03",
            "达能0.03": "达能也看，a2报告里那项0.03",
            "美素0.03": "美素也看，a2报告里那项0.03",
            "皇家美素0.03": "皇家美素也看，a2报告里那项0.03",
            "皇美0.03": "皇美也看，a2报告里那项0.03",
            "雀巢0.03": "雀巢也看，a2报告里那项0.03",
            "超启能恩0.03": "超启能恩也看，a2报告里那项0.03",
            "爱他美的0.03": "爱他美样批也看，a2报告里那项0.03",
            "达能的0.03": "达能也看，a2报告里那项0.03",
            "美素的0.03": "美素也看，a2报告里那项0.03",
            "皇家美素的0.03": "皇家美素也看，a2报告里那项0.03",
            "皇美的0.03": "皇美也看，a2报告里那项0.03",
            "雀巢的0.03": "雀巢也看，a2报告里那项0.03",
            "超启能恩的0.03": "超启能恩也看，a2报告里那项0.03",
            "爱他美和a2的0.03": "爱他美样批也看，a2报告里那项0.03",
            "达能和a2的0.03": "达能也看，a2报告里那项0.03",
            "美素和a2的0.03": "美素也看，a2报告里那项0.03",
            "皇家美素和a2的0.03": "皇家美素也看，a2报告里那项0.03",
            "皇美和a2的0.03": "皇美也看，a2报告里那项0.03",
            "雀巢和a2的0.03": "雀巢也看，a2报告里那项0.03",
            "超启能恩和a2的0.03": "超启能恩也看，a2报告里那项0.03",
            "爱他美和0.03": "爱他美样批也看，a2报告里那项0.03",
            "达能和0.03": "达能也看，a2报告里那项0.03",
            "美素和0.03": "美素也看，a2报告里那项0.03",
            "皇家美素和0.03": "皇家美素也看，a2报告里那项0.03",
            "皇美和0.03": "皇美也看，a2报告里那项0.03",
            "雀巢和0.03": "雀巢也看，a2报告里那项0.03",
            "超启能恩和0.03": "超启能恩也看，a2报告里那项0.03",
            "a2的0.03": "a2报告里那项0.03",
            "a2这边0.03": "a2报告里那项0.03",
            "报告里的0.03": "报告里那项0.03",
            "批次报告里0.03": "批次报告里那项0.03",
            "a2那项报告里那项0.03": "a2报告里那项0.03",
            "a2那项报告里那项": "a2报告里那项",
            "报告里报告里那项": "报告里那项",
            "0.03那项": "0.03",
            "a2每罐": "a2每批",
            "每罐": "这罐",
            "补一罐": "补货",
            "拿一罐": "补货拿",
            "新的一罐": "新到手的",
            "一罐": "这罐",
            "先先不忙": "先不忙",
            "没慌，": "",
            "没慌": "踏实",
            "慌": "不悬",
            "纸尿裤": "奶粉",
            "擦屁屁总有点红": "喝奶状态我会多留意",
            "奶量喝奶反应": "奶量接受度",
            "便便偏稀": "便便状态我会多留意",
            "便便偏软": "便便状态我会多留意",
            "臭臭有点稀": "便便状态我会多留意",
            "截图": "记录",
            "a2码": "a2",
            "罐底码": "物流码",
            "物流码底": "罐底物流码",
            "罐底批次": "物流码批次",
            "底部的码": "物流码",
            "罐上批次": "物流码批次",
            "罐子扫一扫批次": "扫物流码看批次",
            "扫罐": "扫物流码",
            "扫完罐底": "扫完罐底物流码看报告",
            "物流码的码": "物流码",
            "码的码": "码",
            "批次码": "物流码",
            "60+": "60多项",
            "蜡样报告细节": "蜡样检测标准",
            "检测项目": "检测项",
            "重金属报告": "报告细节",
            "继续喂": "继续喝",
            "批批报告": "批批检报告",
            "三方检测报告": "三方检测数据",
            "第三方检测报告": "三方检测数据",
            "三方报告": "三方检测数据",
            "第三方报告": "三方检测数据",
            "对上报文": "对上报告",
            "看说": "看到",
            "不不悬": "踏实些",
            "才敢喂": "再开罐",
            "不悬着了": "踏实不少",
        },
        context_replacements={"蜡毒": "蜡样那项"},
        export_profile="article_pool_5_columns",
    ),
    A2_NEGATIVE_POST_COMMENT_PROFILE_KEY: QualityGuardProfile(
        profile_key=A2_NEGATIVE_POST_COMMENT_PROFILE_KEY,
        label="A2既存负面帖铺评论轻守卫",
        forbidden_terms=A2_NEGATIVE_POST_COMMENT_FORBIDDEN_TERMS,
        context_required_fields=("人设", "关键词", "扰动规则", "生文指令", "业务规则", "生文输出格式"),
        context_keyword_allowlist=A2_NEGATIVE_POST_KEYWORDS,
        keyword_markers={
            "到货安抚": ("到货安抚", *A2_NEGATIVE_POST_ARRIVAL_MARKERS),
            "转奶安抚": ("转奶安抚", *A2_NEGATIVE_POST_TRANSFER_MARKERS),
        },
        default_keyword="到货安抚",
        body_must_include_any_by_keyword={
            "到货安抚": A2_NEGATIVE_POST_ARRIVAL_MARKERS,
            "转奶安抚": A2_NEGATIVE_POST_TRANSFER_MARKERS,
        },
        body_replacements={
            "A2": "a2",
            "三方检测报告": "三方检测数据",
            "第三方检测报告": "三方检测数据",
            "三方报告": "三方检测数据",
            "第三方报告": "三方检测数据",
            "转一罐": "先试一罐",
            "换一罐": "先试一罐",
            "换一小罐": "先试一罐",
            "屯一罐": "囤一罐",
            "先先试一罐试试": "先试一罐",
        },
        export_profile="article_pool_5_columns",
    ),
    A2_SENTIMENT_POST_PROFILE_KEY: QualityGuardProfile(
        profile_key=A2_SENTIMENT_POST_PROFILE_KEY,
        label="A2舆情相关UGC帖子轻守卫",
        forbidden_terms=(
            "愿意喝着",
            "愿意喝上",
            "习惯性",
            "断档",
        ),
        body_replacements={
            "A2": "a2",
            "a2至补货": "a2至初",
            "三方检测报告": "三方检测数据",
            "第三方检测报告": "三方检测数据",
            "三方报告": "三方检测数据",
            "第三方报告": "三方检测数据",
            "屯": "囤",
        },
        export_profile="article_pool_5_columns",
    ),
    A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY: QualityGuardProfile(
        profile_key=A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY,
        label="A2剧情讨论评论专项守卫",
        context_required_fields=("人设", "扰动规则", "生文指令", "业务规则", "生文输出格式"),
        keyword_markers={
            A2_PLOT_DISCUSSION_KEYWORD: (
                "奶宝",
                "找妈妈",
                "山洞",
                "求援",
                "对讲机",
                "门店",
                "活动",
                "补货",
            ),
        },
        default_keyword=A2_PLOT_DISCUSSION_KEYWORD,
        body_must_include_any_by_keyword={
            A2_PLOT_DISCUSSION_KEYWORD: A2_PLOT_DISCUSSION_ACTIVITY_MARKERS,
        },
        body_replacements={
            "稀有A2牛": "稀有A2型奶牛",
            "稀有A2型的": "稀有A2型奶牛",
            "稀有奶牛": "稀有A2型奶牛",
            "A2奶牛": "A2型奶牛",
            "稀有A2奶牛": "稀有A2型奶牛",
            "山洞救援": "山洞求援",
        },
    ),
}


def resolve_quality_guard_profile(profile_key: Any) -> QualityGuardProfile | None:
    normalized = _normalize_key(profile_key)
    if not normalized:
        return None
    return QUALITY_GUARD_PROFILES.get(normalized)


def quality_guard_profile_key_from_asset(asset: Any) -> str | None:
    for source in (getattr(asset, "content_json", None), getattr(asset, "metadata_json", None)):
        if isinstance(source, dict):
            key = _normalize_key(source.get("quality_guard_profile_key") or source.get("quality_guard_profile"))
            if key:
                return key
    return None


def quality_guard_profile_key_from_job(job: Any) -> str | None:
    strategy = getattr(job, "strategy_json", None)
    if isinstance(strategy, dict):
        return _normalize_key(strategy.get("quality_guard_profile_key") or strategy.get("quality_guard_profile"))
    return None


def build_article_pool_context_list(item: Any, profile_key: Any = None) -> dict[str, str]:
    profile = resolve_quality_guard_profile(profile_key or _plan_profile_key(item))
    plan = _dict_value(getattr(item, "plan_json", None))
    selected_keywords = _selected_keywords(plan, _dict_value(getattr(item, "quality_json", None)))
    keyword = _derive_keyword(item, plan, profile)
    context = {
        "人设": _keyword_name(selected_keywords, codes=("persona",), names=("人设",)) or "",
        "关键词": keyword or "",
        "扰动规则": _keyword_name(selected_keywords, codes=("perturbation_rule",), names=("扰动规则",)) or "通用",
        "生文指令": _keyword_name(
            selected_keywords,
            codes=("comment_writing_instruction", "writing_instruction"),
            names=("生文指令", "写作指令"),
        )
        or "评论-短句",
        "业务规则": _derive_business_rule(item, plan, keyword=keyword, profile=profile),
        "生文输出格式": _keyword_name(
            selected_keywords,
            codes=("comment_format_control", "format_control"),
            names=("生文输出格式", "输出格式"),
        )
        or "生文输出格式-评论",
    }
    return {
        key: _sanitize_context_value(str(value or "").strip(), profile)
        for key, value in context.items()
    }


class ActivityQualityGuardService:
    """Apply configured guard profiles to generated items and batches."""

    def review_item(self, item: Any, profile_key: Any = None) -> dict[str, Any] | None:
        profile = resolve_quality_guard_profile(profile_key or _plan_profile_key(item))
        if profile is None:
            return None
        context = build_article_pool_context_list(item, profile.profile_key)
        repairs = self._repair_item_body(item, profile, context)
        title_repairs = self._repair_item_title(item, profile)
        repairs.extend(title_repairs)
        if repairs:
            context = build_article_pool_context_list(item, profile.profile_key)
        issues = self._item_issues(item, profile, context)
        payload = _guard_payload(profile, context=context, issues=issues, repairs=repairs)
        _attach_guard_payload(item, payload)
        return payload

    def review_batch(self, job: Any, items: list[Any]) -> None:
        profile = resolve_quality_guard_profile(quality_guard_profile_key_from_job(job))
        if profile is None:
            return
        generated_items = [
            item
            for item in items
            if getattr(item, "status", None) == "generated" and str(getattr(item, "body", "") or "").strip()
        ]
        for item in generated_items:
            self.review_item(item, profile.profile_key)

    def _item_issues(self, item: Any, profile: QualityGuardProfile, context: dict[str, str]) -> list[dict[str, Any]]:
        body = str(getattr(item, "body", "") or "")
        context_text = json.dumps(context, ensure_ascii=False)
        issues: list[dict[str, Any]] = []
        hits = _profile_forbidden_term_hits(profile, body=body, context_text=context_text)
        if hits:
            issues.append(
                {
                    "code": "activity_forbidden_terms",
                    "message": "命中活动专项禁词",
                    "evidence": hits,
                    "risk_level": "high",
                }
            )
        missing = [field for field in profile.context_required_fields if not str(context.get(field) or "").strip()]
        if missing:
            issues.append(
                {
                    "code": "activity_context_missing_fields",
                    "message": "上下文变量缺少必填字段",
                    "evidence": missing,
                    "risk_level": "high",
                }
            )
        keyword = context.get("关键词")
        if profile.context_keyword_allowlist and keyword not in profile.context_keyword_allowlist:
            issues.append(
                {
                    "code": "activity_context_keyword_out_of_range",
                    "message": "上下文变量关键词超出活动允许范围",
                    "evidence": [keyword],
                    "risk_level": "high",
                }
            )
        required_markers = profile.body_must_include_any_by_keyword.get(keyword or "")
        if required_markers and not any(marker in body for marker in required_markers):
            issues.append(
                {
                    "code": "activity_body_missing_keyword_marker",
                    "message": f"{keyword}方向正文缺少明确标记",
                    "evidence": list(required_markers),
                    "risk_level": "high",
                }
            )
        if profile.profile_key == A2_SENTIMENT_COMMENT_PROFILE_KEY:
            issues.extend(_a2_combo_item_issues(item, body, keyword or ""))
        if profile.profile_key == A2_SENTIMENT_POST_PROFILE_KEY:
            issues.extend(_a2_sentiment_post_item_issues(item, body))
        if profile.profile_key == A2_NEGATIVE_POST_COMMENT_PROFILE_KEY:
            issues.extend(_a2_negative_post_item_issues(body))
        if profile.profile_key == A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY:
            issues.extend(_a2_plot_discussion_item_issues(body))
        return issues

    def _repair_item_body(
        self,
        item: Any,
        profile: QualityGuardProfile,
        context: dict[str, str],
    ) -> list[dict[str, Any]]:
        body = str(getattr(item, "body", "") or "")
        if not body:
            return []
        repaired = body
        repairs: list[dict[str, Any]] = []
        for source, replacement in profile.body_replacements.items():
            if source and source in repaired:
                repaired = repaired.replace(source, replacement)
                repairs.append(
                    {
                        "code": "activity_body_replacement",
                        "source": source,
                        "replacement": replacement,
                    }
                )
        if profile.profile_key == A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY:
            # 只修“稀有A2牛/是A2牛”这类省略说法，不吞掉应拦截的“A2牛牛”。
            a2_cow_repaired = re.sub(r"A2牛(?!牛)", "A2型奶牛", repaired)
            if a2_cow_repaired != repaired:
                repaired = a2_cow_repaired
                repairs.append(
                    {
                        "code": "activity_body_replacement",
                        "source": "A2牛",
                        "replacement": "A2型奶牛",
                    }
                )
        if profile.profile_key == A2_SENTIMENT_COMMENT_PROFILE_KEY:
            # A2 的 0.03 必须回到“报告里的蜡样检测那项”，避免模型把数值写成竞品归因或悬空卖点。
            a2_repaired = _repair_a2_003_reference(repaired)
            if a2_repaired != repaired:
                repaired = a2_repaired
                repairs.append({"code": "activity_body_a2_003_reference_repaired"})
        collapsed = _collapse_repeated_activity_terms(repaired)
        if collapsed != repaired:
            repaired = collapsed
            repairs.append({"code": "activity_body_duplicate_term_collapsed"})
        keyword = context.get("关键词")
        required_markers = profile.body_must_include_any_by_keyword.get(keyword or "")
        if required_markers and not any(marker in repaired for marker in required_markers):
            marker_repaired = _insert_required_keyword_marker(repaired, keyword or "")
            if marker_repaired != repaired:
                repaired = marker_repaired
                repairs.append(
                    {
                        "code": "activity_body_keyword_marker_inserted",
                        "keyword": keyword,
                        "markers": list(required_markers),
                    }
                )
        if repaired != body:
            # 只有评论链路需要把守卫修复后的正文收口；帖子链路正文不做长度裁剪。
            if profile.profile_key in A2_COMMENT_PROFILE_KEYS:
                item.body = _trim_activity_comment(repaired)
            else:
                item.body = repaired.strip()
        return repairs

    def _repair_item_title(self, item: Any, profile: QualityGuardProfile) -> list[dict[str, Any]]:
        title = str(getattr(item, "title", "") or "")
        if not title:
            return []
        repaired = title
        repairs: list[dict[str, Any]] = []
        for source, replacement in profile.body_replacements.items():
            if source != "A2":
                continue
            if source and source in repaired:
                repaired = repaired.replace(source, replacement)
                repairs.append(
                    {
                        "code": "activity_title_replacement",
                        "source": source,
                        "replacement": replacement,
                    }
                )
        if repaired != title:
            item.title = repaired.strip()
        return repairs

def _guard_payload(
    profile: QualityGuardProfile,
    *,
    context: dict[str, str],
    issues: list[dict[str, Any]],
    repairs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "source": "activity_quality_guard",
        "profile_key": profile.profile_key,
        "profile_label": profile.label,
        "export_profile": profile.export_profile,
        "pass": not issues,
        "context_list": context,
        "issues": issues,
        "repairs": repairs or [],
    }


def _attach_guard_payload(item: Any, payload: dict[str, Any]) -> None:
    quality = dict(getattr(item, "quality_json", None) or {})
    quality["activity_quality_guard"] = payload
    _sync_guard_to_review_report(quality, payload)
    item.quality_json = quality


def _sync_guard_to_review_report(quality: dict[str, Any], payload: dict[str, Any]) -> None:
    review_report = dict(quality.get("review_report") or {})
    hard_results = [
        dict(result)
        for result in review_report.get("hard_results") or []
        if isinstance(result, dict) and not str(result.get("ae_code") or "").startswith("activity_quality_guard")
    ]
    for issue in payload.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        hard_results.append(
            {
                "ae_code": f"activity_quality_guard.{issue.get('code') or 'issue'}",
                "pass": False,
                "risk_level": issue.get("risk_level") or "high",
                "feedback": issue.get("message") or "活动专项质量守卫未通过",
                "evidence": issue.get("evidence") or [],
            }
        )
    review_report["hard_results"] = hard_results
    if payload.get("issues"):
        review_report["rewrite_required"] = True
        review_report["rewrite_reason"] = "活动专项质量守卫未通过"
    quality["review_report"] = review_report
    guard_pass = bool(payload.get("pass"))
    existing_hard_pass = quality.get("hard_pass")
    quality["hard_pass"] = guard_pass if existing_hard_pass is None else bool(existing_hard_pass and guard_pass)


def _derive_keyword(item: Any, plan: dict[str, Any], profile: QualityGuardProfile | None) -> str:
    if profile is None:
        return _keyword_name(_selected_keywords(plan, _dict_value(getattr(item, "quality_json", None))), names=("关键词",)) or ""
    source = "\n".join(
        str(value or "")
        for value in (
            getattr(item, "title", None),
            getattr(item, "body", None),
            _plan_business_rule(plan),
            plan.get("corpus"),
            " ".join(str(example) for example in plan.get("examples") or []),
        )
    )
    return derive_profile_keyword_from_text(source, profile)


def derive_profile_keyword_from_text(text: str, profile: QualityGuardProfile) -> str:
    """Resolve activity keywords from rule/comment text, including A2 combo keywords."""
    source = str(text or "")
    if profile.profile_key == A2_SENTIMENT_COMMENT_PROFILE_KEY:
        return _derive_a2_combo_keyword(source, profile)
    if profile.profile_key == A2_NEGATIVE_POST_COMMENT_PROFILE_KEY:
        return _derive_a2_negative_post_keyword(source, profile)
    for keyword, markers in profile.keyword_markers.items():
        if any(marker and marker in source for marker in markers):
            return keyword
    return profile.default_keyword or ""


def _derive_business_rule(item: Any, plan: dict[str, Any], *, keyword: str, profile: QualityGuardProfile | None) -> str:
    base = str(_plan_business_rule(plan) or getattr(item, "title", "") or "").strip()
    heading = _corpus_heading(plan.get("corpus"))
    if profile and profile.profile_key == A2_SENTIMENT_COMMENT_PROFILE_KEY and base and heading:
        return f"{base}，{keyword}-{heading}" if keyword else f"{base}，{heading}"
    return base or heading


def _plan_business_rule(plan: dict[str, Any]) -> Any:
    value = plan.get("business_rule")
    if value is None:
        value = plan.get("comment_" + "angle")
    return value


def _corpus_heading(corpus: Any) -> str:
    for raw_line in str(corpus or "").splitlines():
        line = raw_line.strip().strip("#").strip()
        if not line:
            continue
        line = re.sub(r"[:：]\s*$", "", line)
        if line and not line.startswith("像") and not line.startswith("示例") and not line.startswith("注意"):
            return line
    return ""


def _selected_keywords(plan: dict[str, Any], quality: dict[str, Any]) -> list[dict[str, Any]]:
    unified = plan.get("unified_generation") if isinstance(plan.get("unified_generation"), dict) else {}
    candidates = unified.get("selected_keywords") or quality.get("selected_keywords") or []
    return [item for item in candidates if isinstance(item, dict)]


def _keyword_name(
    selected_keywords: list[dict[str, Any]],
    *,
    codes: tuple[str, ...] = (),
    names: tuple[str, ...] = (),
) -> str | None:
    normalized_codes = {value.lower() for value in codes}
    normalized_names = set(names)
    for item in selected_keywords:
        code = str(item.get("category_code") or "").lower()
        name = str(item.get("category_name") or "")
        if (normalized_codes and code in normalized_codes) or (normalized_names and name in normalized_names):
            value = str(item.get("keyword_name") or item.get("keyword_code") or "").strip()
            if value:
                return value
    return None


def _sanitize_context_value(value: str, profile: QualityGuardProfile | None) -> str:
    if profile is None:
        return value
    sanitized = value
    for source, replacement in profile.context_replacements.items():
        sanitized = sanitized.replace(source, replacement)
    return sanitized


def _insert_required_keyword_marker(body: str, keyword: str) -> str:
    text = str(body or "").strip()
    if not text or "有货" not in keyword:
        return text
    replacements = (
        ("新补的这罐", "补货拿的这罐"),
        ("新补的", "补货拿的"),
        ("按需补", "按需补货"),
        ("买前", "补货前"),
    )
    for source, replacement in replacements:
        if source in text:
            return text.replace(source, replacement, 1)
    if "门店" in text:
        return re.sub(r"^.*?门店", "补货时问门店", text, count=1)
    return f"有货了，{text}"


def _trim_activity_comment(text: str, max_chars: int = 60) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    truncated = value[:max_chars].rstrip("，。！？、；; ")
    return truncated or value[:max_chars]


def _collapse_repeated_activity_terms(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"扫物流码底(?:物流码|码)?", "扫罐底物流码", value)
    value = re.sub(r"物流码底(?:物流码|码)?", "罐底物流码", value)
    value = re.sub(r"物流码码", "物流码", value)
    value = re.sub(r"物流码(?:那个|这个)码", "物流码", value)
    value = re.sub(r"物流码(?:那个|这个|这边|这里)?物流码", "物流码", value)
    for term in ("物流码", "批次报告", "检测报告", "蜡样检测", "报告里那项"):
        value = re.sub(f"(?:{re.escape(term)}){{2,}}", term, value)
    return value


def _repair_a2_003_reference(text: str) -> str:
    value = str(text or "")
    competitor = r"(爱他美|达能|美素|皇家美素|皇美|雀巢|超启能恩)"
    value = re.sub(r"(?<!<)(?<!小于)0\.03这点", "蜡样检测0.03这点", value)
    value = re.sub(r"(?<!<)(?<!小于)0\.03这个细节", "蜡样检测0.03这个细节", value)
    value = re.sub(r"(?<!<)(?<!小于)0\.03这个数值", "蜡样检测0.03这个数值", value)
    value = re.sub(r"(?<!<)(?<!小于)0\.03这条线", "报告里那项0.03", value)
    value = re.sub(rf"(?:拿|把){competitor}也看，", r"\1也看，", value)
    value = re.sub(
        rf"{competitor}(?:和|跟)a2的(?:蜡样检测)?(?:报告里那项)?0\.03(?:报告)?",
        r"\1也看，a2报告里那项0.03",
        value,
    )
    value = re.sub(
        rf"{competitor}[^，。！？；;]{{0,12}}报告里那项0\.03",
        r"\1也看，a2报告里那项0.03",
        value,
    )
    value = re.sub(
        rf"(?:拿|把){competitor}和(?:蜡样检测)?0\.03(?:一起)?(?:对比|比|看)?",
        r"\1也看，a2报告里那项0.03",
        value,
    )
    value = re.sub(
        rf"{competitor}(?:那边|这边|这里)(?:蜡样检测)?0\.03(?:这个数值)?",
        r"\1也看，a2报告里那项0.03",
        value,
    )
    value = re.sub(
        rf"{competitor}和(?:蜡样检测)?0\.03(?:一起)?(?:对比|比|看)?",
        r"\1也看，a2报告里那项0.03",
        value,
    )
    value = re.sub(
        r"(a2报告里那项0\.03)(?:一起)?(?:对比|比)(肚肚|便便|奶量|适应|喝奶|反应)",
        r"\1，再看\2",
        value,
    )
    value = re.sub(
        rf"(还会|会|想|先){competitor}也看，",
        r"\1看\2，也看",
        value,
    )
    if "0.03" in value and not A2_003_CONTEXT_PATTERN.search(value):
        value = re.sub(r"(?<!<)(?<!小于)0\.03", "报告里那项0.03", value, count=1)
    value = value.replace("爱他美也看，a2报告里那项0.03", "爱他美样批也看，a2报告里那项0.03")
    return value


def _derive_a2_combo_keyword(source: str, profile: QualityGuardProfile) -> str:
    for keyword, markers in A2_DIRECT_KEYWORD_MARKERS.items():
        if any(marker in source for marker in markers):
            return keyword
    has_yohuo = _has_any_marker(source, A2_DIRECTION_MARKER_GROUPS["有货+批批检"]["有货信息"])
    has_batch = _has_any_marker(source, A2_DIRECTION_MARKER_GROUPS["有货+批批检"]["批批检信息"])
    has_transfer = _has_any_marker(source, A2_DIRECTION_MARKER_GROUPS["批批检+转奶"]["转奶动作"])
    if has_yohuo and has_batch:
        return "有货+批批检"
    if has_batch and has_transfer:
        return "批批检+转奶"
    if has_yohuo and has_transfer:
        return "有货+转奶"
    return profile.default_keyword or ""


def _derive_a2_negative_post_keyword(source: str, profile: QualityGuardProfile) -> str:
    for keyword in A2_NEGATIVE_POST_KEYWORDS:
        if keyword in source:
            return keyword
    for keyword, markers in profile.keyword_markers.items():
        if any(marker and marker in source for marker in markers):
            return keyword
    return profile.default_keyword or ""


def _a2_plot_discussion_item_issues(body: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    body_chars = len(str(body or "").strip())
    if body_chars < A2_PLOT_DISCUSSION_MIN_CHARS or body_chars > A2_PLOT_DISCUSSION_MAX_CHARS:
        issues.append(
            {
                "code": "activity_body_length_out_of_range",
                "message": "剧情讨论评论字数需控制在21到50字",
                "evidence": [f"{body_chars}字"],
                "risk_level": "high",
            }
        )
    if not _has_any_marker(body, A2_PLOT_DISCUSSION_PLOT_MARKERS):
        issues.append(
            {
                "code": "activity_body_missing_plot_anchor",
                "message": "剧情讨论评论缺少明确剧情锚点",
                "evidence": ["奶宝/找妈妈/山洞求援/艾尔博士/A2型奶牛"],
                "risk_level": "high",
            }
        )
    if not _has_any_marker(body, A2_PLOT_DISCUSSION_ACTIVITY_MARKERS):
        issues.append(
            {
                "code": "activity_body_missing_store_activity",
                "message": "剧情讨论评论缺少门店活动或补货引流",
                "evidence": ["门店/母婴店/店里/活动/补货/续上/对讲机"],
                "risk_level": "high",
            }
        )
    if A2_PLOT_DISCUSSION_CHILD_ACTIVITY_PATTERN.search(body) or A2_PLOT_DISCUSSION_CHILD_STORE_DESIRE_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_child_knows_store_gift",
                "message": "不要写成孩子知道或主动要门店活动赠品",
                "evidence": ["孩子知道门店活动/对讲机赠品"],
                "risk_level": "high",
            }
        )
    odd_play_hits = [term for term in A2_PLOT_DISCUSSION_ODD_PLAY_PHRASES if term in body]
    if odd_play_hits:
        issues.append(
            {
                "code": "activity_body_odd_drinking_play_phrase",
                "message": "不要把喝奶粉和玩剧情硬粘成“喝着演”这类怪表达",
                "evidence": odd_play_hits,
                "risk_level": "high",
            }
        )
    invalid_wording_hits = [term for term in A2_PLOT_DISCUSSION_INVALID_WORDING_TERMS if term in body]
    if invalid_wording_hits:
        issues.append(
            {
                "code": "activity_body_invalid_plot_wording",
                "message": "剧情讨论里的A2身份、走散对象或童言表述不自然",
                "evidence": invalid_wording_hits,
                "risk_level": "high",
            }
        )
    unsupported_plot_hits = [term for term in A2_PLOT_DISCUSSION_UNSUPPORTED_PLOT_TERMS if term in body]
    if unsupported_plot_hits:
        issues.append(
            {
                "code": "activity_body_unsupported_plot_detail",
                "message": "剧情讨论不要编出未给到的动画剧情细节",
                "evidence": unsupported_plot_hits,
                "risk_level": "high",
            }
        )
    activity_misstatement_hits = [term for term in A2_PLOT_DISCUSSION_ACTIVITY_MISSTATEMENT_TERMS if term in body]
    if activity_misstatement_hits:
        issues.append(
            {
                "code": "activity_body_activity_misstatement",
                "message": "门店活动表达不要写偏成超市、小礼品或错误购买门槛",
                "evidence": activity_misstatement_hits,
                "risk_level": "high",
            }
        )
    return issues


def _a2_negative_post_item_issues(body: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if A2_NEGATIVE_POST_NOTE_LIKE_DAILY_PURCHASE_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_note_like_daily_purchase",
                "message": "正文像生活笔记流水账，不像评论区接话",
                "evidence": [A2_NEGATIVE_POST_NOTE_LIKE_DAILY_PURCHASE_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    if A2_NEGATIVE_POST_BAD_BATCH_CHECK_ATTRIBUTION_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_bad_batch_check_attribution",
                "message": "批批检是每批检测/报告，不要写成姐妹或人群属性",
                "evidence": [A2_NEGATIVE_POST_BAD_BATCH_CHECK_ATTRIBUTION_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    return issues


def _a2_combo_item_issues(item: Any, body: str, keyword: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    product_split_hit = _a2_zhichu_product_split_hit(body)
    if product_split_hit:
        issues.append(
            {
                "code": "activity_body_bad_a2_zhichu_product_split",
                "message": "a2至初是一个产品名，不能写成“至初这边有a2现货”这类拆分表达",
                "evidence": [product_split_hit],
                "risk_level": "high",
            }
        )
    stock_overclaim_hit = _a2_stock_overclaim_hit(body)
    if stock_overclaim_hit:
        issues.append(
            {
                "code": "activity_body_bad_stock_claim",
                "message": "库存消息不要写成官方公告、全国补货或保证买到这类确定性表达",
                "evidence": [stock_overclaim_hit],
                "risk_level": "high",
            }
        )
    supply_trend_claim_hit = _a2_supply_trend_claim_hit(body)
    if supply_trend_claim_hit:
        issues.append(
            {
                "code": "activity_body_supply_trend_claim",
                "message": "有货评论只讲个人买到/问到事实，不判断货源趋势、陆续到货、回货或放货",
                "evidence": [supply_trend_claim_hit],
                "risk_level": "high",
            }
        )
    bad_stock_wording_hit = _a2_brand_bad_stock_wording_hit(body)
    if bad_stock_wording_hit:
        issues.append(
            {
                "code": "activity_body_brand_bad_stock_wording",
                "message": "品牌反馈不建议这类库存/渠道承诺话术，改成我刚买到、我刚问到、直接下单了等个人事实",
                "evidence": [bad_stock_wording_hit],
                "risk_level": "high",
            }
        )
    transfer_tutorial_hit = _a2_transfer_tutorial_hit(body)
    if transfer_tutorial_hit:
        issues.append(
            {
                "code": "activity_body_transfer_tutorial",
                "message": "评论不要写具体转奶教程、勺量比例或适应承诺",
                "evidence": [transfer_tutorial_hit],
                "risk_level": "high",
            }
        )
    bad_transfer_framing_hit = _a2_brand_bad_transfer_framing_hit(body)
    if bad_transfer_framing_hit:
        issues.append(
            {
                "code": "activity_body_brand_bad_transfer_framing",
                "message": "有货+转奶评论不要写本来想换、转奶很乱、打消念头或回到至初这类负面转奶框架",
                "evidence": [bad_transfer_framing_hit],
                "risk_level": "high",
            }
        )
    ai_template_question_hit = _a2_ai_template_conditional_question_hit(body)
    if ai_template_question_hit:
        issues.append(
            {
                "code": "activity_body_ai_template_conditional_question",
                "message": "评论不要写成“能买到a2的话，是不是先继续原来的就行”这类条件式模板问句",
                "evidence": [ai_template_question_hit],
                "risk_level": "high",
            }
        )
    product_effect_hit = _a2_product_effect_claim_hit(body)
    if product_effect_hit:
        issues.append(
            {
                "code": "activity_body_product_effect_claim",
                "message": "不要把a2/a2至初写成解决便便、肚肚、奶量或长肉问题的确定原因",
                "evidence": [product_effect_hit],
                "risk_level": "high",
            }
        )
    report_overclaim_hit = _a2_report_overclaim_hit(body)
    if report_overclaim_hit:
        issues.append(
            {
                "code": "activity_body_report_overclaim",
                "message": "报告只能作为可查看信息点，不能写成安全证明或保证没问题",
                "evidence": [report_overclaim_hit],
                "risk_level": "high",
            }
        )
    scan_before_can_hit = _a2_scan_before_can_in_hand_hit(body)
    if scan_before_can_hit:
        issues.append(
            {
                "code": "activity_body_scan_before_can_in_hand",
                "message": "罐底物流码应是到手/拿到后扫，不写成下单后就能扫",
                "evidence": [scan_before_can_hit],
                "risk_level": "high",
            }
        )
    supply_pressure_transfer_hit = _a2_supply_pressure_transfer_hit(body)
    if supply_pressure_transfer_hit:
        issues.append(
            {
                "code": "activity_body_supply_pressure_transfer_memory",
                "message": "有货/转奶评论不要回忆货少、买不到或被动换奶这类过往供应压力",
                "evidence": [supply_pressure_transfer_hit],
                "risk_level": "high",
            }
        )
    feeding_anxiety_stock_hit = _a2_feeding_anxiety_stock_hit(body)
    if feeding_anxiety_stock_hit:
        issues.append(
            {
                "code": "activity_body_feeding_anxiety_stock",
                "message": "家庭库存可以写快空/见底，不要写成断顿、没奶喝或接不上这类喂养焦虑",
                "evidence": [feeding_anxiety_stock_hit],
                "risk_level": "high",
            }
        )
    if keyword in A2_BATCH_REPORT_REQUIRED_KEYWORDS:
        if (
            not _has_any_marker(body, A2_BATCH_REPORT_MARKERS)
            and not _a2_has_wax_standard_advantage_for_rule(item, body)
            and not _a2_has_third_party_data_advantage_for_rule(item, body)
            and not _a2_has_contextual_batch_detection_advantage(body)
        ):
            issues.append(
                {
                    "code": "activity_body_missing_combo_marker",
                    "message": f"{keyword}方向正文缺少批次/报告/物流码信息",
                    "evidence": ["批次/报告/物流码"],
                    "risk_level": "high",
                }
            )
    if (
        keyword in A2_BATCH_REPORT_REQUIRED_KEYWORDS
        or (keyword == "有货+转奶" and _has_any_marker(body, A2_BATCH_REPORT_MARKERS))
    ):
        if (
            not _a2_has_specific_advantage(body)
            and not _a2_has_wax_standard_advantage_for_rule(item, body)
            and not _a2_has_third_party_data_advantage_for_rule(item, body)
            and not _a2_has_contextual_batch_detection_advantage(body)
        ):
            issues.append(
                {
                    "code": "activity_body_missing_a2_specific_advantage",
                    "message": "正文只做泛泛对比，没有讲清a2的批次报告/物流码/每批检测优势",
                    "evidence": ["a2具体优势"],
                    "risk_level": "high",
                }
            )
    if keyword in A2_COMBO_KEYWORDS and "0.03" in body and not A2_003_CONTEXT_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_unclear_003_context",
                "message": "0.03需要说清楚是蜡样/蜡毒检测相关数值",
                "evidence": ["0.03"],
                "risk_level": "high",
            }
        )
    out_of_scope_competitors = [term for term in A2_OUT_OF_SCOPE_COMPETITOR_TERMS if term in body]
    if out_of_scope_competitors:
        issues.append(
            {
                "code": "activity_body_out_of_scope_competitor",
                "message": "正文出现不在本活动竞品组内的品牌名",
                "evidence": out_of_scope_competitors,
                "risk_level": "high",
            }
        )
    if A2_UNCONFIRMED_COMPETITOR_VALUE_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_unconfirmed_competitor_value",
                "message": "雀巢/超启能恩只露出竞品名，不归因0.03数值",
                "evidence": [A2_UNCONFIRMED_COMPETITOR_VALUE_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    if A2_AMBIGUOUS_COMPETITOR_003_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_ambiguous_competitor_003",
                "message": "0.03不能和竞品直接并列，需要落到a2报告里的蜡样检测那项",
                "evidence": [A2_AMBIGUOUS_COMPETITOR_003_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    if A2_BAD_003_PAIN_POINT_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_bad_003_pain_point_comparison",
                "message": "0.03不能和肚肚、便便、奶量反应直接对比",
                "evidence": [A2_BAD_003_PAIN_POINT_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    if A2_BAD_003_COMPETITOR_COMPARISON_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_bad_003_competitor_comparison",
                "message": "0.03不要写成和竞品数值直接比细的硬口径",
                "evidence": [A2_BAD_003_COMPETITOR_COMPARISON_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    # 竞品只做轻对比和用户功课铺垫；雀巢组可写每批检，样批只给已确认的达能组/皇家美素组。
    if _a2_has_unconfirmed_competitor_batch_claim(body):
        issues.append(
            {
                "code": "activity_body_unconfirmed_competitor_batch_report",
                "message": "爱他美/达能/皇家美素/皇美不写每批检口径；雀巢组和a2可以写每批检",
                "evidence": [A2_UNCONFIRMED_COMPETITOR_BATCH_REPORT_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    if A2_UNCONFIRMED_COMPETITOR_SAMPLE_BATCH_PATTERN.search(body):
        issues.append(
            {
                "code": "activity_body_unconfirmed_competitor_sample_batch",
                "message": "样批口径只用于爱他美/达能组和美素/皇家美素/皇美，雀巢组不要扩写样批",
                "evidence": [A2_UNCONFIRMED_COMPETITOR_SAMPLE_BATCH_PATTERN.pattern],
                "risk_level": "high",
            }
        )
    if (
        "爱他美" in body
        and A2_VAGUE_APTAMIL_COMPARISON_PATTERN.search(body)
        and not _a2_has_precise_aptamil_comparison(body)
        and not _a2_has_specific_advantage(body)
    ):
        issues.append(
            {
                "code": "activity_body_vague_aptamil_comparison",
                "message": "爱他美对比需要落到样批/平台公开 vs a2每批检/罐底扫码，不能只泛泛说看过或问过",
                "evidence": ["爱他美样批/平台公开/a2每批检/罐底扫码"],
                "risk_level": "high",
            }
        )
    lab_hits = [term for term in A2_LAB_NOTATION_TERMS if term in body]
    if lab_hits:
        issues.append(
            {
                "code": "activity_body_lab_notation",
                "message": "正文不应出现实验室单位或符号，0.03需口语化表达",
                "evidence": lab_hits,
                "risk_level": "high",
            }
        )
    incomplete_reason = _a2_incomplete_comment_reason(body)
    if incomplete_reason:
        issues.append(
            {
                "code": "activity_body_incomplete_comment",
                "message": "正文像被截断的残句",
                "evidence": [incomplete_reason],
                "risk_level": "high",
            }
        )
    vague_deictic_reason = _a2_vague_deictic_without_product_reason(body)
    if vague_deictic_reason:
        issues.append(
            {
                "code": "activity_body_vague_deictic_without_product",
                "message": "正文只说这罐/刚收到但没有a2或评论区接话对象，像孤立残句",
                "evidence": [vague_deictic_reason],
                "risk_level": "high",
            }
        )
    if body.count("蜡毒") > 1:
        issues.append(
            {
                "code": "activity_body_wax_term_overexposed",
                "message": "单条正文里蜡毒最多出现一次",
                "evidence": ["蜡毒"],
                "risk_level": "high",
            }
        )
    return issues


def _a2_zhichu_product_split_hit(body: str) -> str | None:
    match = A2_ZHICHU_PRODUCT_SPLIT_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_stock_overclaim_hit(body: str) -> str | None:
    match = A2_STOCK_OVERCLAIM_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_supply_trend_claim_hit(body: str) -> str | None:
    text = str(body or "")
    if A2_PERSONAL_SUPPLY_TREND_CONTEXT_PATTERN.search(text):
        return None
    match = A2_SUPPLY_TREND_CLAIM_PATTERN.search(text)
    return match.group(0) if match else None


def _a2_brand_bad_stock_wording_hit(body: str) -> str | None:
    match = A2_BRAND_BAD_STOCK_WORDING_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_transfer_tutorial_hit(body: str) -> str | None:
    match = A2_TRANSFER_TUTORIAL_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_brand_bad_transfer_framing_hit(body: str) -> str | None:
    match = A2_BRAND_BAD_TRANSFER_FRAMING_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_ai_template_conditional_question_hit(body: str) -> str | None:
    match = A2_AI_TEMPLATE_CONDITIONAL_QUESTION_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_product_effect_claim_hit(body: str) -> str | None:
    match = A2_PRODUCT_EFFECT_CLAIM_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_report_overclaim_hit(body: str) -> str | None:
    match = A2_REPORT_OVERCLAIM_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_scan_before_can_in_hand_hit(body: str) -> str | None:
    match = A2_SCAN_BEFORE_CAN_IN_HAND_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_supply_pressure_transfer_hit(body: str) -> str | None:
    text = str(body or "")
    for match in A2_SUPPLY_PRESSURE_TRANSFER_PATTERN.finditer(text):
        hit = match.group(0)
        prefix = text[max(0, match.start() - 8) : match.start()]
        window = f"{prefix}{hit}"
        if "没货" in hit and any(marker in window for marker in A2_HOUSEHOLD_STOCK_MARKERS):
            continue
        return hit
    return None


def _a2_feeding_anxiety_stock_hit(body: str) -> str | None:
    match = A2_FEEDING_ANXIETY_STOCK_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_incomplete_comment_reason(body: str) -> str | None:
    raw_text = str(body or "").strip()
    if raw_text.endswith(("，", ",", "、", "；", ";")):
        return "结尾标点像残句"
    text = raw_text.strip("，。！？,!?；;、 ")
    if not text:
        return "空正文"
    if len(text) < 12 and not _a2_is_complete_supply_transfer_comment(text):
        return "正文过短"
    for suffix in A2_INCOMPLETE_COMMENT_SUFFIXES:
        if text.endswith(suffix):
            if suffix in {"a2", "A2"} and _a2_is_complete_supply_transfer_comment(text):
                continue
            return f"结尾残句：{suffix}"
    return None


def _a2_vague_deictic_without_product_reason(body: str) -> str | None:
    text = str(body or "").strip()
    if any(marker in text for marker in ("a2", "A2", "至初")):
        return None
    if any(marker in text for marker in ("姐妹", "哪买", "哪里买", "哪家", "求问", "+1", "我也")):
        return None
    if "这罐" in text and any(marker in text for marker in ("刚收", "收到", "喝完", "补上", "拿了")):
        return "缺少产品对象"
    return None


def _a2_is_complete_supply_transfer_comment(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    has_product = any(marker in normalized for marker in ("a2", "A2", "至初"))
    has_supply = any(
        marker in normalized
        for marker in (
            "能买到",
            "买到",
            "想买",
            "接着买",
            "先买",
            "我也买",
            "我就买",
            "先拍",
            "我就先拍",
            "刚下单",
            "下单",
            "订到",
            "预定",
            "到了",
            "有货",
            "到货",
            "现货",
            "能补",
            "补到",
            "能拿",
            "能调",
            "可下单",
        )
    )
    has_transfer_decision = any(
        marker in normalized
        for marker in (
            "先不转",
            "不转了",
            "先不换",
            "不换了",
            "继续喝",
            "接着喝",
            "接着买",
            "先买",
            "先拍",
            "先拿",
            "先下单",
            "先订",
            "喝原来的",
            "按原来的",
        )
    )
    has_question_or_thread_tone = any(marker in normalized for marker in ("哪家店", "哪里买", "哪买", "求问", "姐妹"))
    return has_product and has_supply and (has_transfer_decision or has_question_or_thread_tone)


def _a2_sentiment_post_item_issues(item: Any, body: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    title = str(getattr(item, "title", "") or "")
    json_leak_hit = _a2_post_json_leak_hit(title, body)
    if json_leak_hit:
        issues.append(
            {
                "code": "activity_output_json_leak",
                "message": "A2帖子生成结果不能把JSON字段或括号漏进标题/正文",
                "evidence": [json_leak_hit],
                "risk_level": "high",
            }
        )
    ai_title_hit = _a2_post_ai_title_hit(title)
    if ai_title_hit:
        issues.append(
            {
                "code": "activity_title_ai_advice_tone",
                "message": "A2帖子标题不要写成安抚建议、攻略指南或一句话解决问题的AI口吻",
                "evidence": [ai_title_hit],
                "risk_level": "high",
            }
        )
    transfer_decision_hit = _a2_post_transfer_decision_hit(title, body)
    if transfer_decision_hit:
        issues.append(
            {
                "code": "activity_body_transfer_decision_advice",
                "message": "A2帖子可以写个人慢慢转，但不要向姐妹求该不该转、适不适合转这类决策建议",
                "evidence": [transfer_decision_hit],
                "risk_level": "high",
            }
        )
    report_safety_hit = _a2_post_report_safety_decision_hit(body)
    if report_safety_hit:
        issues.append(
            {
                "code": "activity_body_report_safety_decision",
                "message": "报告只能写能查到和看不太懂，不要让姐妹判断没问题、安全或放心喝",
                "evidence": [report_safety_hit],
                "risk_level": "high",
            }
        )
    feeding_decision_hit = _a2_post_feeding_decision_hit(body)
    if feeding_decision_hit:
        issues.append(
            {
                "code": "activity_body_feeding_decision_advice",
                "message": "A2帖子不要让姐妹判断能不能给宝宝喝、该不该喝这款这类喂养决策",
                "evidence": [feeding_decision_hit],
                "risk_level": "high",
            }
        )
    incomplete_reason = _a2_incomplete_post_reason(body)
    if incomplete_reason:
        issues.append(
            {
                "code": "activity_body_incomplete_post",
                "message": "正文像被截断的残句",
                "evidence": [incomplete_reason],
                "risk_level": "high",
            }
        )
    return issues


def _a2_post_ai_title_hit(title: str) -> str | None:
    text = str(title or "").strip()
    match = A2_POST_AI_TITLE_PATTERN.search(text)
    return match.group(0) if match else None


def _a2_post_json_leak_hit(title: str, body: str) -> str | None:
    text = f"{str(title or '').strip()}\n{str(body or '').strip()}"
    match = A2_POST_JSON_LEAK_PATTERN.search(text)
    return match.group(0) if match else None


def _a2_post_transfer_decision_hit(title: str, body: str) -> str | None:
    text = f"{str(title or '').strip()}\n{str(body or '').strip()}"
    match = A2_POST_TRANSFER_DECISION_PATTERN.search(text)
    return match.group(0) if match else None


def _a2_post_report_safety_decision_hit(body: str) -> str | None:
    text = str(body or "")
    match = A2_POST_REPORT_SAFETY_DECISION_PATTERN.search(text)
    if match:
        return match.group(0)
    if any(marker in text for marker in A2_POST_REPORT_MARKERS):
        for term in A2_POST_REPORT_SAFETY_DECISION_TERMS:
            if term in text:
                return term
    return None


def _a2_post_feeding_decision_hit(body: str) -> str | None:
    match = A2_POST_FEEDING_DECISION_PATTERN.search(str(body or ""))
    return match.group(0) if match else None


def _a2_incomplete_post_reason(body: str) -> str | None:
    text = str(body or "").strip()
    if text.endswith(("，", ",", "、", "；", ";")):
        return "结尾标点像残句"
    if not text:
        return "空正文"
    if len(text.strip("。！？!? ")) < 20:
        return "正文过短"
    if text.strip("。！？!? ").endswith(("每条细", "逐条细", "来说", "而言", "感觉", "觉得", "其")):
        return "结尾残句：逐条细看"
    return None


def _a2_competitor_group_hits(text: str) -> list[str]:
    hits: list[str] = []
    for group_name, terms in A2_COMPETITOR_GROUPS.items():
        if any(term in text for term in terms):
            hits.append(group_name)
    return hits


def _a2_rule_requires_competitor_group(item: Any) -> bool:
    plan = _dict_value(getattr(item, "plan_json", None))
    heading = _corpus_heading(plan.get("corpus"))
    source = "\n".join(
        str(value or "")
        for value in (
            getattr(item, "title", None),
            _plan_business_rule(plan),
            heading,
        )
    )
    if "竞品" in source:
        return True
    return any(term in source for terms in A2_COMPETITOR_GROUPS.values() for term in terms)


def _has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker and marker in text for marker in markers)


def _profile_forbidden_term_hits(profile: QualityGuardProfile, *, body: str, context_text: str) -> list[str]:
    hits: list[str] = []
    for term in profile.forbidden_terms:
        if not term:
            continue
        if profile.profile_key in {A2_SENTIMENT_COMMENT_PROFILE_KEY, A2_NEGATIVE_POST_COMMENT_PROFILE_KEY} and term in {
            "急",
            "慌",
        }:
            # “急/慌”本身偏负面，硬拦；“不着急/别慌”这类安抚转折不误伤。
            if _a2_has_forbidden_negative_term(body, term) or (
                profile.profile_key == A2_SENTIMENT_COMMENT_PROFILE_KEY
                and _a2_has_forbidden_negative_term(context_text, term)
            ):
                hits.append(term)
            continue
        if profile.profile_key == A2_NEGATIVE_POST_COMMENT_PROFILE_KEY:
            if term in body:
                hits.append(term)
            continue
        if term in body or term in context_text:
            hits.append(term)
    return hits


def _a2_has_forbidden_negative_term(text: str, term: str) -> bool:
    value = text or ""
    for match in re.finditer(re.escape(term), value):
        start = match.start()
        if start > 0 and value[start - 1] == "不":
            continue
        if start > 0 and value[start - 1] == "别":
            continue
        if term == "急":
            prefix = value[max(0, start - 5) : start]
            if any(marker in prefix for marker in ("不", "别", "不能", "不用", "不要")):
                continue
        if term == "急" and start >= 2 and value[start - 2 : start] in {"别着", "不着"}:
            continue
        if term == "急" and start >= 2 and value[start - 2 : start] == "不着":
            continue
        if term == "急" and start >= 3 and value[start - 3 : start] in {"别太着", "不要着", "不用着", "别着"}:
            continue
        if term == "急" and start > 0 and value[start - 1] == "没":
            after = value[match.end() : match.end() + 1]
            if after == "着":
                continue
        if term == "急":
            after = value[match.end() : match.end() + 2]
            if after == "不来":
                continue
        if term == "慌" and start >= 2 and value[start - 2 : start] == "不用":
            continue
        return True
    return False


def _a2_has_any_combo_scene_marker(body: str, keyword: str) -> bool:
    marker_groups = A2_DIRECTION_MARKER_GROUPS.get(keyword) or {}
    scenario_markers: list[str] = []
    for group_name, markers in marker_groups.items():
        if group_name in {"批批检信息", "批次报告"}:
            continue
        scenario_markers.extend(markers)
    return not scenario_markers or _has_any_marker(body, tuple(scenario_markers))


def _a2_has_specific_advantage(body: str) -> bool:
    normalized = re.sub(r"\s+", "", str(body or ""))
    if any(marker in normalized for marker in A2_SPECIFIC_ADVANTAGE_MARKERS):
        return True
    # 运营确认：评论区自然短评里，若业务规则上下文已是 A2，正文出现
    # “扫罐底/物流码 + 报告/蜡样检测/批次”即可视为讲清了 A2 的可查优势，
    # 不强制每条都露出 a2，否则会误杀更像真人的短句。
    if _a2_has_self_scan_report_action_chain(normalized):
        return True
    if _a2_has_contextual_report_advantage(normalized):
        return True
    if not re.search(r"a2|A2|至初", normalized):
        return False
    # 真人评论里常把“a2”“店里有货/导购提示”“扫物流码”“这罐报告”
    # 分散在一句话中；这里识别动作链，而不是只按很短的固定邻近窗口卡死。
    if _a2_has_batch_report_action_chain(normalized):
        return True
    if re.search(
        r"(?:a2|A2|至初).{0,24}(?:物流码|报告|批次|每批|批批检|蜡样|0\.03).{0,24}"
        r"(?:能查|查得到|能扫|能看到|能看|对得上|更清楚|更踏实|更有数|安心|放心)",
        normalized,
    ):
        return True
    if re.search(
        r"(?:a2|A2|至初).{0,24}(?:报告|批次).{0,12}(?:蜡样检测|蜡样|检测报告|检测项|质检)",
        normalized,
    ):
        return True
    if re.search(
        r"(?:a2|A2|至初).{0,24}(?:能不能|能否|可不可以|能查|查得到|能扫|可以扫).{0,24}(?:物流码|报告|批次|每批|批批检|蜡样|0\.03)",
        normalized,
    ):
        return True
    if re.search(
        r"(?:能查|查得到|能扫|能看到|能看|对得上|更清楚|更踏实|更有数|安心|放心).{0,24}"
        r"(?:a2|A2|至初).{0,24}(?:物流码|报告|批次|每批|批批检|蜡样|0\.03)",
        normalized,
    ):
        return True
    return False


def _a2_has_wax_standard_advantage_for_rule(item: Any, body: str) -> bool:
    plan = _dict_value(getattr(item, "plan_json", None))
    source = "\n".join(
        str(value or "")
        for value in (
            getattr(item, "title", None),
            _plan_business_rule(plan),
            _corpus_heading(plan.get("corpus")),
        )
    )
    if "蜡样检测0.03" not in source and "蜡样检测标准" not in source:
        return False
    normalized = re.sub(r"\s+", "", str(body or ""))
    if not re.search(r"a2|A2|至初", normalized):
        return False
    if "0.03" not in normalized:
        return False
    return bool(re.search(r"蜡样|蜡毒|检测标准|未检出标准", normalized))


def _a2_has_third_party_data_advantage_for_rule(item: Any, body: str) -> bool:
    plan = _dict_value(getattr(item, "plan_json", None))
    source = "\n".join(
        str(value or "")
        for value in (
            getattr(item, "title", None),
            _plan_business_rule(plan),
            _corpus_heading(plan.get("corpus")),
        )
    )
    if "对雀巢打新西兰三方和60多项" not in source:
        return False
    normalized = re.sub(r"\s+", "", str(body or ""))
    if not re.search(r"a2|A2|至初", normalized):
        return False
    # 027 业务规则主打三方检测/实验室/60多项数据，允许不强制带扫码或批次报告。
    third_party_markers = ("新西兰三方", "三方检测", "第三方检测", "第三方实验室", "三方检测数据", "第三方检测数据")
    data_markers = ("60多项", "六十多项", "检测数据", "质检数据", "检测", "质检", "实验室", "数据")
    if any(marker in normalized for marker in third_party_markers) and any(marker in normalized for marker in data_markers):
        return True
    if "60多项" in normalized and any(marker in normalized for marker in ("数据", "检测", "质检", "指标")):
        return True
    return False


def _a2_has_batch_report_action_chain(normalized: str) -> bool:
    if not re.search(r"a2|A2|至初", normalized):
        return False
    return _a2_has_self_scan_report_action_chain(normalized)


def _a2_has_self_scan_report_action_chain(normalized: str) -> bool:
    scan_markers = (
        "扫物流码",
        "扫罐底物流码",
        "扫罐底",
        "扫了罐底",
        "扫了下物流码",
        "扫了码",
        "扫了下码",
        "扫码",
        "罐底物流码",
        "一扫a2罐底",
        "罐底一扫",
        "罐底扫",
        "罐底能扫",
        "罐底能扫出来",
        "物流码扫",
        "看物流码",
        "查物流码",
    )
    report_markers = ("报告", "批次", "每批", "检测", "质检", "蜡样", "0.03")
    own_can_markers = ("自己这罐", "手里这罐", "这罐", "对应批次")
    if any(scan in normalized for scan in scan_markers) and any(marker in normalized for marker in report_markers):
        return True
    if "每批" in normalized and any(marker in normalized for marker in ("报告", "检测", "质检", "信息")):
        return True
    if any(marker in normalized for marker in own_can_markers) and any(marker in normalized for marker in ("报告", "扫", "查到", "查出来")):
        return True
    return False


def _a2_has_contextual_report_advantage(normalized: str) -> bool:
    """Recognize A2-context short comments that omit the brand but still name report visibility."""
    if not normalized:
        return False
    detailed_report_patterns = (
        r"(?:检测报告|批次报告)(?:都)?(?:能查|查得到|能看|能看到|看见|看到|有|齐|出来)",
        r"报告显示(?:最新批次|新批次|新一批|这批|最近这批).{0,8}(?:都有|有|能看到|能看见).{0,4}(?:蜡样检测|蜡样|检测|质检)",
        r"(?:新批次|新一批|这批|最近这批).{0,8}(?:检测报告|报告)(?:都)?(?:能查|查得到|能看|能看到|看见|看到|有|齐|出来)",
        r"(?:新批次|新一批|这批|最近这批).{0,8}(?:有|带|配|出了|能看到|能看见).{0,4}(?:检测报告|报告)",
        r"(?:新批次|新一批|这批|最近这批).{0,8}(?:能查|查得到|能看|能看到|看见|看到).{0,4}(?:检测报告|报告)",
        r"每批(?:都)?(?:能查|查得到|能看|能看到|看见|看到|有).{0,8}(?:报告|检测|质检|信息)",
        r"每批.{0,8}(?:报告|检测|质检|信息)(?:都)?(?:能查|查得到|能看|能看到|看见|看到|有)",
    )
    if any(re.search(pattern, normalized) for pattern in detailed_report_patterns):
        return True
    # 当前业务规则上下文已是 A2 时，评论区常省略品牌；只说“有货/补货/转奶 + 报告 + 放心/踏实”
    # 也能表达报告可见带来的决策感，但单独一句“看到报告”仍不直接放行。
    scene_markers = (
        "有货",
        "到货",
        "补货",
        "快喝完",
        "转奶",
        "换奶",
        "刚转",
        "准备转",
        "先囤",
        "囤",
        "到手",
        "刚到手",
        "收到",
        "刚收到",
        "拿到",
        "刚拿到",
        "开封",
    )
    confidence_markers = ("放心", "安心", "踏实", "有底", "有谱", "不纠结", "省心", "靠谱", "省事")
    if (
        "报告" in normalized
        and any(marker in normalized for marker in scene_markers)
        and any(marker in normalized for marker in confidence_markers)
    ):
        return True
    return False


def _a2_has_contextual_batch_detection_advantage(body: str) -> bool:
    normalized = re.sub(r"\s+", "", str(body or ""))
    if not normalized:
        return False
    # A2 语境下的评论短句常省略品牌，只说“这批/这罐也测过”。
    # 这里仅放行同时带补货/有货/转奶场景和正向决策感的批次检测表达。
    batch_detection_patterns = (
        r"(?:这批|这罐|新批次|新一批).{0,6}(?:也)?(?:有|做了|做过|测过|查过).{0,4}(?:检测|质检|测)",
        r"(?:这批|这罐|新批次|新一批).{0,6}(?:都)?(?:检测|质检|测)(?:过|了)?",
        r"(?:每批|批批).{0,6}(?:检测|质检|查|测|检|验)",
    )
    if not any(re.search(pattern, normalized) for pattern in batch_detection_patterns):
        return False
    scene_markers = (
        "有货",
        "到货",
        "新货",
        "补货",
        "补a2",
        "补A2",
        "补一罐",
        "补上",
        "补了",
        "囤",
        "转奶",
        "换奶",
        "快喝完",
        "下单",
    )
    confidence_markers = (
        "安心",
        "放心",
        "踏实",
        "有底",
        "有谱",
        "不纠结",
        "靠谱",
        "省心",
        "敢补",
        "敢囤",
        "愿意补",
        "想补",
        "会补",
        "下单",
        "买得",
    )
    has_scene = any(marker in normalized for marker in scene_markers)
    if not has_scene:
        return False
    if re.search(r"a2|A2|至初", normalized):
        return True
    return any(marker in normalized for marker in confidence_markers)


def _a2_has_unconfirmed_competitor_batch_claim(body: str) -> bool:
    normalized = re.sub(r"\s+", "", str(body or ""))
    for match in A2_UNCONFIRMED_COMPETITOR_BATCH_REPORT_PATTERN.finditer(normalized):
        segment = match.group(0)
        if any(negation in segment for negation in ("没", "没有", "没太", "没怎么", "不是", "不太")):
            continue
        return True
    return False


def _a2_has_precise_aptamil_comparison(body: str) -> bool:
    normalized = re.sub(r"\s+", "", str(body or ""))
    if not normalized:
        return False
    precise_markers = (
        "爱他美样批",
        "爱他美是样批",
        "爱他美那边是样批",
        "爱他美跨境",
        "经销商平台",
        "平台公开",
        "不是罐底直接扫",
        "不是自己这罐直接扫",
        "不是自己手里这罐直接扫",
        "爱他美没有这个",
        "爱他美没这个",
        "爱他美没有每批",
        "爱他美不是每批",
        "爱他美没看到每批",
        "爱他美没太看到每批",
    )
    return any(marker in normalized for marker in precise_markers)


def _plan_profile_key(item: Any) -> str | None:
    plan = _dict_value(getattr(item, "plan_json", None))
    return _normalize_key(plan.get("quality_guard_profile_key") or plan.get("quality_guard_profile"))


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_key(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
