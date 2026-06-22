"""QA guard for repeated article business-rule phrase patterns."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SKELETON_PARTS: dict[str, tuple[str, ...]] = {
    "selection_process": (
        "纠结",
        "犹豫",
        "做功课",
        "翻成分表",
        "看成分表",
        "对比",
        "看评价",
        "问朋友",
        "问店员",
        "选奶",
        "换奶",
        "4段",
    ),
    "price": (
        "贵",
        "不便宜",
        "价格",
        "肉疼",
        "趁活动",
        "不算便宜",
        "闭眼买",
        "心疼",
    ),
    "kid_acceptance": (
        "愿意喝",
        "不排斥",
        "不抗拒",
        "接受",
        "喝完",
        "咕咚",
        "顺口",
        "口味",
        "主动要喝",
        "喝光",
    ),
    "ai_closure": (
        "省心",
        "踏实",
        "固定",
        "固定下来",
        "心里有数",
        "好执行",
        "省得",
        "先这样",
        "继续喝着",
        "不用额外操心",
    ),
}

AI_PHRASES = (
    "省心",
    "踏实",
    "固定下来",
    "这事先这么放着",
    "不用每天临时凑",
    "不用临时凑",
    "不用额外想一堆",
    "不用额外想",
    "孩子愿意喝就好执行",
    "早上冲得快",
    "价格不算友好",
    "心里有数",
    "安心",
    "老母亲",
    "神药",
    "收藏起来",
    "收藏",
    "没那么焦虑",
    "放进日常",
    "固定在日常",
)

STATE_TEMPLATE_PHRASES = (
    "精神头足",
    "精神头十足",
    "精神头一直在线",
    "精神头挺好",
    "精神抖擞",
    "精神满满",
    "精神好",
    "状态一直在线",
    "状态在线",
    "状态一直挺稳",
    "状态挺稳",
    "状态稳得很",
    "状态好",
    "胃口一直在线",
)

WANGYUE_GROWTH_NUTRITION_DRIFT_PHRASES = (
    "身高体重曲线",
    "身高体重",
    "每天冲一杯",
    "日常冲一杯",
    "冲一杯",
    "每天一杯",
    "每天两杯",
    "每天当奶喝",
    "早晚一杯",
    "每天喝奶",
    "每天喝上",
    "早晚要喝",
    "当早餐补充",
    "当早餐",
    "纯牛奶",
    "喝奶敏感",
    "奶粉杯",
    "奶粉罐",
    "奶罐子",
    "配料表",
    "配料",
    "配方",
    "成分",
    "乳铁蛋白",
    "DHA",
    "ARA",
    "活性蛋白",
    "大脑成长",
    "支持保护力",
    "微量元素",
    "容易缺",
    "支持发育",
    "看了半天",
    "看来看去",
    "挑来挑去",
    "怕踩坑",
    "自己每天喝",
    "主动提醒我泡",
    "提醒我泡",
    "每天就是旺玥",
    "每天给他喝",
    "当主力",
    "开始喝旺玥",
    "平时喝着",
    "喝着挺实在",
    "喝得可带劲",
    "喝着对口",
    "喝得顺口",
    "喝得挺顺",
    "喝着挺顺",
    "喝着也顺",
    "喝得顺",
    "喝着顺",
    "日常喝着顺手",
    "日常喝喝顺手",
    "喝得适应",
    "喝着适应",
    "喝着不难接受",
    "喝着还行",
    "喝着接受",
    "孩子喝着接受",
    "孩子喝着也接受",
    "自己记得去喝",
    "记得去喝",
    "放柜子里",
    "喝下来",
    "喝下来挺对路",
    "喝得自然",
    "每天喝得自然",
    "喝得习惯",
    "愿意喝",
    "孩子愿意喝",
    "娃愿意喝",
    "肯喝",
    "不抗拒",
    "开封",
    "奶香",
    "泡奶",
    "冲开",
    "随手就能冲",
    "粉质",
    "不结块",
    "没结块",
    "冲出来",
    "怪味",
    "喝了段时间",
    "试了段时间",
    "先喝着观察",
    "后续效果",
    "后续再看效果",
    "用着挺顺手",
    "日常里顺手就给",
    "顺手就给了",
    "顺手给了",
    "娃自己愿意",
    "自己愿意",
    "愿意接受",
    "口感娃也挺爱喝",
    "娃也挺爱喝",
    "挺爱喝",
    "主动说要喝奶",
    "要喝奶奶",
    "抱着喝",
    "咂咂嘴",
    "好喝",
    "蹦蹦跳跳",
    "跑跑跳跳",
    "跑来跑去",
    "蹦跶",
    "睡得沉",
    "活力也更足",
    "活力满满",
    "精力跟得上",
    "精力足",
    "精力挺足",
    "跑跳精力",
    "精神头",
    "精神好",
    "状态不错",
    "状态好",
    "长势",
    "营养到位",
    "状态怎么样",
    "喝一阵",
    "坚持喝一喝",
    "精神点就好",
    "小身板",
    "更结实",
    "长得好",
    "一步搞定",
    "一罐搞定",
    "一罐到位",
    "一次顾好",
    "一次性顾好",
    "一次补到位",
    "成长有底",
    "成长力",
    "成长不掉队",
    "空罐",
    "翻出一罐",
    "抢着喝",
    "囤货",
    "没白囤",
    "囤的",
    "囤了",
    "囤几罐",
    "那叫一个投入",
    "罐底",
    "选对了",
    "选对",
    "补这补那",
    "该补的",
    "先喝喝看",
    "效果啥",
    "省得我东想西想",
    "图个方便",
    "链接",
    "甩了旺玥的链接",
    "继续买",
    "继续买这个",
    "带了一罐",
    "柜子里那罐旺玥",
    "柜子里那罐",
    "凑过去看看",
    "捧着罐子",
    "拿着罐子",
    "罐子看",
    "催我泡",
    "罐子放回包",
    "明天喝",
    "留着明天喝",
    "眼睛和身体状态",
    "身体状态",
    "营养保险",
    "兜底",
    "兜住",
    "保障",
    "饭量",
    "饭菜",
    "挑食",
    "吃饭",
    "小零食",
    "三餐",
    "加餐",
    "配饭",
    "身高",
    "体重",
    "长高",
    "长个",
    "喝完",
    "喊累",
    "跑几步就喊累",
)

WANGYUE_ARTICLE_LOGIC_DRIFT_PHRASES = (
    "口粮",
    "购物车",
    "放进购物车",
    "直接下单",
    "下单了",
    "大路灯",
    "护眼",
    "用眼过渡",
    "用眼过度",
    "眼睛都快冒星星",
    "眼睛还亮亮",
    "眼睛亮亮",
    "脸色都亮堂",
    "脸色亮堂",
    "奶香清淡",
    "冲出来",
    "泡了杯",
    "给他泡了杯",
    "给她泡了杯",
    "没怎么咳嗽",
    "咳嗽",
    "吭吭唧唧",
    "换成了皇家美素佳儿旺玥",
    "换成了旺玥",
    "给孩子选了皇家美素佳儿旺玥",
    "给他选了皇家美素佳儿旺玥",
    "给她选了皇家美素佳儿旺玥",
    "给孩子选了旺玥",
    "给他选了旺玥",
    "给她选了旺玥",
    "给选了皇家美素佳儿旺玥",
    "给选了旺玥",
    "小脑瓜",
    "用脑太多",
    "脑子转得快",
    "奶粉罐",
    "家里那款",
    "家里那罐",
    "家里一直备着",
    "正好家里有",
    "家里有皇家美素佳儿旺玥",
    "把皇家美素佳儿旺玥放在家里",
    "把旺玥放在家里",
    "放在家里",
    "一直备着",
    "一直喝着",
    "平时那杯",
    "给着",
    "给娃试了",
    "给娃加了",
    "给他喝",
    "给她喝",
    "给孩子喝上",
    "下午点心",
    "补点眼脑营养",
    "顺手补补眼脑营养",
    "顺手补补",
    "先这么喝着看看",
    "你们娃也会这样吗",
    "翻了一圈",
    "天天喝",
    "让她喝上",
    "让他喝上",
    "眼睛有点累",
    "眼睛累",
    "翻出绘本",
    "看绘本",
    "绘本",
    "动画片",
    "动画",
    "揉眼睛",
    "用眼",
    "视力",
    "学习效果",
    "不结块",
    "粉质",
    "煮粥",
    "往牛奶里加",
    "牛奶里加",
    "加了一勺旺玥",
    "加一勺旺玥",
    "兑旺玥",
    "日常喝着顺手",
    "日常喝喝顺手",
    "日常里顺手就给",
    "顺手就给了",
    "顺手给了",
)

WANGYUE_ROW2_EYE_BRAIN_DRIFT_PHRASES = (
    "叶黄素",
    "护眼",
    "视力",
    "近视",
    "眼睛营养",
    "眼睛发育",
    "眼睛酸",
    "眼睛不酸了",
    "眼睛不酸",
    "揉眼睛",
    "眼睛得跟上",
    "眼睛也不能落下",
    "脑子不够用",
    "脑子够不够用",
    "脑子跟着转",
    "脑子那块",
    "脑子眼睛",
    "大脑和眼睛",
    "看绘本",
    "翻绘本",
    "绘本",
    "画画",
    "写写画画",
    "写字",
    "看书",
    "小猪佩奇",
    "手机平板",
    "看视频",
)

WANGYUE_ROW2_DRINKING_ACTION_DRIFT_PHRASES = (
    "冲一杯",
    "泡一杯",
    "随手给他冲",
    "随手给她冲",
    "给他冲",
    "给她冲",
    "每天一杯",
    "每天两杯",
    "每天几杯",
    "早晚一杯",
    "早晚喝",
    "先喝着看",
    "先喝着",
    "家里常备",
    "家里备的",
    "家里备着",
    "家里给备的",
    "给他备上",
    "给她备上",
    "给家里备了",
    "家里常备着",
    "放家里当儿童奶粉备着",
    "平时就放家里",
    "放桌上备着",
    "当早餐喝",
    "放学先喝一杯",
    "就是这时候开始喝的",
    "递了杯旺玥",
    "直接递了杯旺玥",
    "翻出旺玥的罐子",
    "翻出来就是旺玥",
    "包里装的啥",
    "饿了渴了自然会去倒",
    "自然会去倒",
    "没白囤",
    "以前囤的",
    "囤的",
    "奶粉柜",
    "还剩半罐",
    "剩半罐",
    "空奶粉罐",
    "奶粉罐",
    "空罐",
    "旺玥放桌边",
    "放桌边",
    "活动后立刻",
    "玩累了直接冲",
    "回家喝一杯",
    "回家就喝一杯",
    "跑累了回家喝一杯",
    "补补保护力",
    "补点保护力",
    "补补营养",
    "想喝点",
    "就当补充营养",
    "当补充营养",
    "白天折腾完的补充",
    "折腾完的补充",
    "孩子活动量大以后",
    "我选奶粉会多看保护力",
    "活动量大以后，我选奶粉会多看",
    "桌上那盒旺玥",
    "那盒旺玥",
    "牛奶味",
    "喝得挺顺",
    "顺手补补",
    "递过去让她自己喝",
    "递过去让他自己喝",
    "把旺玥递过去让她自己喝",
    "把旺玥递过去让他自己喝",
    "旺玥喝了几个月",
    "喝了好几个月",
    "多备了旺玥",
    "备了旺玥",
    "天天追着补",
    "追着补",
)

HARD_AI_CLOSURE_PHRASES = (
    "老母亲",
    "神药",
    "收藏起来",
    "收藏",
    "固定下来",
    "这事先这么放着",
)

COMMON_AI_CLOSURE_PHRASES = (
    "希望能一直这样省心",
    "一直这样省心",
    "继续观察看看，先这样喂着吧",
    "继续观察看看",
    "继续观察着",
    "继续观察吧",
    "继续观察",
    "后续再观察看看",
    "先这样喝着看看",
    "先这样喝着",
    "先这样喂着吧",
    "先这样喂着",
    "先这么喂着",
    "就这样简单搞定",
    "简单搞定",
    "我也算松了口气",
    "松了口气",
    "暂时满意",
    "先这样记录一下",
    "欢迎留言聊聊",
    "欢迎留言",
    "留言聊聊",
    "评论区留言",
    "老母亲",
)

COMMON_AI_CLOSURE_REPLACEMENTS = (
    ("希望能一直这样省心", "希望后面少折腾点"),
    ("一直这样省心", "后面少折腾点"),
    ("继续观察看看，先这样喂着吧", ""),
    ("继续观察看看", ""),
    ("继续观察着", ""),
    ("继续观察吧", ""),
    ("继续观察", ""),
    ("后续再观察看看", ""),
    ("先这样喝着看看", ""),
    ("先这样喝着", ""),
    ("先这样喂着吧", ""),
    ("先这样喂着", ""),
    ("先这么喂着", ""),
    ("就这样简单搞定", "就行"),
    ("简单搞定", ""),
    ("我也算松了口气", ""),
    ("松了口气", ""),
    ("暂时满意", ""),
    ("先这样记录一下", "记一笔"),
    ("欢迎留言聊聊", ""),
    ("欢迎留言", ""),
    ("留言聊聊", ""),
    ("评论区留言", ""),
    ("老母亲", "我"),
)

ODD_PHRASE_REPLACEMENTS = (
    ("打开湿湿的？", ""),
    ("打开湿湿的", ""),
    ("开罐那会还湿湿的，问了才知道是工艺原因，喝着没问题。", ""),
    ("开罐那会还湿湿的，问了才知道是工艺原因，喝着没问题", ""),
    ("湿湿的", ""),
    ("潮湿感", ""),
    ("开盖那会儿有点湿，查了是工艺问题", ""),
    ("开盖那会儿有点湿", ""),
    ("刚打开罐子湿的，不知道正常不？", ""),
    ("刚打开罐子湿的", ""),
    ("打开奶粉罐湿的感觉，还以为受潮了，查了说正常。", ""),
    ("打开奶粉罐湿的感觉，还以为受潮了，查了说正常", ""),
    ("打开奶粉罐湿的感觉", ""),
    ("为了闺女少喝奶茶，", ""),
    ("为了闺女少喝奶茶", ""),
    ("娃上小学后", "孩子上学后"),
    ("孩子上小学后", "孩子上学后"),
    ("上小学后", "上学后"),
    ("有点湿", ""),
    ("开罐的时候勺子上带着点湿气，我反而。", ""),
    ("勺子上带着点湿气", "粉质看着还细"),
    ("我反而。", ""),
    ("奶粉有点潮湿", "奶粉状态还行"),
    ("开罐发现是湿的", ""),
    ("对🧠的保护", "眼脑营养"),
    ("🧠", "眼脑营养"),
    ("挑食宝宝", "挑食娃"),
    ("宝宝", "孩子"),
    ("宝妈", "妈妈"),
    ("内护力", "保护力"),
    ("自护力", "保护力"),
    ("抵抗力", "保护力"),
    ("底气", "保护力"),
    ("体质明显比同龄人稳", "看着比同龄人结实"),
    ("体质稳定", "状态稳定"),
    ("体质稳了", "状态稳了"),
    ("体质稳", "状态稳"),
    ("小体质", "身体状态"),
    ("体质", "身体状态"),
    ("正文：", ""),
    ("正文开头", ""),
    ("上了上学以后", "上学以后"),
    ("上了上学后", "上学后"),
    ("日常一杯当辅食", "日常一杯当补充"),
    ("当辅食", "当日常补充"),
    ("营养师朋友", "朋友"),
    ("营养师", "朋友"),
    ("皇家美美佳儿", "皇家美素佳儿"),
    ("主要是看里面保护力这块", "主要是看皇家美素佳儿旺玥的保护力这块"),
    ("主要看里面保护力这块", "主要看皇家美素佳儿旺玥的保护力这块"),
    ("看里面保护力这块", "看皇家美素佳儿旺玥的保护力这块"),
    ("看里面营养全面", "看皇家美素佳儿旺玥营养全面"),
    ("换了皇家美素佳儿旺玥", "选了皇家美素佳儿旺玥"),
    ("换了旺玥", "选了旺玥"),
    ("换成旺玥", "选了旺玥"),
    ("换到旺玥", "选了旺玥"),
    ("羊奶粉钱", "这罐奶粉钱"),
    ("羊奶粉", "奶粉"),
    ("流感多的时候", "请假多的时候"),
    ("流感", "小状况"),
    ("手足口", "班里请假"),
    ("P磷脂酰丝氨酸S", "磷脂酰丝氨酸"),
    ("P磷脂酰丝氨酸", "磷脂酰丝氨酸"),
    ("保护力也顺", "状态也顺"),
    ("背着有肉", "背上有肉"),
    ("午睡枕头边还放水杯，喝奶比喝水积极", "平时喝奶还算积极"),
    ("午睡枕头边还放水杯", "平时喝奶还算积极"),
    ("小状况季", "小状况多的时候"),
    ("肉疼的那种扎实感", "摸着挺扎实"),
    ("免疫力也顺手抓了", "保护力这块也看了"),
    ("体格挺打底", "体格看着挺扎实"),
    ("一杯下去又活过来了", "休息一会儿状态能缓过来"),
    ("冲一杯就搞定", "日常补充起来还算顺手"),
    ("每天当补给", "作为日常补充"),
    ("一杯搞定保护力和眼脑营养", "保护力和眼脑营养这两块我都会看"),
    ("一杯搞定", "日常补充"),
    ("带出门消停了不少", "带出门状态还可以"),
    ("出门消停了不少", "出门状态还可以"),
    ("消停了不少", "状态还可以"),
    ("也没有动不动就掉状态", "状态也还可以"),
    ("没有动不动就掉状态", "状态看着还可以"),
    ("动不动就掉状态", "状态不太稳"),
    ("营养保险", "日常营养补充"),
    ("缺这缺那", "营养不均衡"),
    ("缺一点少一点", "营养没跟上"),
    ("缺了啥", "营养没跟上"),
    ("缺啥补啥", "营养不均衡"),
    ("缺啥", "营养不均衡"),
    ("反正不贵", "确实不便宜"),
    ("价格不贵", "价格不低"),
    ("不算贵", "不算便宜"),
    ("也不贵", "也不便宜"),
    ("最近季", "最近"),
    ("日常喝着顺手", "日常里还算合适"),
    ("日常喝喝顺手", "日常里还算合适"),
    ("家里一直备着皇家美素佳儿旺玥", "家里一直是皇家美素佳儿旺玥"),
    ("正好家里有皇家美素佳儿旺玥", "正好留意到皇家美素佳儿旺玥"),
    ("家里有皇家美素佳儿旺玥", "留意到皇家美素佳儿旺玥"),
    ("把皇家美素佳儿旺玥放在家里", "留意到皇家美素佳儿旺玥"),
    ("把旺玥放在家里", "留意到旺玥"),
    ("一直备着", "一直关注"),
    ("一直喝着", "一直关注"),
    ("平时那杯皇家美素佳儿旺玥", "皇家美素佳儿旺玥"),
    ("平时那杯旺玥", "旺玥"),
    ("给着", "用着"),
    ("给娃试了", "留意到"),
    ("给娃加了", "留意到"),
    ("给他喝", "留意到"),
    ("给她喝", "留意到"),
    ("给孩子喝上", "留意到"),
    ("下午点心", "日常安排"),
    ("补点眼脑营养", "关注眼脑营养"),
    ("顺手补补眼脑营养", "顺带关注眼脑营养"),
    ("顺手补补", "顺带关注"),
    ("先这么喝着看看", "先这样观察"),
    ("你们娃也会这样吗？", ""),
    ("你们娃也会这样吗", ""),
    ("翻了一圈", "想了一下"),
    ("家里备着皇家美素佳儿旺玥", "皇家美素佳儿旺玥"),
    ("家里备着旺玥", "旺玥"),
    ("家里就备上了", "后来就关注到旺玥"),
    ("家里那款皇家美素佳儿旺玥", "皇家美素佳儿旺玥"),
    ("家里那款旺玥", "旺玥"),
    ("家里那款儿童奶粉", "这款儿童奶粉"),
    ("家里那款", "这款儿童奶粉"),
    ("家里那罐皇家美素佳儿旺玥", "皇家美素佳儿旺玥"),
    ("家里那罐旺玥", "旺玥"),
    ("家里那罐", "这款儿童奶粉"),
    ("日常里顺手就给了", "日常里自然会想到它"),
    ("日常里顺手就给", "日常里自然会想到它"),
    ("顺手就给了", "自然会想到它"),
    ("顺手给了", "自然会想到它"),
    ("柜子里那罐旺玥", "旺玥"),
    ("柜子里那罐", "这款儿童奶粉"),
    ("凑过去看看", "会多看一眼"),
    ("有些变化不敢全归到奶上，但日常喝着我会继续观察", "有些变化不敢全归到奶上"),
    ("有些变化不敢全归到奶上，但日常喝着我会", "有些变化不敢全归到奶上"),
    ("有些变化不敢全归到奶上，但喝着我就", "有些变化不敢全归到奶上"),
    ("但日常喝着我会继续观察", ""),
    ("但日常喝着我会", ""),
    ("但喝着我就", ""),
    ("日常喝着我会", "日常喝着我会继续观察"),
    ("先着吧", ""),
    ("我这我算是", ""),
    ("我这我", "我"),
    ("，效果", ""),
    ("半电量永远满格", "精力一直挺足"),
    ("我俩都行", "孩子喝着还行"),
    ("奶粉奶粉罐", "奶粉罐"),
    ("没白做功課", "没白做功课"),
    ("谁懂这种当妈的轻松感", "这种小变化我会记一下"),
    ("谁懂这种我的踏实感", "这种小变化我会记一下"),
    ("谁懂啊，当妈的心里就这点小算盘", "这种小变化我会记一下"),
    ("你家娃在忙啥？", ""),
    ("你家娃在忙啥", ""),
    ("当妈的心里稳当多了", "先记一笔"),
    ("吸管一插自己抱着喝", "自己拿着杯子喝"),
    ("吸管一插", "杯子一拿"),
    ("丢过去", "递过去"),
)

ODD_PHRASES = tuple(source for source, _replacement in ODD_PHRASE_REPLACEMENTS)

STRONG_REAL_PHRASES = (
    "没再半夜闹腾",
    "不容易中招",
    "精力恢复得快",
    "一直挺稳",
    "可能跟每天那杯旺玥有关系",
    "可能跟每天那杯有关系",
    "坐不住",
    "坐不久",
    "少请假",
    "长个",
    "窜个",
    "抵抗力",
)

HARD_RISK_PHRASES = (
    "保证长高",
    "一定长高",
    "喝了就不生病",
    "不生病了",
    "再也不生病",
    "提高免疫力",
    "增强免疫力",
    "免疫力提高",
    "治疗",
    "改善乳糖不耐受",
    "乳糖不耐受好转",
    "专注力提升",
    "专注力变好",
    "体检身高追上来",
    "身高追上来两厘米",
    "长高两厘米",
    "长高2厘米",
    "高了两厘米",
    "防风全靠",
    "全靠它",
    "全靠旺玥",
    "没白养",
    "没白选",
    "保护力确实",
    "赶紧把旺玥安排上",
    "赶紧安排上",
    "临时补救",
)

ADULT_SELF_DRINKING_PHRASES = (
    "给自己冲了一杯",
    "给自己冲一杯",
    "自己冲了一杯",
    "自己冲一杯",
    "给自己泡了一杯",
    "给自己泡一杯",
    "我喝了一杯旺玥",
    "我也喝旺玥",
    "我喝旺玥",
    "我喝奶粉",
    "我喝儿童奶粉",
    "我喝这罐奶粉",
    "我现在喝的是皇家美素佳儿旺玥",
    "我现在喝的是旺玥",
    "妈妈自己喝旺玥",
    "我自己也能当早餐奶",
    "自己也能当早餐奶",
    "我自己喝着觉得挺香",
    "我自己喝了一口",
    "我自己偷偷喝了一口",
    "自己偷偷喝了一口",
    "我先喝了一口",
    "我先喝一口",
    "泡了一杯自己先尝",
    "自己先尝了",
    "自己先尝",
    "我先偷喝了一口",
    "先偷喝了一口",
    "自己喝了一口",
    "自己先喝了一口",
    "偷喝她剩的一口底",
    "偷喝他剩的一口底",
    "偷喝剩的一口底",
    "我偷喝过半杯",
    "偷喝过半杯",
    "到手尝了口",
    "尝了口，不甜腻",
    "我自己偷偷尝过",
    "自己偷偷尝过",
    "我自己尝了一口",
    "自己尝了一口",
    "我自己尝过",
    "自己尝过",
    "我自己尝了下",
    "自己尝了下",
    "我自己喝着也觉得还行",
    "我自己喝着",
    "我偷偷尝了一口",
    "偷偷尝了一口",
    "偷偷尝过",
    "我喝着试了试",
    "我喝着试试",
)

CHILD_SELF_BREWING_PHRASES = (
    "每天主动要泡",
    "主动去泡奶喝",
    "自己主动冲奶",
    "自己主动泡奶",
    "自己主动去泡奶了",
    "自己主动冲",
    "自己主动泡",
    "自己冲旺玥",
    "自己泡旺玥",
    "自己开罐旺玥泡一杯",
    "自己打开罐子",
    "自己打开奶粉罐",
    "自己打开旺玥罐子",
    "自己递过来让我开",
    "递过来让我开",
    "自己递给我让我开",
    "递给我让我开",
    "自己拿过来让我开",
    "拿过来让我开",
    "自己抱过来让我开",
    "抱过来让我开",
    "找出一罐旺玥",
    "找出那罐旺玥",
    "抱过来往我手里塞",
    "找出一罐旺玥，抱过来往我手里塞",
    "翻柜子，找出一罐旺玥",
    "孩子自己倒水舀粉",
    "娃自己倒水舀粉",
    "自己倒水舀奶粉",
    "自己倒水舀粉",
    "自己舀粉冲奶",
    "自己舀了两勺",
    "自己舀两勺",
    "自己舀了两勺冲水喝",
    "自己舀奶粉",
    "自己拿勺子舀了三勺",
    "自己拿勺子舀",
    "自己搬小凳子冲奶",
    "自己搬小凳子去拿奶粉罐",
    "自己搬小凳子去拿罐子",
    "自己洗完澡就去厨房泡旺玥",
    "自己拿勺子挖了两勺",
    "每天自己挖奶粉",
    "自己挖奶粉",
    "自己偷偷多舀了一勺",
    "自己搬奶粉罐去了",
    "自己搬奶粉罐",
    "自己开柜门拿奶粉罐",
    "开柜门拿奶粉罐",
    "踮脚够奶粉罐",
    "蹬着小凳子去够奶粉罐",
    "自己搬凳子去够柜子上的罐子",
    "搬凳子去够柜子上的罐子",
    "自己搬凳子去够罐子",
    "搬凳子去够罐子",
    "去够奶粉罐",
    "够奶粉罐",
    "去够柜子上的罐子",
    "够柜子上的罐子",
    "抱着空罐子在地上滚",
    "抱着空罐子",
    "扛奶粉",
    "自己主动去冲",
    "自己主动去泡",
    "天天自己主动去泡",
    "天天自己主动去冲",
    "主动去倒奶喝",
    "自己到点就去泡一杯",
    "自己又跑去倒了半杯",
    "自己泡上",
    "自己记得泡",
    "自己记得冲",
    "娃自己会去冲",
    "孩子自己会去冲",
    "自己会去冲",
    "自己跑去冲一杯",
    "自己去冲",
    "主动去冲",
    "每天自己冲",
    "每天自己泡",
    "每天一杯自己冲",
    "每天一杯自己泡",
    "自己每天冲一杯",
    "每天自己倒着喝",
    "自己倒着喝",
    "自己倒来喝",
    "自己端着小碗蹲旁边等",
    "自己端着小碗",
    "碗底舔干净",
    "到点自己冲",
    "到点自己泡",
    "主动自己冲",
    "主动自己泡",
    "每天早上主动去冲",
    "每天早上自己跑去冲一杯",
    "自己抱着杯子要冲",
    "自己抱着罐子催我冲",
    "自己抱着罐子喝",
    "娃自己抱着喝",
    "孩子拿着自己冲",
    "娃拿着自己冲",
    "自己抱着罐子看",
    "自己抱着罐子让冲",
    "自己捧着旺玥罐子叫妈妈开",
    "自己捧着奶粉罐子叫妈妈开",
    "捧着旺玥罐子叫妈妈开",
    "捧着奶粉罐子叫妈妈开",
    "自己跑去把旺玥罐子抱过来",
    "自己跑去把奶粉罐抱过来",
    "自己抱出奶粉罐",
    "自己抱出旺玥罐子",
    "自己抱出旺玥",
    "把旺玥罐子抱过来",
    "把奶粉罐抱过来",
    "伸手拽奶粉罐",
    "抱怀里不撒手",
    "当积木摆弄",
    "被她翻出来当积木",
    "被他翻出来当积木",
    "自己翻出奶粉罐",
    "自己翻出旺玥",
    "他泡好端着",
    "偷着干吃好几勺",
    "干吃好几勺",
    "偷着干吃",
    "干吃奶粉",
    "干吃",
    "拿勺子舀粉",
    "拿勺子舀奶粉",
    "拿勺子挖奶粉",
    "自己冲杯奶粉",
    "自己泡杯奶粉",
    "自己冲杯旺玥",
    "自己冲一杯旺玥",
    "自己泡一杯旺玥",
    "自己拆了条冲好",
    "自己拆条冲好",
    "自己拆了条",
    "拆了条冲好",
    "自己冲奶",
    "自己泡奶",
    "主动冲奶",
    "主动泡奶",
    "主动去泡奶",
    "主动要泡",
    "自己就去泡",
    "自己就去冲",
    "娃冲完",
    "孩子冲完",
)

CHILD_FORMULA_BOTTLE_PHRASES = (
    "抱着奶瓶",
    "奶瓶一递过去",
    "奶瓶",
)

WANGYUE_WRONG_BRAND_PHRASES = (
    "贝博氏旺玥",
    "贝博氏",
    "源悦",
    "小安素",
)

WANGYUE_EXPLICIT_AGE_PHRASES = (
    "断奶",
    "辅食",
    "半岁",
    "三岁后",
    "3岁后",
    "三岁",
    "3岁",
    "两岁",
    "2岁",
    "一岁后",
    "宝宝一岁多",
    "宝宝1岁多",
    "娃一岁多",
    "孩子一岁多",
    "一岁多",
    "1岁多",
    "一岁半",
    "1岁半",
)

WANGYUE_PORTABLE_FORM_PHRASES = (
    "书包侧袋",
    "书包侧兜",
    "塞书包",
    "塞进背包",
    "背包里塞",
    "书包里放旺玥",
    "书包里放一盒旺玥",
    "书包里",
    "书包有奶",
    "塞一罐旺玥到书包里",
    "塞一袋旺玥",
    "一袋旺玥",
    "包里一定会塞",
    "路上喝",
    "一盒旺玥",
    "旺玥小条装",
    "便携装",
    "出门揣",
    "揣两小袋",
    "两小袋",
    "小袋",
    "玩累了直接冲",
    "直接冲",
    "分装",
    "两条旺玥",
    "两条",
    "小双肩包",
    "出门背的小双肩包",
    "包里除了水杯纸巾",
    "包里除了水杯零食",
    "辅食机都塞包里",
    "塞包里",
    "一包皇家美素佳儿旺玥",
    "一包旺玥",
    "塞几包",
    "几包",
    "随时能泡",
    "出门包里会多放一罐奶粉",
    "包里会多放一罐奶粉",
    "多放一罐奶粉",
    "包里光是奶粉和水壶",
    "我最烦一罐罐分开带",
    "一罐全包",
    "出门前顺手抓一罐",
    "顺手抓一罐",
    "出门前顺手带一罐",
    "顺手带一罐",
    "带一罐旺玥",
    "抓一罐",
    "出门包里",
    "出门太急忘了带旺玥",
    "忘了带旺玥",
    "忘带旺玥",
    "忘了带奶粉",
    "忘带奶粉",
    "带旺玥",
    "带奶粉",
    "塞了旺玥",
    "开盖即饮",
    "即饮",
    "随身包",
    "外出随身包",
    "奶粉条",
    "小条装",
    "几袋",
    "三根",
    "奶粉盒",
    "水壶里都是这个",
    "水壶里",
    "奶粉袋",
    "倒进奶粉袋",
    "带两小包",
    "两小包",
    "小包冲奶",
    "这小包",
    "兑点温水摇匀",
    "兑温水",
    "当顺手的水喝",
    "水喝下去",
    "当水喝",
    "当水奶喝",
    "水奶",
    "搁在茶几上",
    "放在茶几上",
    "路过就喝几口",
    "抱着罐子",
    "抱着奶粉罐",
)

WANGYUE_DIGESTIVE_EFFECT_PHRASES = (
    "不是胀气就是不爱喝",
    "胀气",
    "肚子软软的",
    "小肚子",
    "便便也规律",
    "便便规律",
    "没闹过肚肚",
    "闹过肚肚",
    "闹肚子",
    "肚肚",
    "肠胃",
    "脾胃",
    "消化",
    "舌苔白",
    "舌苔",
)

CHILD_SUBJECT_PATTERN = r"(?:娃|孩子|宝贝|宝宝|小朋友|儿子|闺女|他|她)"
CHILD_SELF_BREWING_PATTERNS = (
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己冲一杯"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己[^。！？；;，,]{{0,12}}(?:冲|泡)一杯"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己冲(?:旺玥|奶|奶粉)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己泡(?:旺玥|奶|奶粉)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己[^。！？；;，,]{{0,12}}(?:冲|泡)(?:旺玥|奶|奶粉)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;]{{0,24}}(?:找出|摸出|翻出|抱过来|拿过来)[^。！？；;]{{0,12}}(?:旺玥|奶粉|奶粉罐|罐子)"),
    re.compile(r"自己[^。！？；;，,]{0,8}主动去(?:冲|泡)"),
    re.compile(r"(?:现在|每天|早晚|一天[^。！？；;，,]{0,4}|到点|平时)[^。！？；;，,]{0,8}自己(?:冲|泡)一杯"),
    re.compile(r"(?:每天|早晚|一天[^。！？；;，,]{0,4}|到点|平时)[^。！？；;，,]{0,8}一杯[^。！？；;，,]{0,4}自己(?:冲|泡)"),
    re.compile(r"(?:每天|早晚|一天[^。！？；;，,]{0,4}|到点|平时)[^。！？；;，,]{0,8}自己记得(?:冲|泡)"),
    re.compile(r"自己[^。！？；;，,]{0,12}(?:冲|泡)(?:旺玥|奶|奶粉)"),
    re.compile(r"(?:放学|回家|回来|早上|晚上|每天|平时|到点)[^。！？；;，,]{0,12}自己(?:冲|泡)(?:一?杯|杯)(?:旺玥|奶粉|奶)"),
    re.compile(rf"{CHILD_SUBJECT_PATTERN}[^。！？；;，,]{{0,12}}自己(?:偷偷)?(?:拿勺子)?(?:倒水)?(?:多)?(?:舀|挖)(?:了?[一二两三]勺|粉|奶粉)(?:冲奶)?"),
    re.compile(r"自己(?:拿勺子)?(?:舀|挖)了?[一二两三0-9]+勺[^。！？；;，,]{0,8}(?:冲|泡|喝)"),
    re.compile(r"(?:摸出|翻出|拿出)[^。！？；;，,]{0,8}(?:旺玥|奶粉|罐)[^。！？；;，,]{0,8}自己(?:舀|挖|冲|泡)"),
    re.compile(r"(?:打开|开了|开)[^。！？；;，,]{0,8}(?:罐子|奶粉罐)[^。！？；;，,]{0,12}(?:娃|孩子|宝贝|宝宝|小朋友|儿子|闺女|他|她)?自己抱着喝"),
)

TEMPORAL_CONTEXT_PHRASES = (
    "风大的季节",
    "换季",
    "双十一",
    "降温",
    "春天",
    "寒假",
    "春节",
    "过年",
    "暑假",
    "冬天",
    "入冬",
    "入夏",
    "夏天",
    "天冷",
    "秋天",
    "入秋",
    "开学",
    "放假",
    "学期",
    "感冒季",
    "天气忽冷忽热",
    "天气一变",
    "小班",
    "中班",
    "大班",
)

TEMPORAL_CONTEXT_REPLACEMENTS = (
    ("风大的季节", "这阵"),
    ("换季", "这阵"),
    ("双十一", "之前"),
    ("降温", "这阵"),
    ("春天", "最近"),
    ("寒假", "这段时间"),
    ("暑假", "这段时间"),
    ("冬天", "最近"),
    ("入夏", "最近"),
    ("夏天", "最近"),
    ("天冷", "最近"),
    ("秋天", "最近"),
    ("入秋", "最近"),
    ("开学", "最近"),
    ("放假", "这段时间"),
    ("学期", "段时间"),
    ("感冒季", "这阵"),
    ("天气忽冷忽热", "最近"),
    ("天气一变", "这阵"),
    ("小班", "上学"),
    ("中班", "上学"),
    ("大班", "上学"),
)


@dataclass(frozen=True)
class ProductExperiencePhraseReview:
    pass_: bool
    rewrite_required: bool
    reasons: list[str]
    skeleton_parts: list[str]
    skeleton_hits: dict[str, list[str]]
    ai_phrase_hits: list[str]
    state_template_hits: list[str]
    odd_phrase_hits: list[str]
    strong_real_expression_hits: list[str]
    hard_risk_hits: list[str]
    adult_self_drinking_hits: list[str]
    child_self_brewing_hits: list[str]
    child_formula_bottle_hits: list[str]
    wangyue_wrong_brand_hits: list[str]
    wangyue_explicit_age_hits: list[str]
    wangyue_portable_form_hits: list[str]
    wangyue_digestive_effect_hits: list[str]
    wangyue_growth_nutrition_drift_hits: list[str]
    wangyue_article_logic_drift_hits: list[str]
    wangyue_row2_drinking_action_hits: list[str]
    temporal_context_hits: list[str]
    run_on_fragment_hits: list[str]
    malformed_fragment_hits: list[str]
    body_chars: int
    length_target: tuple[str, int, int] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "rewrite_required": self.rewrite_required,
            "reasons": self.reasons,
            "skeleton_parts": self.skeleton_parts,
            "skeleton_hits": self.skeleton_hits,
            "ai_phrase_hits": self.ai_phrase_hits,
            "state_template_hits": self.state_template_hits,
            "odd_phrase_hits": self.odd_phrase_hits,
            "strong_real_expression_hits": self.strong_real_expression_hits,
            "hard_risk_hits": self.hard_risk_hits,
            "adult_self_drinking_hits": self.adult_self_drinking_hits,
            "child_self_brewing_hits": self.child_self_brewing_hits,
            "child_formula_bottle_hits": self.child_formula_bottle_hits,
            "wangyue_wrong_brand_hits": self.wangyue_wrong_brand_hits,
            "wangyue_explicit_age_hits": self.wangyue_explicit_age_hits,
            "wangyue_portable_form_hits": self.wangyue_portable_form_hits,
            "wangyue_digestive_effect_hits": self.wangyue_digestive_effect_hits,
            "wangyue_growth_nutrition_drift_hits": self.wangyue_growth_nutrition_drift_hits,
            "wangyue_article_logic_drift_hits": self.wangyue_article_logic_drift_hits,
            "wangyue_row2_drinking_action_hits": self.wangyue_row2_drinking_action_hits,
            "temporal_context_hits": self.temporal_context_hits,
            "run_on_fragment_hits": self.run_on_fragment_hits,
            "malformed_fragment_hits": self.malformed_fragment_hits,
            "body_chars": self.body_chars,
            "length_target": self.length_target,
        }


def should_review_product_experience(plan: dict[str, Any] | None) -> bool:
    plan = plan or {}
    corpus = str(plan.get("corpus") or "")
    return (
        plan.get("rule_type") == "business_rule"
        and (
            str(plan.get("asset_key") or "").startswith("wangyue_")
            or "0705旺玥活动" in corpus
        )
    )


def review_product_experience_phrase(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any] | None,
) -> ProductExperiencePhraseReview:
    plan = plan or {}
    body_text = str(body or "")
    text = f"{title or ''}\n{body_text}"
    is_wangyue = _is_wangyue_plan(plan)
    skeleton_hits = {
        part: _hits(body_text, phrases)
        for part, phrases in SKELETON_PARTS.items()
        if _hits(body_text, phrases)
    }
    skeleton_parts = sorted(skeleton_hits)
    ai_hits = _hits(text, AI_PHRASES)
    state_template_hits = _hits_prefer_longer(text, STATE_TEMPLATE_PHRASES)
    odd_phrase_hits = _hits_prefer_longer(text, ODD_PHRASES)
    strong_real_hits = _hits(text, STRONG_REAL_PHRASES)
    hard_risk_hits = _hard_risk_hits(text)
    adult_self_drinking_hits = _hits_prefer_longer(text, ADULT_SELF_DRINKING_PHRASES)
    child_self_brewing_hits = _merge_hits(
        _hits_prefer_longer(text, CHILD_SELF_BREWING_PHRASES),
        _child_self_brewing_regex_hits(text),
    )
    child_formula_bottle_hits = _hits_prefer_longer(text, CHILD_FORMULA_BOTTLE_PHRASES)
    wangyue_wrong_brand_hits = _hits_prefer_longer(text, WANGYUE_WRONG_BRAND_PHRASES) if is_wangyue else []
    wangyue_explicit_age_hits = (
        _merge_hits(
            _hits_prefer_longer(text, WANGYUE_EXPLICIT_AGE_PHRASES),
            _wangyue_explicit_age_regex_hits(text),
        )
        if is_wangyue
        else []
    )
    wangyue_portable_form_hits = _hits_prefer_longer(text, WANGYUE_PORTABLE_FORM_PHRASES) if is_wangyue else []
    wangyue_digestive_effect_hits = _hits_prefer_longer(text, WANGYUE_DIGESTIVE_EFFECT_PHRASES) if is_wangyue else []
    wangyue_missing_product_mention = is_wangyue and not any(
        term in text for term in ("旺玥", "皇家美素佳儿")
    )
    wangyue_growth_nutrition_drift_hits = (
        _hits_prefer_longer(text, WANGYUE_GROWTH_NUTRITION_DRIFT_PHRASES)
        if _is_wangyue_growth_nutrition_plan(plan)
        else []
    )
    wangyue_article_logic_drift_hits = (
        _hits_prefer_longer(text, WANGYUE_ARTICLE_LOGIC_DRIFT_PHRASES) if is_wangyue else []
    )
    if _is_wangyue_row2_energy_plan(plan):
        wangyue_article_logic_drift_hits = _merge_hits(
            wangyue_article_logic_drift_hits,
            _hits_prefer_longer(text, WANGYUE_ROW2_EYE_BRAIN_DRIFT_PHRASES),
        )
    wangyue_row2_drinking_action_hits = (
        _merge_hits(
            _hits_prefer_longer(text, WANGYUE_ROW2_DRINKING_ACTION_DRIFT_PHRASES),
            _wangyue_row2_drinking_action_regex_hits(text),
        )
        if _is_wangyue_row2_energy_plan(plan)
        else []
    )
    temporal_context_hits = _hits_prefer_longer(text, TEMPORAL_CONTEXT_PHRASES)
    run_on_fragment_hits = _long_unpunctuated_segment_hits(body_text)
    malformed_fragment_hits = _malformed_fragment_hits(body_text)
    body_chars = _compact_len(body_text)
    length_target = _article_length_target(plan)

    reasons: list[str] = []
    if not body_text.strip():
        reasons.append("empty_body")
    if len(skeleton_parts) >= 3:
        reasons.append("complete_selection_price_acceptance_closure_skeleton")
    if _hits(text, HARD_AI_CLOSURE_PHRASES):
        reasons.append("hard_ai_closure_phrase")
    if _hits(text, COMMON_AI_CLOSURE_PHRASES):
        reasons.append("common_ai_closure_phrase")
    if _has_state_template_pattern(state_template_hits, ai_hits):
        reasons.append("state_template_phrase")
    if odd_phrase_hits:
        reasons.append("odd_product_experience_phrase")
    if hard_risk_hits:
        reasons.append("hard_risk_expression")
    if adult_self_drinking_hits:
        reasons.append("adult_self_drinking_child_formula")
    if child_self_brewing_hits:
        reasons.append("child_self_brewing_formula")
    if child_formula_bottle_hits:
        reasons.append("child_formula_bottle_context")
    if wangyue_wrong_brand_hits:
        reasons.append("wangyue_wrong_brand")
    if wangyue_explicit_age_hits:
        reasons.append("wangyue_explicit_age_context")
    if wangyue_portable_form_hits:
        reasons.append("wangyue_portable_form_context")
    if wangyue_digestive_effect_hits:
        reasons.append("wangyue_digestive_effect_context")
    if wangyue_missing_product_mention:
        reasons.append("wangyue_missing_product_mention")
    if wangyue_growth_nutrition_drift_hits:
        reasons.append("wangyue_growth_nutrition_drift_context")
    if wangyue_article_logic_drift_hits:
        reasons.append("wangyue_article_logic_drift_context")
    if wangyue_row2_drinking_action_hits:
        reasons.append("wangyue_row2_drinking_action_context")
    if temporal_context_hits:
        reasons.append("explicit_temporal_context")
    if run_on_fragment_hits:
        reasons.append("long_unpunctuated_body_segment")
    if malformed_fragment_hits:
        reasons.append("malformed_fragment")

    rewrite_required = bool(reasons)
    return ProductExperiencePhraseReview(
        pass_=not rewrite_required,
        rewrite_required=rewrite_required,
        reasons=reasons,
        skeleton_parts=skeleton_parts,
        skeleton_hits=skeleton_hits,
        ai_phrase_hits=ai_hits,
        state_template_hits=state_template_hits,
        odd_phrase_hits=odd_phrase_hits,
        strong_real_expression_hits=strong_real_hits,
        hard_risk_hits=hard_risk_hits,
        adult_self_drinking_hits=adult_self_drinking_hits,
        child_self_brewing_hits=child_self_brewing_hits,
        child_formula_bottle_hits=child_formula_bottle_hits,
        wangyue_wrong_brand_hits=wangyue_wrong_brand_hits,
        wangyue_explicit_age_hits=wangyue_explicit_age_hits,
        wangyue_portable_form_hits=wangyue_portable_form_hits,
        wangyue_digestive_effect_hits=wangyue_digestive_effect_hits,
        wangyue_growth_nutrition_drift_hits=wangyue_growth_nutrition_drift_hits,
        wangyue_article_logic_drift_hits=wangyue_article_logic_drift_hits,
        wangyue_row2_drinking_action_hits=wangyue_row2_drinking_action_hits,
        temporal_context_hits=temporal_context_hits,
        run_on_fragment_hits=run_on_fragment_hits,
        malformed_fragment_hits=malformed_fragment_hits,
        body_chars=body_chars,
        length_target=length_target,
    )


def sanitize_temporal_context(value: str | None) -> str:
    text = str(value or "")
    for source, replacement in TEMPORAL_CONTEXT_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = text.replace("最近这阵", "最近")
    text = text.replace("最近后", "最近")
    text = text.replace("这阵后", "这阵子")
    text = text.replace("这段时间后", "这段时间")
    text = text.replace("这阵这阵", "这阵")
    text = text.replace("这段时间这段时间", "这段时间")
    text = text.replace("这段时间段时间", "这段时间")
    text = text.replace("这段时间这阵", "这段时间")
    text = text.replace("上上学", "上学")
    text = text.replace("一最近", "一有状况")
    text = text.replace("一这阵", "一有状况")
    text = re.sub(r"[，,]\s*[，,]", "，", text)
    return text.strip(" ，,")


def sanitize_product_experience_format(value: str | None) -> str:
    text = str(value or "")
    text = re.sub(r"[\u200d\ufe0f]", "", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+)__", r"\1", text)
    text = re.sub(r"\s*[\r\n]+\s*", "，", text)
    text = text.replace("，。", "。")
    text = text.replace("。，", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = text.replace("我我", "我")
    return text.strip(" ，,。；;")


def sanitize_common_ai_closure(value: str | None) -> str:
    text = str(value or "")
    for source, replacement in COMMON_AI_CLOSURE_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = text.replace("，。", "。")
    text = text.replace("。，", "。")
    text = text.replace("，, ", "，")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = text.replace("，.", "。")
    text = text.replace("。,", "。")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，,。；;\s]*长势$", "", text)
    text = re.sub(r"^[，,。；;]+", "", text)
    return text.strip(" ，,。；;")


def sanitize_odd_product_experience_phrases(value: str | None) -> str:
    text = str(value or "")
    for source, replacement in ODD_PHRASE_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = text.replace("我会继续观察继续观察", "我会继续观察")
    text = text.replace("保护力、保护力和保护力", "保护力")
    text = text.replace("保护力、保护力", "保护力")
    text = text.replace("保护力和保护力", "保护力")
    text = text.replace("（）", "")
    text = text.replace("()", "")
    text = re.sub(r"[，,。；;\s]*(?:效果|先着吧|我这我算是|先|踏实)$", "", text)
    text = text.replace("，。", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"[\u200d\ufe0f]", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def sanitize_baby_milk_action_phrases(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return text

    text = text.replace("奶瓶一递过去", "奶杯一递过去")
    text = text.replace("抱着奶瓶", "抱着杯子")
    text = text.replace("看奶瓶", "看奶量")
    text = text.replace("奶瓶里", "杯子里")
    text = text.replace("奶瓶", "杯子")
    text = re.sub(r"[^。！？；;]*?(?:偷着干吃|干吃)[^。！？；;]*", "孩子这阵喝奶还算顺", text)
    text = text.replace("自己主动去泡奶了", "喝奶倒是主动了")
    text = text.replace("自己主动去泡奶", "喝奶倒是主动")
    text = text.replace("自己又跑去倒了半杯", "还想再喝半杯")
    text = text.replace("自己每天冲一杯", "每天等我冲一杯")
    text = text.replace("每天一杯自己冲", "每天一杯等我冲")
    text = text.replace("每天一杯自己泡", "每天一杯等我泡")
    text = text.replace("每天自己挖奶粉", "每天等我冲奶")
    text = text.replace("自己挖奶粉", "等我冲奶")
    text = text.replace("自己打开旺玥罐子", "等我打开旺玥罐子")
    text = text.replace("自己打开奶粉罐", "等我打开奶粉罐")
    text = text.replace("自己打开罐子", "等我打开罐子")
    text = text.replace("自己搬小凳子去拿奶粉罐", "等我冲奶")
    text = text.replace("自己搬小凳子去拿罐子", "等我冲奶")
    text = text.replace("自己跑去把旺玥罐子抱过来", "会提醒我冲奶")
    text = text.replace("自己跑去把奶粉罐抱过来", "会提醒我冲奶")
    text = text.replace("自己抱出奶粉罐", "提醒我冲奶")
    text = text.replace("自己抱出旺玥罐子", "提醒我冲奶")
    text = text.replace("自己抱出旺玥", "提醒我冲奶")
    text = text.replace("把旺玥罐子抱过来", "提醒我冲奶")
    text = text.replace("把奶粉罐抱过来", "提醒我冲奶")
    text = text.replace("伸手拽奶粉罐", "在旁边等我看奶粉罐")
    text = text.replace("一把抱怀里不撒手", "在旁边等着")
    text = text.replace("抱怀里不撒手", "在旁边等着")
    text = text.replace("被她翻出来当积木摆弄", "放在家里")
    text = text.replace("被他翻出来当积木摆弄", "放在家里")
    text = text.replace("被她翻出来当积木", "放在家里")
    text = text.replace("被他翻出来当积木", "放在家里")
    text = text.replace("当积木摆弄", "放在家里")
    text = text.replace("自己翻出奶粉罐", "提醒我冲奶")
    text = text.replace("自己翻出旺玥", "提醒我冲奶")
    text = text.replace("自己拆了条冲好", "等我冲好")
    text = text.replace("自己拆条冲好", "等我冲好")
    text = text.replace("自己拆了条", "等我冲好")
    text = text.replace("拆了条冲好", "冲好")
    text = text.replace("妈妈泡奶泡奶", "想喝奶")
    text = text.replace("每天自己倒着喝", "每天喝得挺顺")
    text = text.replace("自己倒着喝", "喝得挺顺")
    text = text.replace("自己倒来喝", "等我倒好再喝")
    text = text.replace("自己捧着旺玥罐子叫妈妈开", "会提醒我冲奶")
    text = text.replace("自己捧着奶粉罐子叫妈妈开", "会提醒我冲奶")
    text = text.replace("捧着旺玥罐子叫妈妈开", "提醒我冲奶")
    text = text.replace("捧着奶粉罐子叫妈妈开", "提醒我冲奶")
    text = text.replace("自己端着小碗蹲旁边等", "自己端着杯子在旁边等")
    text = text.replace("自己端着小碗", "自己端着杯子")
    text = text.replace("碗底舔干净", "杯底喝干净")

    text = text.replace("每天每天", "每天")
    text = text.replace("早上早上", "早上")
    text = text.replace("还会会提醒", "还会提醒")
    text = text.replace("，。", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def sanitize_adult_self_drinking_phrases(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return text

    text = text.replace("反正喝不完我自己也能当早餐奶", "反正先试一罐")
    text = text.replace("喝不完我自己也能当早餐奶", "先试一罐")
    text = text.replace("我自己也能当早餐奶", "先试一罐")
    text = text.replace("自己也能当早餐奶", "先试一罐")
    text = text.replace("给自己冲了一杯旺玥", "给孩子冲了一杯旺玥")
    text = text.replace("给自己冲一杯旺玥", "给孩子冲一杯旺玥")
    text = text.replace("自己冲了一杯旺玥", "给孩子冲了一杯旺玥")
    text = text.replace("自己冲一杯旺玥", "给孩子冲一杯旺玥")
    text = text.replace("给自己泡了一杯旺玥", "给孩子泡了一杯旺玥")
    text = text.replace("给自己泡一杯旺玥", "给孩子泡一杯旺玥")
    text = text.replace("我喝了一杯旺玥", "孩子喝了一杯旺玥")
    text = text.replace("我也喝旺玥", "孩子也喝旺玥")
    text = text.replace("我喝儿童奶粉", "孩子喝儿童奶粉")
    text = text.replace("我喝这罐奶粉", "孩子喝这罐奶粉")
    text = text.replace("我现在喝的是皇家美素佳儿旺玥", "给孩子选的是皇家美素佳儿旺玥")
    text = text.replace("我现在喝的是旺玥", "给孩子选的是旺玥")
    text = text.replace("我喝奶粉", "孩子喝奶粉")
    text = text.replace("我喝旺玥", "孩子喝旺玥")
    text = text.replace("妈妈自己喝旺玥", "孩子喝旺玥")
    text = text.replace("我自己喝着觉得挺香", "孩子喝着觉得挺香")
    text = text.replace("我自己喝了一口，还行", "孩子喝着还行")
    text = text.replace("我自己偷偷喝了一口", "孩子喝了一口")
    text = text.replace("自己偷偷喝了一口", "孩子喝了一口")
    text = text.replace("我自己喝了一口", "孩子喝了一口")
    text = text.replace("我先喝了一口", "先递给孩子喝")
    text = text.replace("我先喝一口", "先递给孩子喝")
    text = text.replace("泡了一杯自己先尝", "冲好后先递给孩子喝")
    text = text.replace("到手尝了口，不甜腻，", "")
    text = text.replace("到手尝了口，不甜腻", "")
    text = text.replace("到手尝了口", "")
    text = text.replace("尝了口，不甜腻，", "")
    text = text.replace("尝了口，不甜腻", "")
    text = text.replace("我自己偷偷尝过，确实不腥，", "")
    text = text.replace("我自己偷偷尝过，确实不腥", "")
    text = text.replace("我自己偷偷尝过", "")
    text = text.replace("自己偷偷尝过", "")
    text = text.replace("我自己尝了一口，", "")
    text = text.replace("我自己尝了一口", "")
    text = text.replace("自己尝了一口，", "")
    text = text.replace("自己尝了一口", "")
    text = text.replace("我自己尝过，", "")
    text = text.replace("我自己尝过", "")
    text = text.replace("自己尝过，", "")
    text = text.replace("自己尝过", "")
    text = text.replace("我自己尝了下，", "")
    text = text.replace("我自己尝了下", "")
    text = text.replace("自己尝了下，", "")
    text = text.replace("自己尝了下", "")
    text = text.replace("我自己喝着也觉得还行", "孩子喝着还行")
    text = text.replace("我自己喝着，", "")
    text = text.replace("我自己喝着", "")
    text = text.replace("我偷偷尝了一口，", "")
    text = text.replace("我偷偷尝了一口", "")
    text = text.replace("偷偷尝了一口，", "")
    text = text.replace("偷偷尝了一口", "")
    text = text.replace("偷偷尝过", "")
    text = text.replace("自己先尝了", "先递给孩子喝")
    text = text.replace("自己先尝", "先递给孩子喝")
    text = text.replace("我先偷喝了一口", "先递给孩子喝")
    text = text.replace("先偷喝了一口", "先递给孩子喝")
    text = text.replace("自己喝了一口", "孩子喝了一口")
    text = text.replace("自己先喝了一口", "先递给孩子喝")
    text = text.replace("偷喝她剩的一口底", "看她喝完杯底")
    text = text.replace("偷喝他剩的一口底", "看他喝完杯底")
    text = text.replace("偷喝剩的一口底", "看孩子喝完杯底")
    text = text.replace("我偷喝过半杯", "我闻过奶香味")
    text = text.replace("偷喝过半杯", "闻过奶香味")
    text = text.replace("先试一罐吧，先试一罐", "先试一罐吧")
    text = text.replace("先试一罐吧，反正先试一罐", "先试一罐吧")
    text = text.replace("，。", "。")
    text = text.replace("。，", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def sanitize_wangyue_context_phrases(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return text

    eye_brain_drift_pattern = (
        r"拼乐高|看绘本|翻绘本|绘本|写写画画|写字|画画|看书|小猪佩奇|手机平板|看视频|叶黄素|近视|"
        r"眼睛营养|眼睛发育|眼睛不酸了|眼睛不酸|揉眼睛|眼睛得跟上|眼睛也不能落下|脑子不够用|"
        r"脑子够不够用|脑子跟着转|脑子那块|脑子眼睛|大脑和眼睛"
    )
    product_name_pattern = r"(?:皇家美素佳儿旺玥|旺玥)"
    text = re.sub(
        rf"[^。！？；;]*?(?:{eye_brain_drift_pattern})[^。！？；;]*?(我(?:就)?给(?:他|她|孩子|娃)?选了?{product_name_pattern})",
        r"\1",
        text,
    )
    text = text.replace("我就给选了皇家美素佳儿旺玥", "我就给孩子选了皇家美素佳儿旺玥")
    text = text.replace("我给选了皇家美素佳儿旺玥", "我给孩子选了皇家美素佳儿旺玥")
    text = text.replace("我就给选了旺玥", "我就给孩子选了旺玥")
    text = text.replace("我给选了旺玥", "我给孩子选了旺玥")
    text = re.sub(
        rf"[^。！？；;]*?(?:{eye_brain_drift_pattern})[^。！？；;]*[。！？；;]?",
        "",
        text,
    )
    text = text.replace("源悦", "旺玥")
    text = text.replace("旺玥小安素", "旺玥儿童奶粉")
    text = text.replace("小安素", "儿童奶粉")
    text = text.replace("主要是看里面保护力这块", "主要是看皇家美素佳儿旺玥的保护力这块")
    text = text.replace("主要看里面保护力这块", "主要看皇家美素佳儿旺玥的保护力这块")
    text = text.replace("看里面保护力这块", "看皇家美素佳儿旺玥的保护力这块")
    text = text.replace("看里面营养全面", "看皇家美素佳儿旺玥营养全面")
    text = text.replace("给娃挑个口粮", "给娃挑奶粉")
    text = text.replace("给娃挑口粮", "给娃挑奶粉")
    text = text.replace("选口粮", "选奶粉")
    text = text.replace("娃的口粮", "孩子的奶粉")
    text = text.replace("孩子口粮", "孩子奶粉")
    text = text.replace("口粮", "奶粉")
    text = text.replace("放进购物车", "先记下来")
    text = text.replace("放购物车", "先记下来")
    text = text.replace("购物车", "备选里")
    text = text.replace("直接下单了", "最后选了它")
    text = text.replace("直接下单", "最后选了它")
    text = text.replace("下单了", "选下来了")
    text = text.replace("大路灯", "儿童奶粉")
    text = text.replace("护眼", "眼脑营养")
    text = text.replace("用眼过渡", "日常营养")
    text = text.replace("用眼过度", "日常营养")
    text = text.replace("眼睛都快冒星星", "活动量确实不小")
    text = text.replace("眼睛还亮亮", "状态还可以")
    text = text.replace("眼睛亮亮", "状态还可以")
    text = text.replace("眼睛不酸了", "状态还可以")
    text = text.replace("眼睛不酸", "状态还可以")
    text = text.replace("脸色都亮堂", "状态还可以")
    text = text.replace("脸色亮堂", "状态还可以")
    text = text.replace("冲出来奶香清淡，娃不挑", "选奶粉这事我记一下")
    text = text.replace("冲出来奶香清淡，", "")
    text = text.replace("冲出来奶香清淡", "")
    text = re.sub(
        r"[^。！？；;]*?(?:没怎么咳嗽|咳嗽|吭吭唧唧)[^。！？；;]*?(?:皇家美素佳儿旺玥|旺玥)[^。！？；;]*[。！？；;]?",
        "这段时间状态看着还行。",
        text,
    )
    text = re.sub(
        r"[^。！？；;]*?(?:没怎么咳嗽|咳嗽|吭吭唧唧)[^。！？；;]*[。！？；;]?",
        "这段时间状态看着还行。",
        text,
    )
    text = text.replace("换成了皇家美素佳儿旺玥", "后来留意到皇家美素佳儿旺玥")
    text = text.replace("换成了旺玥", "后来留意到旺玥")
    text = text.replace("给孩子选了皇家美素佳儿旺玥", "后来留意到皇家美素佳儿旺玥")
    text = text.replace("给他选了皇家美素佳儿旺玥", "后来留意到皇家美素佳儿旺玥")
    text = text.replace("给她选了皇家美素佳儿旺玥", "后来留意到皇家美素佳儿旺玥")
    text = text.replace("给孩子选了旺玥", "后来留意到旺玥")
    text = text.replace("给他选了旺玥", "后来留意到旺玥")
    text = text.replace("给她选了旺玥", "后来留意到旺玥")
    text = text.replace("给选了皇家美素佳儿旺玥", "后来留意到皇家美素佳儿旺玥")
    text = text.replace("给选了旺玥", "后来留意到旺玥")
    text = text.replace("小脑瓜", "状态")
    text = text.replace("用脑太多", "信息量太多")
    text = text.replace("脑子转得快", "反应挺快")
    text = re.sub(r"[^。！？；;，,]*?(?:开罐|冲泡|冲出来|奶香|粉质|不结块|煮粥)[^。！？；;]*[。！？；;]?", "", text)
    text = text.replace("从断奶开始", "孩子大点后")
    text = text.replace("两岁后", "孩子大点后")
    text = text.replace("2岁后", "孩子大点后")
    for phrase in WANGYUE_EXPLICIT_AGE_PHRASES:
        text = text.replace(phrase, "孩子")
    text = text.replace("孩子开始", "孩子大点开始")
    text = text.replace("孩子之后", "孩子大点之后")

    text = re.sub(
        r"(?:书包侧袋|书包侧兜|书包里|塞书包)[^。！？；;]*?(?:一盒旺玥|旺玥|奶粉盒|旺玥小条装)[^。！？；;]*",
        "家里那罐旺玥",
        text,
    )
    text = re.sub(
        r"塞[^。！？；;]*?(?:一罐旺玥|旺玥|奶粉)[^。！？；;]*?书包[^。！？；;]*",
        "家里那罐旺玥照常在喝",
        text,
    )
    text = text.replace("娃自己路上喝掉", "回家后照常喝完")
    text = text.replace("孩子自己路上喝掉", "回家后照常喝完")
    text = text.replace("自己路上喝掉", "回家后照常喝完")
    text = text.replace("路上喝掉", "回家后喝完")
    text = text.replace("路上喝", "在家喝")
    text = text.replace("书包有奶", "家里那款奶粉")
    text = text.replace("抱着奶粉罐", "看着奶粉罐")
    text = text.replace("抱着罐子", "看着罐子")
    text = text.replace("旺玥小条装", "旺玥奶粉")
    text = text.replace("便携装", "这罐奶粉")
    text = re.sub(
        r"出门[^。！？；;]*?(?:揣|带)[^。！？；;]*?(?:小袋|旺玥|奶粉)[^。！？；;]*?(?:直接冲|随时能泡|能泡)[^。！？；;]*",
        "日常喝旺玥这件事先照常安排",
        text,
    )
    text = text.replace("玩累了直接冲", "回家后照常喝")
    text = text.replace("直接冲", "照常喝")
    text = text.replace("揣两小袋", "家里备着")
    text = text.replace("两小袋", "一些")
    text = text.replace("小袋", "奶粉")
    text = text.replace("分装", "奶粉")
    text = text.replace("两条旺玥", "一杯旺玥")
    text = text.replace("两条", "一杯")
    text = text.replace("出门背的小双肩包", "家里的餐边柜")
    text = text.replace("小双肩包", "餐边柜")
    text = text.replace("外出随身包", "餐边柜")
    text = text.replace("随身包", "餐边柜")
    text = text.replace("包里除了水杯纸巾，还塞了旺玥", "家里那罐旺玥照常在喝")
    text = text.replace("包里除了水杯纸巾", "家里那罐旺玥")
    text = text.replace("包里除了水杯零食", "家里那罐旺玥")
    text = text.replace("出门恨不得把辅食机都塞包里", "有时会觉得营养安排挺琐碎")
    text = text.replace("辅食机都塞包里", "营养安排也跟着琐碎")
    text = text.replace("塞进背包", "放在家里")
    text = text.replace("背包里塞", "家里备着")
    text = text.replace("塞包里", "放在家里")
    text = text.replace("放一包皇家美素佳儿旺玥", "家里备着皇家美素佳儿旺玥")
    text = text.replace("放一包旺玥", "家里备着旺玥")
    text = text.replace("一包皇家美素佳儿旺玥", "一罐皇家美素佳儿旺玥")
    text = text.replace("一包旺玥", "一罐旺玥")
    text = text.replace("带娃出门，包里一定会塞一袋旺玥", "家里那罐旺玥一直在喝")
    text = text.replace("包里一定会塞一袋旺玥", "家里那罐旺玥一直在喝")
    text = text.replace("包里一定会塞", "家里一直备着")
    text = text.replace("塞一袋旺玥", "喝着旺玥")
    text = text.replace("出门前塞几包在包里，随时能泡", "家里备着，日常喝着")
    text = text.replace("塞几包在包里", "家里备着")
    text = text.replace("塞几包", "家里备着")
    text = text.replace("随时能泡", "日常喝着")
    text = text.replace("几包", "一些")
    text = text.replace("一袋旺玥", "一罐旺玥")
    text = text.replace("现在出门包里会多放一罐奶粉", "现在家里那罐奶粉照常喝")
    text = text.replace("出门包里会多放一罐奶粉", "家里那罐奶粉照常喝")
    text = text.replace("包里会多放一罐奶粉", "家里那罐奶粉照常喝")
    text = text.replace("多放一罐奶粉", "家里那罐奶粉")
    text = text.replace("包里光是奶粉和水壶就塞满了", "家里那罐奶粉照常喝着")
    text = text.replace("包里光是奶粉和水壶", "家里那罐奶粉")
    text = text.replace("我最烦一罐罐分开带", "我不想东补西补")
    text = text.replace("一罐全包", "日常营养补充省点事")
    text = text.replace("出门前顺手抓一罐", "家里那罐照常喝")
    text = text.replace("出门前顺手带一罐", "家里那罐照常喝")
    text = text.replace("顺手抓一罐", "选这一罐")
    text = text.replace("顺手带一罐", "家里那罐照常喝")
    text = text.replace("带一罐旺玥", "家里喝旺玥")
    text = text.replace("抓一罐", "选一罐")
    text = text.replace("出门包里", "家里")
    text = text.replace("出门太急忘了带旺玥", "出门太急漏了点小事")
    text = text.replace("忘了带旺玥", "漏了这杯奶")
    text = text.replace("忘带旺玥", "漏了这杯奶")
    text = text.replace("忘了带奶粉", "漏了这杯奶")
    text = text.replace("忘带奶粉", "漏了这杯奶")
    text = text.replace("带旺玥", "选旺玥")
    text = text.replace("带奶粉", "选奶粉")
    text = text.replace("塞了旺玥", "喝着旺玥")
    text = text.replace("奶粉条", "奶粉")
    text = text.replace("小条装", "奶粉")
    text = text.replace("水壶里都是这个", "在家喝这杯奶")
    text = text.replace("水壶里", "杯子里")
    text = re.sub(r"奶量从\s*\d+\s*ml\s*慢慢喝到\s*\d+\s*ml", "奶量慢慢上来", text, flags=re.IGNORECASE)
    text = re.sub(r"\d+\s*ml", "一杯", text, flags=re.IGNORECASE)
    text = text.replace("倒进奶粉袋", "放在家里")
    text = text.replace("奶粉袋", "奶粉罐")
    text = text.replace("带两小包冲奶刚好，", "在家冲好喝着顺，")
    text = text.replace("带两小包", "家里那罐")
    text = text.replace("两小包冲奶", "在家冲奶")
    text = text.replace("两小包", "一罐")
    text = text.replace("小包冲奶", "在家冲奶")
    text = text.replace("这小包", "这罐")
    text = text.replace("开盖即饮", "日常喝奶")
    text = text.replace("即饮", "日常喝奶")
    text = re.sub(r"干掉了[一二两三0-9]+根", "喝完一杯", text)
    text = text.replace("几袋", "一些")
    text = text.replace("塞奶粉盒兑点温水摇匀", "家里那罐旺玥照常冲好")
    text = text.replace("兑点温水摇匀", "照常冲好")
    text = text.replace("兑温水", "照常冲好")
    text = text.replace("当顺手的水喝下去", "照常喝下去")
    text = text.replace("当顺手的水喝", "照常喝")
    text = text.replace("水喝下去", "奶喝下去")
    text = text.replace("当水奶喝着", "照常喝着")
    text = text.replace("当水奶喝", "照常喝")
    text = text.replace("水奶", "奶粉")
    text = text.replace("当水喝", "照常喝")
    text = text.replace("旺玥我搁在茶几上", "旺玥这罐放在家里")
    text = text.replace("搁在茶几上", "放在家里")
    text = text.replace("放在茶几上", "放在家里")
    text = text.replace("他路过就喝几口", "他喝着还算顺")
    text = text.replace("她路过就喝几口", "她喝着还算顺")
    text = text.replace("路过就喝几口", "喝着还算顺")
    text = text.replace("一盒旺玥", "一罐旺玥")
    text = text.replace("奶粉盒", "奶粉罐")
    text = text.replace("不是胀气就是不爱喝", "喝奶一直不算顺")
    text = text.replace("肚子软软的，便便也规律了", "日常状态看着还顺")
    text = text.replace("肚子软软的，便便也规律", "日常状态看着还顺")
    text = text.replace("肚子软软的", "日常状态看着还顺")
    text = text.replace("便便也规律了", "日常状态还顺")
    text = text.replace("便便也规律", "日常状态还顺")
    text = text.replace("便便规律了", "日常状态还顺")
    text = text.replace("便便规律", "日常状态还顺")
    text = text.replace("没闹过肚肚", "喝着还算顺")
    text = text.replace("闹过肚肚", "不太适应")
    text = text.replace("闹肚子", "不太适应")
    text = text.replace("肚肚", "状态")
    text = text.replace("小肚子", "状态")
    text = text.replace("胀气", "不适应")
    text = text.replace("舌苔白", "不太适应")
    text = text.replace("舌苔", "状态")
    text = text.replace("肠胃", "喝奶")
    text = text.replace("脾胃", "喝奶")
    text = text.replace("消化", "接受度")

    text = text.replace("孩子孩子", "孩子")
    text = text.replace("，。", "。")
    text = text.replace("，，", "，")
    text = text.replace("。。", "。")
    text = re.sub(r"\s+", "", text)
    return text.strip(" ，,。；;")


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase and phrase in text]


def _hits_prefer_longer(text: str, phrases: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for phrase in sorted((phrase for phrase in phrases if phrase and phrase in text), key=len, reverse=True):
        if any(phrase in existing for existing in hits):
            continue
        hits.append(phrase)
    return hits


def _merge_hits(*groups: list[str]) -> list[str]:
    hits: list[str] = []
    for group in groups:
        for hit in group:
            if hit not in hits:
                hits.append(hit)
    return hits


def _hard_risk_hits(text: str) -> list[str]:
    hits = _hits(text, HARD_RISK_PHRASES)
    if "临时补救" not in hits:
        return hits
    if re.search(r"(?:不是|不算|别写成|不能当|不要当|不靠).{0,8}临时补救", text):
        return [hit for hit in hits if hit != "临时补救"]
    return hits


def _wangyue_row2_drinking_action_regex_hits(text: str) -> list[str]:
    patterns = (
        r"(?:每天|早晚)[^。！？；;]{0,10}(?:喝|冲|泡)[^。！？；;]{0,10}(?:旺玥|奶粉|儿童奶粉|奶)?",
        r"(?:放学|活动后|玩完|跑累|喊累|白天消耗)[^。！？；;]{0,16}(?:先喝|喝|补)[^。！？；;]{0,12}(?:一杯|旺玥|奶粉|儿童奶粉|奶|保护力|营养)",
        r"(?:回家|回家路上|回来)[^。！？；;]{0,12}(?:先喝|喝|补)[^。！？；;]{0,12}(?:一杯|旺玥|奶粉|儿童奶粉|奶|保护力|营养)",
        r"(?:回来|回家|活动量大|白天|折腾完|玩完)[^。！？；;]{0,18}(?:想喝点|当补充|补充营养|补充吧)",
        r"(?:家里|平时)[^。！？；;]{0,12}(?:放一罐|放着)[^。！？；;]{0,12}(?:旺玥|奶粉|儿童奶粉)",
        r"(?:包里|书包|随身)[^。！？；;]{0,16}(?:旺玥|奶粉|儿童奶粉|奶)",
        r"(?:翻出|翻出来|摸出)[^。！？；;]{0,12}(?:旺玥|奶粉|儿童奶粉|奶罐|罐子)",
        r"(?:家里|平时)[^。！？；;]{0,12}(?:备着|常备|备的|备了|囤)[^。！？；;]{0,14}(?:旺玥|奶粉|儿童奶粉)",
        r"(?:家里|放家里|平时)[^。！？；;]{0,12}(?:旺玥|奶粉|儿童奶粉)[^。！？；;]{0,12}(?:备着|常备|备的|备了|囤)",
        r"(?:多备了|备了|备着)[^。！？；;]{0,8}(?:旺玥|奶粉|儿童奶粉)",
        r"(?:旺玥|奶粉|儿童奶粉)[^。！？；;]{0,10}喝了(?:几个月|好几个月|一阵|段时间)",
        r"(?:递过去|递给他|递给她|把旺玥递过去)[^。！？；;]{0,12}(?:自己)?喝",
        r"(?:天天|每天|老是)?[^。！？；;]{0,8}追着补",
        r"(?:递|递了|直接递|给)[^。！？；;]{0,6}(?:一)?杯[^。！？；;]{0,6}(?:旺玥|奶粉|儿童奶粉|奶)",
        r"(?:冲|泡)[^。！？；;]{0,8}(?:一杯|一碗|旺玥|奶粉|儿童奶粉|奶)",
    )
    hits: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            hit = match.group(0).strip(" ，,。；;")
            if hit and hit not in hits:
                hits.append(hit)
    return hits


def _child_self_brewing_regex_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in CHILD_SELF_BREWING_PATTERNS:
        for match in pattern.finditer(text):
            hit = match.group(0)
            if hit not in hits:
                hits.append(hit)
    return hits


def _wangyue_explicit_age_regex_hits(text: str) -> list[str]:
    hits: list[str] = []
    age_token = r"(?:[1-9]\d?|[一二三四五六七八九十两])\s*[岁歲](?:多|半|后)?"
    patterns = (
        re.compile(rf"(?:宝宝|娃|孩子|小孩|男孩|女孩|儿子|女儿|闺女)?{age_token}(?:宝宝|娃|孩子|儿童)?"),
        re.compile(r"(?:几岁|幾歲)(?:宝宝|娃|孩子|儿童)?"),
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            hit = match.group(0).strip()
            if hit and hit not in hits:
                hits.append(hit)
    return hits


def _long_unpunctuated_segment_hits(text: str, *, threshold: int = 90) -> list[str]:
    hits: list[str] = []
    for segment in re.split(r"[，,。.!！？?；;\n\r]", str(text or "")):
        compact = re.sub(r"\s+", "", segment)
        if len(compact) >= threshold:
            hits.append(compact[:80])
    return hits


def _malformed_fragment_hits(text: str) -> list[str]:
    text = str(text or "")
    hits: list[str] = []
    if text.count("“") != text.count("”"):
        hits.append("中文引号不成对")
    if text.count("「") != text.count("」"):
        hits.append("中文引号不成对")
    if "中文引号不成对" in hits and re.search(r"[“「][^”」。！？；;]{18,}[。！？；;]", text):
        hits.append("半截对话")
    return hits


def _has_state_template_pattern(state_hits: list[str], ai_hits: list[str]) -> bool:
    if len(state_hits) >= 2:
        return True
    closure_hits = {"省心", "踏实", "安心"}
    return bool(state_hits and closure_hits.intersection(ai_hits))


def _is_wangyue_plan(plan: dict[str, Any]) -> bool:
    corpus = str(plan.get("corpus") or "")
    return str(plan.get("asset_key") or "").startswith("wangyue_") or "旺玥" in corpus


def _is_wangyue_growth_nutrition_plan(plan: dict[str, Any]) -> bool:
    if not _is_wangyue_plan(plan):
        return False
    row_no = plan.get("source_row_no")
    try:
        if row_no is not None and int(row_no) == 4:
            return True
    except (TypeError, ValueError):
        pass
    plan_text = "\n".join(
        str(plan.get(key) or "")
        for key in ("business_rule", "topic", "corpus", "rule_name")
    )
    return (
        "营养不足/成长发育需求" in plan_text
        or ("营养不足" in plan_text and "成长发育需求" in plan_text)
        or ("补充营养" in plan_text and "支持成长" in plan_text)
    )


def _is_wangyue_row2_energy_plan(plan: dict[str, Any]) -> bool:
    if not _is_wangyue_plan(plan):
        return False
    row_no = plan.get("source_row_no")
    try:
        if row_no is not None and int(row_no) == 2:
            return True
    except (TypeError, ValueError):
        pass
    plan_text = "\n".join(
        str(plan.get(key) or "")
        for key in ("business_rule", "topic", "corpus", "rule_name")
    )
    return "精力不足" in plan_text and "日常状态观察" in plan_text


def _compact_len(value: str | None) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _article_length_target(plan: dict[str, Any]) -> tuple[str, int, int] | None:
    corpus = str(plan.get("corpus") or "")
    explicit = re.search(r"正文\s*(\d{2,3})\s*[-~—到至]\s*(\d{2,3})\s*字", corpus)
    if explicit:
        min_chars, max_chars = int(explicit.group(1)), int(explicit.group(2))
        if min_chars < max_chars:
            return "自定义", min_chars, max_chars
    if "篇幅类型：中短文" in corpus:
        return "中短文", 120, 150
    if "篇幅类型：短文" in corpus:
        return "短文", 40, 80
    return None
