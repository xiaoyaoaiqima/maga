from typing import List, Optional, Dict, Any
from loguru import logger

from app.services.llm_factory import LLMFactory
from app.utils.model_config import build_llm_config


class RLHFExpertService:
    """RLHF 专家服务，提供 AI 总结标签、AI 总结意见等能力"""

    @staticmethod
    async def summarize_tags(
        annotations: List[Dict[str, Any]], 
        comment: Optional[str] = None,
        model_code: str = "gpt-4o"
    ) -> List[str]:
        """根据划词评论和人工意见，利用 AI 总结问题标签"""
        
        # 整理输入信息
        annotation_texts = []
        if annotations:
            for ann in annotations:
                selected_text = ann.get('selected_text', '')
                ann_comment = ann.get('comment', '')
                annotation_texts.append(f"- 选中文本: \"{selected_text}\", 评价: {ann_comment}")
        
        input_info = "\n".join(annotation_texts)
        if comment:
            input_info += f"\n- 总结意见: {comment}"
            
        if not input_info:
            return []

        # 调用 LLM（使用 LLMFactory.call_llm 以兼容无 SDK 环境）
        try:
            llm_config = build_llm_config(model_code, {})
            user_prompt = f"""你是一个专业的 AI 内容审核助手。请根据以下审核员的划词评论和总结意见，提取出 3-5 个简短的"问题标签"（每个标签 2-6 个字）。
标签应涵盖：逻辑错误、事实性问题、价值观倾向、格式问题、表达生硬等。

审核输入信息：
{input_info}

请仅返回标签列表，用逗号分隔，不要有任何其他解释。"""

            content = await LLMFactory.call_llm(
                config=llm_config,
                system_prompt="",
                user_prompt=user_prompt,
            )
            
            # 清理可能的 Markdown 格式或多余符号
            content = content.replace("，", ",").replace("、", ",")
            tags = [t.strip() for t in content.split(",") if t.strip()]
            logger.info(f"[RLHFExpert] AI 建议标签成功: {tags}")
            return tags[:10]  # 最多取 10 个
        except Exception as e:
            logger.error(f"[RLHFExpert] AI summarize tags failed: {e}")
            return []

    @staticmethod
    async def summarize_comment(
        original_content: str,
        annotations: List[Dict[str, Any]],
        refined_content: Optional[str] = None,
        model_code: str = "gpt-4o"
    ) -> str:
        """根据原文内容和划词评论/精修内容，利用 AI 生成修改意见/问题描述
        
        支持三种模式：
        1. 划词评论模式：基于 annotations 生成意见
        2. 精修内容模式：对比 original_content 和 refined_content 生成意见
        3. 综合模式：两者都有时，结合生成综合意见
        """
        
        # 判断是否有划词评论
        annotation_texts = []
        if annotations:
            for ann in annotations:
                selected_text = ann.get('selected_text', '')
                ann_comment = ann.get('comment', '')
                if selected_text and ann_comment:
                    annotation_texts.append(f"- 原文片段: 「{selected_text}」\n  评论: {ann_comment}")
        
        has_annotations = len(annotation_texts) > 0
        
        # 判断是否有精修内容（精修内容需要与原文不同才有意义）
        has_refined = (
            refined_content is not None 
            and refined_content.strip() 
            and refined_content.strip() != (original_content or "").strip()
        )
        
        # 如果两者都没有，返回空
        if not has_annotations and not has_refined:
            return ""
        
        # 截取原文（避免过长）
        content_preview = (original_content[:2000] if len(original_content or "") > 2000 
                          else original_content or "")
        
        # 根据不同场景构建 prompt
        try:
            llm_config = build_llm_config(model_code, {})
            
            if has_annotations and has_refined:
                # 综合模式：结合划词评论和精修内容
                annotations_str = "\n".join(annotation_texts)
                refined_preview = refined_content[:2000] if len(refined_content) > 2000 else refined_content
                
                user_prompt = f"""你是一个专业的内容审核助手。请根据以下信息，生成一段简洁的「修改意见/问题描述」。

【原文内容】
{content_preview}

【精修后内容】
{refined_preview}

【审核员划词评论】
{annotations_str}

请综合以上信息，生成一段 50-150 字的修改意见，要求：
1. 分析审核员划词评论指出的问题
2. 对比原文和精修内容，总结修改的核心改动
3. 给出后续改进建议（如有）
4. 语言简洁专业，使用中文

请直接输出修改意见内容，不要有任何标题或前缀。"""

            elif has_refined:
                # 精修内容模式：对比原文和精修内容
                refined_preview = refined_content[:2000] if len(refined_content) > 2000 else refined_content
                
                user_prompt = f"""你是一个专业的内容审核助手。请对比以下原文和精修后的内容，生成一段简洁的「修改意见/问题描述」。

【原文内容】
{content_preview}

【精修后内容】
{refined_preview}

请对比原文和精修后内容，生成一段 50-150 字的修改意见，要求：
1. 总结精修的核心改动点（如：修正了什么问题、优化了什么表达）
2. 说明为何这样修改更好
3. 如还有可改进之处，给出建议
4. 语言简洁专业，使用中文

请直接输出修改意见内容，不要有任何标题或前缀。"""

            else:
                # 划词评论模式（原有逻辑）
                annotations_str = "\n".join(annotation_texts)
                
                user_prompt = f"""你是一个专业的内容审核助手。请根据以下信息，生成一段简洁的「修改意见/问题描述」。

【原文内容】
{content_preview}

【审核员划词评论】
{annotations_str}

请综合以上评论，生成一段 50-150 字的修改意见，要求：
1. 概括主要问题点
2. 给出具体改进建议
3. 语言简洁专业，使用中文

请直接输出修改意见内容，不要有任何标题或前缀。"""

            result = await LLMFactory.call_llm(
                config=llm_config,
                system_prompt="",
                user_prompt=user_prompt,
            )
            
            result = result.strip()
            mode = "综合模式" if (has_annotations and has_refined) else ("精修对比" if has_refined else "划词评论")
            logger.info(f"[RLHFExpert] AI 总结意见成功 ({mode})，长度: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"[RLHFExpert] AI summarize comment failed: {e}")
            return ""
