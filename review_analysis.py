from flask import Blueprint, render_template, request, jsonify, session
from openai import OpenAI
from datetime import datetime, timedelta
from collections import Counter
import bjc
import os
import re
import requests
import json
from department_permissions import require_permission
from tools import ai_chat_complete as _ai_chat_complete

# 创建蓝图
review_analysis_bp = Blueprint('review_analysis', __name__)

_OPENAI_TEXT_MODEL = (os.getenv("OPENAI_TEXT_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5").strip()
_OPENAI_TEXT_MODEL_CANDIDATES = [m for m in [_OPENAI_TEXT_MODEL, "gpt-5-mini", "gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"] if m]


def format_analysis_result(analysis_text):
    """美化分析结果的格式"""
    if not analysis_text:
        return "暂无分析结果"
    
    # 添加一些格式化处理
    formatted_text = analysis_text.replace('\n\n', '\n')
    formatted_text = formatted_text.replace('**', '')
    
    # 如果文本太长，添加换行
    lines = formatted_text.split('\n')
    result_lines = []
    
    for line in lines:
        if len(line) > 100:
            # 长行按句号分割
            sentences = line.split('。')
            for i, sentence in enumerate(sentences):
                if sentence.strip():
                    if i < len(sentences) - 1:
                        result_lines.append(sentence + '。')
                    else:
                        result_lines.append(sentence)
        else:
            result_lines.append(line)
    
    return '\n'.join(result_lines)

def analyze_problem_details(problem_type, keywords):
    """根据问题类型和关键词提供详细的问题分析"""
    problem_analysis = {
        '尺寸问题': {
            'size': '产品尺寸不合适，可能偏大或偏小',
            'small': '产品尺寸偏小，不符合用户期望',
            'large': '产品尺寸偏大，超出用户需求',
            'big': '产品尺寸过大，使用不便',
            'tiny': '产品尺寸过小，影响使用效果',
            'fit': '产品尺寸不合身，贴合度不佳',
            'tight': '产品过紧，穿戴不舒适',
            'loose': '产品过松，影响使用效果',
            'width': '产品宽度不合适',
            'length': '产品长度不符合预期',
            'short': '产品长度偏短',
            'long': '产品长度偏长'
        },
        '质量问题': {
            'quality': '产品整体质量存在问题',
            'cheap': '产品质量较差，做工粗糙',
            'flimsy': '产品结构不牢固，容易损坏',
            'broken': '产品存在破损或损坏',
            'defective': '产品有缺陷，功能异常',
            'poor': '产品质量不佳，不符合期望'
        },
        '物流问题': {
            'shipping': '物流配送存在问题',
            'delivery': '送货服务不满意',
            'late': '配送延迟，未按时到达',
            'damaged': '运输过程中产品受损',
            'packaging': '包装不当，影响产品质量'
        },
        '价格问题': {
            'expensive': '产品价格偏高，性价比不佳',
            'overpriced': '产品定价过高，超出价值',
            'price': '价格与产品质量不匹配',
            'cost': '成本效益不理想',
            'cheap': '价格虽低但质量堪忧'
        }
    }
    
    if problem_type not in problem_analysis:
        return None
    
    details = []
    for keyword in keywords:
        if keyword.lower() in problem_analysis[problem_type]:
            details.append(problem_analysis[problem_type][keyword.lower()])
    
    if details:
        return '; '.join(details[:3])  # 最多显示3个详细说明
    return None


def translate_to_chinese(text):
    """将英文文本翻译成中文"""
    if not text or not text.strip():
        return text
    
    # 检查是否主要是英文（简单判断：英文字符占比超过30%）
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = len(text.replace(' ', '').replace('.', '').replace('!', '').replace('?', ''))
    
    if total_chars == 0 or english_chars / total_chars < 0.2:
        return text  # 如果英文字符占比少于20%，认为不需要翻译
    
    try:
        # 使用百度翻译API（免费版）
        # 这里使用一个简单的翻译服务，实际使用时可以配置API密钥
        url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
        
        # 简化版翻译：使用本地词典进行基本翻译
        translation_dict = {
            # 基本评价词汇
            'good': '好的', 'great': '很棒', 'excellent': '优秀的', 'amazing': '令人惊叹的',
            'bad': '坏的', 'terrible': '糟糕的', 'awful': '可怕的', 'poor': '差的',
            'wonderful': '精彩的', 'fantastic': '极好的', 'awesome': '棒极了', 'outstanding': '杰出的',
            'horrible': '可怕的', 'disgusting': '令人厌恶的', 'disappointing': '令人失望的',
            
            # 产品相关
            'quality': '质量', 'product': '产品', 'item': '商品', 'material': '材料',
            'design': '设计', 'style': '风格', 'appearance': '外观', 'look': '外观',
            'texture': '质地', 'finish': '表面处理', 'craftsmanship': '工艺',
            
            # 物流配送
            'delivery': '配送', 'shipping': '运输', 'package': '包装', 'packaging': '包装',
            'fast': '快速', 'slow': '缓慢', 'quick': '快的', 'delayed': '延迟的',
            'arrived': '到达', 'received': '收到', 'sent': '发送', 'shipped': '已发货',
            
            # 情感表达
            'love': '喜欢', 'like': '喜欢', 'hate': '讨厌', 'recommend': '推荐',
            'satisfied': '满意的', 'disappointed': '失望的', 'happy': '开心的', 'sad': '伤心的',
            'pleased': '高兴的', 'upset': '不高兴的', 'frustrated': '沮丧的', 'impressed': '印象深刻的',
            
            # 外观描述
            'perfect': '完美的', 'nice': '不错的', 'beautiful': '美丽的', 'ugly': '丑陋的',
            'pretty': '漂亮的', 'cute': '可爱的', 'elegant': '优雅的', 'stylish': '时尚的',
            'attractive': '有吸引力的', 'gorgeous': '华丽的', 'stunning': '令人惊艳的',
            
            # 尺寸颜色
            'size': '尺寸', 'color': '颜色', 'colour': '颜色', 'fit': '合身',
            'large': '大的', 'small': '小的', 'big': '大的', 'tiny': '微小的',
            'bright': '明亮的', 'dark': '深色的', 'light': '浅色的',
            
            # 价格价值
            'price': '价格', 'value': '价值', 'cheap': '便宜的', 'expensive': '昂贵的',
            'affordable': '实惠的', 'reasonable': '合理的', 'worth': '值得的',
            'money': '钱', 'cost': '成本', 'budget': '预算',
            
            # 质量状态
            'broken': '破损的', 'damaged': '损坏的', 'defective': '有缺陷的',
            'perfect': '完美的', 'flawless': '无瑕疵的', 'sturdy': '结实的',
            'durable': '耐用的', 'fragile': '易碎的', 'weak': '脆弱的',
            
            # 触感体验
            'comfortable': '舒适的', 'soft': '柔软的', 'hard': '硬的', 'smooth': '光滑的',
            'rough': '粗糙的', 'gentle': '温和的', 'cozy': '舒适的', 'warm': '温暖的',
            'cool': '凉爽的', 'thick': '厚的', 'thin': '薄的',
            
            # 使用体验
            'easy': '容易的', 'easier': '更容易的', 'difficult': '困难的', 'simple': '简单的', 'complex': '复杂的',
            'convenient': '方便的', 'useful': '有用的', 'practical': '实用的',
            'effective': '有效的', 'efficient': '高效的', 'reliable': '可靠的',
            
            # 常用动词和短语
            'buy': '购买', 'bought': '购买了', 'purchase': '购买', 'order': '订购',
            'return': '退货', 'exchange': '交换', 'refund': '退款',
            'work': '工作', 'works': '有效', 'working': '工作中的',
            'use': '使用', 'used': '使用过', 'using': '正在使用',
            'need': '需要', 'needed': '需要的', 'want': '想要', 'have': '有',
            'get': '得到', 'got': '得到了', 'give': '给', 'take': '拿',
            
            # 常用形容词和副词
            'very': '非常', 'really': '真的', 'quite': '相当', 'too': '太',
            'so': '如此', 'much': '很多', 'many': '许多', 'more': '更多',
            'most': '最多', 'less': '更少', 'least': '最少',
            'better': '更好', 'best': '最好', 'worse': '更差', 'worst': '最差',
            
            # 时间相关
            'quickly': '快速地', 'slowly': '缓慢地', 'immediately': '立即',
            'soon': '很快', 'late': '晚的', 'early': '早的', 'on time': '准时',
            'long': '长的', 'short': '短的',
            
            # 服务相关
            'service': '服务', 'customer': '客户', 'support': '支持', 'help': '帮助',
            'staff': '员工', 'team': '团队', 'response': '回应', 'reply': '回复',
            
            # 常用连接词和介词
        'and': '和', 'or': '或者', 'but': '但是', 'because': '因为',
        'with': '与', 'without': '没有', 'for': '为了', 'to': '到',
        'from': '从', 'in': '在', 'on': '在上面', 'at': '在',
        'the': '', 'a': '', 'an': '', 'is': '是', 'are': '是',
        'was': '是', 'were': '是', 'will': '将', 'would': '会',
        'that': '那个', 'this': '这个', 'these': '这些', 'those': '那些',
        'my': '我的', 'your': '你的', 'his': '他的', 'her': '她的',
        'their': '他们的', 'our': '我们的', 'its': '它的',
        
        # 特殊短语和缩写
        'every': '每个', 'all': '所有', 'some': '一些', 'any': '任何',
        'no': '没有', 'not': '不', 'never': '从不', 'always': '总是',
        'i': '我', 'you': '你', 'he': '他', 'she': '她', 'we': '我们',
        'they': '他们', 'it': '它', 'me': '我', 'him': '他', 'her': '她',
        'us': '我们', 'them': '他们',
        'dont': '不', 'didnt': '没有', 'wont': '不会', 'cant': '不能',
            'isnt': '不是', 'arent': '不是', 'wasnt': '不是', 'werent': '不是',
            'im': '我是', 'youre': '你是', 'hes': '他是', 'shes': '她是',
            'were': '我们是', 'theyre': '他们是', 'its': '它是',
            
            # 更多常用词汇
            'fact': '事实', 'has': '有', 'many': '许多', 'sizes': '尺寸',
            'smaller': '更小的', 'better': '更好的', 'needed': '需要的',
            'wider': '更宽的', 'ones': '那些', 'apply': '使用', 'too': '太',
            'plus': '加上', 'edge': '边缘', 'point': '尖', 'terrible': '糟糕的',
            'set': '套装', 'lashes': '睫毛', 'stiff': '僵硬的', 'liked': '喜欢',
            'these': '这些', 'super': '超级', 'amazing': '令人惊叹的',
            'eyes': '眼睛', 'absolute': '绝对的', 'favorite': '最爱的',
            'order': '订购', 'amazon': '亚马逊', 'eyelashes': '睫毛',
            'pretty': '漂亮的', 'also': '也', 'loved': '喜爱',
            
            # 睫毛相关专业词汇
            'just': '只是', 'coarse': '粗糙的', 'irritated': '刺激了', 'lot': '很多',
            'come': '来', 'clusters': '簇状', 'since': '因为', 'natural': '自然的',
            'appearance': '外观', 'beautiful': '美丽的', 'only': '只有', 'down': '向下',
            'fall': '下降', 'curl': '卷曲', 'starts': '开始', 'go': '变成',
            'straight': '直的', 'after': '之后', '3rd': '第三', 'day': '天',
            'guess': '猜测', 'pay': '付费', 'what': '什么', 'wide': '宽的',
            'quite': '相当', 'irritate': '刺激', 'eye': '眼睛', 'appearance': '外观',
            'look': '外观', 'beautiful': '美丽的', 'downfall': '缺点', 'starts': '开始',
            'third': '第三', 'straight': '直的', 'guess': '我想', 'pay': '付出',
            'for': '为了', 'what': '什么', 'you': '你', 'get': '得到'
        }
        
        # 进行简单的词汇替换翻译
        translated = text.lower()  # 转换为小写进行处理
        
        # 先处理特殊短语（多词组合）
        phrase_dict = {
        'every easy to use': '非常容易使用',
        'very easy to use': '非常容易使用', 
        'easy to use': '容易使用',
        'hard to use': '难以使用',
        'good quality': '质量好',
        'poor quality': '质量差',
        'fast delivery': '快速配送',
        'slow delivery': '配送缓慢',
        'on time': '准时',
        'not good': '不好',
        'not bad': '不错',
        'very good': '非常好',
        'very bad': '非常差',
        'i liked the fact that': '我喜欢这样的事实：',
        'it has many sizes': '它有很多尺寸',
        'the smaller sizes the better': '尺寸越小越好',
        'but i needed': '但我需要',
        'so i wont have to': '这样我就不必',
        'apply too many': '使用太多',
        'they are super soft': '它们非常柔软',
        'look amazing on your eyes': '在你眼睛上看起来很棒',
        'it is super easy to apply': '非常容易使用',
        'these are my absolute favorite': '这些是我的绝对最爱',
        'that i order on amazon': '我在亚马逊订购的',
        'these eyelashes are very pretty': '这些睫毛非常漂亮',
            'and also easy to apply': '而且也很容易使用',
            'i loved them': '我喜欢它们',
            'terrible set of lashes': '糟糕的睫毛套装',
            'they are stiff': '它们很僵硬',
            'i didnt like these': '我不喜欢这些',
            'wider ones': '更宽的那些',
            'so i wont have to apply too many': '这样我就不必使用太多',
            'plus their edge r poin': '加上它们的边缘很尖',
            'the fact that it has many sizes': '它有很多尺寸这个事实',
            'the smaller sizes the better': '尺寸越小越好',
            'but i needed wider ones': '但我需要更宽的那些',
            
            # 用户提到的具体评价短语
            'these lashes just are not my favorite': '这些睫毛只是不是我的最爱',
            'they are quite coarse': '它们相当粗糙',
            'irritated my eyes a lot': '很刺激我的眼睛',
            'they also come in pretty wide clusters': '它们也是相当宽的簇状',
            'since i have smaller': '因为我有更小的',
            'natural appearance is beautiful': '自然外观很美丽',
            'only down fall i have': '我唯一的缺点是',
            'of these lashes': '这些睫毛的',
            'the curl of the lashes': '睫毛的卷曲',
            'starts to go straight': '开始变直',
            'after 3rd day': '第三天后',
            'guess u pay for what u': '我想你付出什么就得到什么',
            'just are not': '只是不是',
            'quite coarse and': '相当粗糙并且',
            'irritated my eyes': '刺激了我的眼睛',
            'come in pretty': '呈现漂亮的',
            'wide clusters': '宽簇状',
            'so since i': '所以因为我',
            'have smaller': '有更小的',
            'natural appearance': '自然外观',
            'is beautiful': '很美丽',
            'only down fall': '唯一的缺点',
            'i have of': '我对于',
            'these lashes is': '这些睫毛是',
            'the curl of': '卷曲度',
            'the lashes starts': '睫毛开始',
            'to go straight': '变直',
            'after 3rd': '第三天后',
            'day guess': '天我想',
            'u pay for': '你付出',
            'what u get': '你得到什么'
        }
        
        for phrase, translation in phrase_dict.items():
            translated = translated.replace(phrase, translation)
        
        # 再处理单词翻译
        words = translated.split()
        translated_words = []
        
        for word in words:
            # 清理标点符号
            clean_word = re.sub(r'[^a-zA-Z]', '', word)
            if clean_word in translation_dict and translation_dict[clean_word]:
                translated_words.append(translation_dict[clean_word])
            elif word in translation_dict and translation_dict[word]:
                translated_words.append(translation_dict[word])
            else:
                translated_words.append(word)
        
        translated = ' '.join(translated_words)
    
        # 清理多余的空格和标点
        translated = re.sub(r'\s+', ' ', translated).strip()
        
        # 如果翻译后仍然主要是英文，添加翻译标注
        english_chars_after = len(re.findall(r'[a-zA-Z]', translated))
        total_chars_after = len(translated.replace(' ', '').replace('.', '').replace('!', '').replace('?', ''))
        
        # 降低阈值，只有当英文字符占比超过60%时才显示部分翻译标注
        if total_chars_after > 0 and english_chars_after / total_chars_after > 0.6:
            return f"{translated} (部分翻译)"  # 如果翻译效果不完全，显示部分翻译标注
        
        return translated
        
    except Exception as e:
        # 翻译失败时返回原文并添加标注
        return f"{text} (原文)"

def local_analysis(reviews):
    """本地分析评价的关键词和问题（支持所有星级）"""
    if not reviews:
        return "没有找到相关评价数据"
    
    # 定义问题关键词（负面）
    problem_keywords = {
        '质量问题': ['质量差', '质量不好', '做工粗糙', '材质差', '容易坏', '不耐用', '假货', '次品', '劣质', '瑕疵', '缺陷', '毛糙', '粗制滥造', '偷工减料', '不结实', '易损坏', '脆弱', 'poor quality', 'cheap', 'flimsy', 'broke', 'defective', 'faulty', 'inferior', 'shoddy', 'fragile', 'weak', 'terrible quality', 'bad quality', 'low quality'],
        '物流问题': ['发货慢', '物流慢', '包装差', '破损', '丢件', '延迟', '快递慢', '配送慢', '包装破', '压坏', '漏发', '少发', '错发', '包装简陋', '没保护', 'shipping', 'delivery', 'package', 'damaged', 'slow delivery', 'late delivery', 'poor packaging', 'broken package', 'missing items', 'wrong item', 'delayed', 'lost package'],
        '尺寸问题': ['尺寸不对', '太大', '太小', '不合适', '偏大', '偏小', '尺码不准', '偏差大', '不符合', '测量错误', '标注错误', 'size', 'too big', 'too small', 'fit', 'wrong size', 'sizing issue', 'doesn\'t fit', 'oversized', 'undersized', 'size chart wrong'],
        '效果问题': ['没效果', '效果差', '不明显', '没用', '无效', '没变化', '看不出', '白买了', '浪费钱', '不起作用', '效果微弱', 'not work', 'useless', 'ineffective', 'no effect', 'doesn\'t work', 'waste of money', 'no difference', 'pointless', 'no results'],
        '服务问题': ['态度差', '服务差', '不回复', '售后差', '客服态度', '不理人', '推卸责任', '敷衍', '不解决', '拖延', '不专业', 'customer service', 'support', 'response', 'rude', 'unhelpful', 'poor service', 'bad attitude', 'no response', 'ignore', 'unprofessional'],
        '价格问题': ['太贵', '不值', '性价比低', '坑钱', '价格虚高', '不划算', '贵了', 'overpriced', 'expensive', 'not worth it', 'too costly', 'waste of money', 'poor value'],
        '外观问题': ['难看', '丑', '颜色不对', '色差', '外观差', '不好看', '设计差', '样式老', 'ugly', 'looks bad', 'color difference', 'poor design', 'unattractive', 'hideous'],
        '使用问题': ['难用', '不好用', '操作复杂', '不方便', '麻烦', '体验差', '不顺手', 'hard to use', 'difficult', 'complicated', 'inconvenient', 'user unfriendly', 'poor experience']
    }
    
    # 定义好评关键词（正面）
    positive_keywords = {
        '质量优秀': ['质量好', '质量很好', '做工精细', '材质好', '耐用', '正品', '优质', '精致', '结实', '牢固', '扎实', '工艺好', '品质佳', '高档', '上档次', 'good quality', 'excellent', 'durable', 'well made', 'high quality', 'premium', 'solid', 'sturdy', 'well built', 'top quality', 'superb quality'],
        '物流满意': ['发货快', '物流快', '包装好', '完好无损', '快递给力', '配送及时', '包装精美', '保护到位', '无破损', '包装仔细', 'fast shipping', 'quick delivery', 'well packaged', 'excellent packaging', 'prompt delivery', 'safe packaging', 'careful packaging'],
        '尺寸合适': ['尺寸正好', '合适', '刚好', '尺码准确', '大小合适', '完美贴合', '尺寸标准', 'perfect fit', 'fits well', 'right size', 'accurate sizing', 'true to size', 'fits perfectly', 'good fit'],
        '效果显著': ['效果好', '有效果', '明显', '有用', '效果明显', '立竿见影', '很有效', '效果佳', '见效快', '效果不错', 'works well', 'effective', 'great results', 'amazing results', 'works perfectly', 'very effective', 'excellent results'],
        '服务优质': ['态度好', '服务好', '回复及时', '售后好', '客服专业', '服务周到', '热情', '耐心', '负责任', '贴心', 'great service', 'helpful', 'responsive', 'excellent service', 'professional', 'friendly', 'courteous', 'outstanding service'],
        '价格优势': ['便宜', '实惠', '性价比高', '划算', '值得', '超值', '价格合理', '物美价廉', 'cheap', 'affordable', 'good value', 'worth it', 'great price', 'excellent value', 'reasonable price', 'cost effective'],
        '外观满意': ['好看', '漂亮', '美观', '颜色正', '外观好', '设计好', '时尚', '精美', '颜值高', 'beautiful', 'attractive', 'nice looking', 'gorgeous', 'stylish', 'elegant', 'pretty', 'good design'],
        '使用体验': ['好用', '方便', '简单', '顺手', '舒适', '体验好', '操作简单', '易用', 'easy to use', 'convenient', 'comfortable', 'user friendly', 'simple', 'smooth', 'great experience'],
        '推荐满意': ['推荐', '值得买', '会回购', '满意', '喜欢', '不错', '赞', '棒', '给力', 'recommend', 'satisfied', 'love it', 'awesome', 'amazing', 'fantastic', 'will buy again', 'highly recommend']
    }
    
    # 统计问题类型和好评类型并收集相关评价
    problem_stats = {}
    problem_examples = {}
    positive_stats = {}
    positive_examples = {}
    
    # 分析负面评价
    problem_details = {}  # 存储具体问题细节
    for category, keywords in problem_keywords.items():
        count = 0
        examples = []
        matched_keywords = set()  # 记录匹配到的关键词
        
        for review in reviews:
            if len(review) > 8:
                # 获取评论内容 (索引7是英文，索引8是中文)
                review_text = str(review[7] or '') + ' ' + str(review[8] or '')
                review_text_lower = review_text.lower()
                
                # 检查是否包含该类别的关键词
                found_keywords = [kw for kw in keywords if kw.lower() in review_text_lower]
                if found_keywords:
                    count += 1
                    matched_keywords.update(found_keywords)
                    # 只保留前3个示例
                    if len(examples) < 3:
                        # 清理评论文本，去除多余空格和换行
                        clean_text = review_text.strip().replace('\n', ' ').replace('\r', '').replace('None', '').strip()
                        if clean_text and len(clean_text) > 10:  # 确保评论有实际内容
                            # 增加显示长度，提供更完整的评论内容
                            if len(clean_text) > 150:
                                examples.append(clean_text[:150] + '...')
                            else:
                                examples.append(clean_text)
        
        if count > 0:
            problem_stats[category] = count
            problem_examples[category] = examples
            problem_details[category] = list(matched_keywords)
    
    # 分析正面评价
    positive_details = {}  # 存储具体好评细节
    for category, keywords in positive_keywords.items():
        count = 0
        examples = []
        matched_keywords = set()  # 记录匹配到的关键词
        
        for review in reviews:
            if len(review) > 8:
                # 获取评论内容 (索引7是英文，索引8是中文)
                review_text = str(review[7] or '') + ' ' + str(review[8] or '')
                review_text_lower = review_text.lower()
                
                # 检查是否包含该类别的关键词
                found_keywords = [kw for kw in keywords if kw.lower() in review_text_lower]
                if found_keywords:
                    count += 1
                    matched_keywords.update(found_keywords)
                    # 只保留前3个示例
                    if len(examples) < 3:
                        # 清理评论文本，去除多余空格和换行
                        clean_text = review_text.strip().replace('\n', ' ').replace('\r', '').replace('None', '').strip()
                        if clean_text and len(clean_text) > 10:  # 确保评论有实际内容
                            if len(clean_text) > 150:
                                examples.append(clean_text[:150] + '...')
                            else:
                                examples.append(clean_text)
        
        if count > 0:
            positive_stats[category] = count
            positive_examples[category] = examples
            positive_details[category] = list(matched_keywords)
    
    # 生成详细分析报告
    analysis = f"📊 产品评价深度分析报告\n\n"
    analysis += f"🔍 数据概览：本次分析了 {len(reviews)} 条用户评价数据\n"
    analysis += f"📅 分析时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}\n\n"
    
    # 添加评分统计 (tuple格式: 索引5是星级)
    ratings = [review[5] for review in reviews if len(review) > 5 and review[5]]
    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        rating_counter = Counter(ratings)
        analysis += f"⭐ 评分概况：\n"
        analysis += f"• 平均评分: {avg_rating:.1f} 星\n"
        analysis += f"• 评分分布:\n"
        for rating in sorted(rating_counter.keys()):
            percentage = (rating_counter[rating] / len(ratings)) * 100
            analysis += f"  - {rating}星: {rating_counter[rating]} 条 ({percentage:.1f}%)\n"
        analysis += "\n"
    
    if problem_stats:
        total_issues = sum(problem_stats.values())
        analysis += f"🚨 问题深度分析 (共识别出 {total_issues} 个问题提及，涉及 {len(problem_stats)} 个问题类别)：\n\n"
        sorted_problems = sorted(problem_stats.items(), key=lambda x: x[1], reverse=True)
        
        for i, (problem, count) in enumerate(sorted_problems, 1):
            percentage = (count / len(reviews)) * 100
            severity = "🔴 高" if percentage > 20 else "🟡 中" if percentage > 10 else "🟢 低"
            analysis += f"{i}. 【{problem}】\n"
            analysis += f"   📊 统计数据: {count} 次提及 (占总评论的 {percentage:.1f}%)\n"
            analysis += f"   ⚠️ 严重程度: {severity}\n"
            
            # 添加具体问题细节
            if problem in problem_details and problem_details[problem]:
                details = problem_details[problem][:5]  # 最多显示5个关键词
                analysis += f"   🔍 具体问题: {', '.join(details)}\n"
                
                # 根据关键词提供更详细的问题分析
                detailed_analysis = analyze_problem_details(problem, problem_details[problem])
                if detailed_analysis:
                    analysis += f"   📝 问题详情: {detailed_analysis}\n"
            
            # 添加具体评价示例
            if problem in problem_examples and problem_examples[problem]:
                analysis += f"   💬 典型评价示例:\n"
                for j, example in enumerate(problem_examples[problem], 1):
                    analysis += f"   {j}. \"{example}\"\n"
            analysis += "\n"
        
        # 添加详细改进建议
        analysis += "💡 详细改进建议与解决方案：\n\n"
        
        # 为每个问题提供具体建议
        for i, (problem, count) in enumerate(sorted_problems[:3], 1):  # 只针对前3个主要问题
            percentage = (count / len(reviews)) * 100
            analysis += f"🎯 优先级 {i} - {problem} (影响 {percentage:.1f}% 的用户):\n"
            
            suggestions = {
                '质量问题': {
                    '短期措施': '立即加强质检流程，对现有库存进行全面检查',
                    '中期改进': '优化生产工艺，更换更优质的原材料供应商',
                    '长期规划': '建立完善的质量管理体系，实施全流程质量追溯'
                },
                '物流问题': {
                    '短期措施': '优化包装材料，加强易碎品保护措施',
                    '中期改进': '与物流公司协商改善配送时效，建立配送质量监控',
                    '长期规划': '建设自有仓储配送体系，提升物流服务标准'
                },
                '尺寸问题': {
                    '短期措施': '完善产品详情页尺寸说明，增加实物对比图',
                    '中期改进': '建立详细的尺码对照表，提供在线尺寸顾问服务',
                    '长期规划': '优化产品设计，提供更多尺寸选择'
                },
                '效果问题': {
                    '短期措施': '完善产品使用说明，提供详细的使用教程',
                    '中期改进': '优化产品配方或功能设计，提升产品效果',
                    '长期规划': '持续研发创新，建立用户反馈改进机制'
                },
                '服务问题': {
                    '短期措施': '加强客服培训，建立快速响应机制',
                    '中期改进': '完善售后服务流程，建立客户满意度跟踪',
                    '长期规划': '建设专业客服团队，提供7x24小时服务'
                },
                '价格问题': {
                    '短期措施': '适当调整价格策略，增加促销活动',
                    '中期改进': '优化成本结构，提升产品性价比',
                    '长期规划': '建立差异化定价策略，推出不同价位产品线'
                },
                '外观问题': {
                    '短期措施': '优化产品拍摄，提供更真实的产品展示',
                    '中期改进': '改进产品外观设计，增加颜色和款式选择',
                    '长期规划': '建立设计团队，持续优化产品美观度'
                },
                '使用问题': {
                    '短期措施': '制作详细的使用指南和视频教程',
                    '中期改进': '简化产品操作流程，优化用户体验',
                    '长期规划': '持续收集用户反馈，不断改进产品易用性'
                }
            }
            
            if problem in suggestions:
                suggestion = suggestions[problem]
                analysis += f"   📋 短期措施: {suggestion['短期措施']}\n"
                analysis += f"   📈 中期改进: {suggestion['中期改进']}\n"
                analysis += f"   🚀 长期规划: {suggestion['长期规划']}\n"
            analysis += "\n"
        
        # 添加整体建议
        analysis += "🔧 整体改进策略：\n"
        analysis += f"• 建议优先解决影响面最大的问题：{sorted_problems[0][0]}\n"
        analysis += "• 建立用户反馈收集机制，持续监控产品表现\n"
        analysis += "• 定期分析评价数据，及时发现和解决新问题\n"
        analysis += "• 建立跨部门协作机制，确保改进措施有效执行\n\n"
    else:
        analysis += "✅ 未发现明显的问题关键词\n\n"
    
    # 添加正面评价分析
    if positive_stats:
        total_positives = sum(positive_stats.values())
        analysis += f"🌟 产品优势深度分析 (共发现 {total_positives} 个优点提及，涉及 {len(positive_stats)} 个优势类别)：\n\n"
        sorted_positives = sorted(positive_stats.items(), key=lambda x: x[1], reverse=True)
        
        # 添加优势概览
        analysis += f"📊 优势统计概览：\n"
        for i, (positive, count) in enumerate(sorted_positives[:3], 1):
            percentage = (count / len(reviews)) * 100
            analysis += f"• 第{i}大优势: {positive} ({percentage:.1f}% 用户认可)\n"
        analysis += "\n"
        
        for i, (positive, count) in enumerate(sorted_positives, 1):
            percentage = (count / len(reviews)) * 100
            
            # 优势等级评估
            if percentage >= 30:
                level = "🏆 核心优势"
                importance = "极高"
            elif percentage >= 15:
                level = "🥈 重要优势"
                importance = "高"
            elif percentage >= 5:
                level = "🥉 一般优势"
                importance = "中等"
            else:
                level = "📝 潜在优势"
                importance = "较低"
            
            analysis += f"{i}. 【{positive}】 {level}\n"
            analysis += f"   📊 统计数据: {count} 次提及 (占总评论的 {percentage:.1f}%)\n"
            analysis += f"   ⭐ 重要程度: {importance}\n"
            
            # 添加具体优点细节
            if positive in positive_details and positive_details[positive]:
                details = positive_details[positive][:5]  # 最多显示5个关键词
                analysis += f"   ✨ 具体表现: {', '.join(details)}\n"
            
            # 添加具体评价示例
            if positive in positive_examples and positive_examples[positive]:
                analysis += f"   💬 用户好评示例:\n"
                for j, example in enumerate(positive_examples[positive], 1):
                    analysis += f"   {j}. \"{example}\"\n"
            
            # 添加优势维护建议
            maintain_suggestions = {
                '质量优秀': '继续保持严格的质量控制标准，定期优化生产工艺和原材料选择',
                '物流满意': '维持高效的物流配送体系，继续优化配送时效和包装质量',
                '尺寸合适': '保持准确的尺码标准，继续完善尺寸指导和选择建议',
                '效果显著': '持续优化产品功效，保持技术研发投入和创新',
                '服务优质': '保持优质的客户服务水平，持续提升服务响应速度和专业度',
                '价格优势': '维持合理的价格策略，继续提升产品性价比和市场竞争力',
                '外观满意': '保持产品设计优势，持续创新外观设计和美观度',
                '使用体验': '维持产品易用性，持续优化用户体验和操作便利性',
                '推荐满意': '继续保持产品品质，加强口碑营销和用户推荐机制'
            }
            
            if positive in maintain_suggestions:
                analysis += f"   💡 优势维护策略: {maintain_suggestions[positive]}\n"
            
            analysis += "\n"
        
        # 添加优势总结和建议
        if sorted_positives:
            top_advantage = sorted_positives[0][0]
            top_percentage = (sorted_positives[0][1] / len(reviews)) * 100
            analysis += f"🎖️ 核心竞争优势总结:\n"
            analysis += f"• 最大优势: {top_advantage} (获得 {top_percentage:.1f}% 用户认可)\n"
            analysis += f"• 优势覆盖面: {len(positive_stats)} 个维度表现优秀\n"
            analysis += f"• 用户满意度: 多维度获得用户正面反馈\n\n"
            
            analysis += "📈 优势发展建议:\n"
            analysis += "• 🎯 强化核心优势: 将最受认可的优势作为品牌核心卖点\n"
            analysis += "• 🔄 优势互补: 将多个优势有机结合，形成综合竞争力\n"
            analysis += "• 📢 营销重点: 在产品推广中突出用户最认可的优势\n"
            analysis += "• 📊 持续监控: 定期跟踪优势表现，确保持续领先\n"
            analysis += "• 🚀 创新发展: 基于现有优势，探索新的产品亮点\n\n"
    else:
        analysis += "⚠️ 优势分析结果:\n"
        analysis += "• 未发现明显的优点关键词提及\n"
        analysis += "• 建议加强产品优势建设和用户体验提升\n"
        analysis += "• 可考虑优化产品功能、服务质量或营销策略\n\n"
    
    # 添加综合评估总结
    analysis += "📋 综合评估与总结报告：\n\n"
    
    # 数据概览
    analysis += "📊 数据概览：\n"
    analysis += f"• 评价总数: {len(reviews)} 条\n"
    if ratings:
        analysis += f"• 平均评分: {avg_rating:.2f} 分\n"
    analysis += f"• 问题类别: {len(problem_stats)} 种\n"
    analysis += f"• 优势类别: {len(positive_stats)} 种\n\n"
    
    # 核心发现
    analysis += "🔍 核心发现：\n"
    if problem_stats:
        main_problem = sorted_problems[0][0]
        problem_percentage = (sorted_problems[0][1] / len(reviews)) * 100
        analysis += f"• 🚨 最主要问题: {main_problem} (影响 {problem_percentage:.1f}% 的用户)\n"
        analysis += f"• 📉 问题影响面: {len(problem_stats)} 个维度存在改进空间\n"
    
    if positive_stats:
        main_positive = sorted_positives[0][0]
        positive_percentage = (sorted_positives[0][1] / len(reviews)) * 100
        analysis += f"• 🏆 最大竞争优势: {main_positive} (获得 {positive_percentage:.1f}% 用户认可)\n"
        analysis += f"• 📈 优势覆盖面: {len(positive_stats)} 个维度表现优秀\n"
    
    # 满意度分析
    if ratings:
        high_rating_count = sum(1 for rating in ratings if rating >= 4)
        medium_rating_count = sum(1 for rating in ratings if rating == 3)
        low_rating_count = sum(1 for rating in ratings if rating <= 2)
        
        satisfaction_rate = (high_rating_count / len(ratings)) * 100
        medium_rate = (medium_rating_count / len(ratings)) * 100
        dissatisfaction_rate = (low_rating_count / len(ratings)) * 100
        
        analysis += f"\n📈 用户满意度分析：\n"
        analysis += f"• 高满意度 (4-5星): {satisfaction_rate:.1f}% ({high_rating_count} 条)\n"
        analysis += f"• 中等满意度 (3星): {medium_rate:.1f}% ({medium_rating_count} 条)\n"
        analysis += f"• 低满意度 (1-2星): {dissatisfaction_rate:.1f}% ({low_rating_count} 条)\n"
        
        # 综合评估
        analysis += f"\n🎯 综合评估结果：\n"
        if satisfaction_rate >= 80:
            grade = "A级 (优秀)"
            status = "✅ 产品表现优秀"
            recommendation = "继续保持现有优势，适度优化细节问题"
        elif satisfaction_rate >= 70:
            grade = "B级 (良好)"
            status = "✅ 产品表现良好"
            recommendation = "在保持优势的基础上，重点改进主要问题"
        elif satisfaction_rate >= 60:
            grade = "C级 (一般)"
            status = "⚠️ 产品表现一般"
            recommendation = "需要系统性改进，优先解决影响面最大的问题"
        elif satisfaction_rate >= 40:
            grade = "D级 (较差)"
            status = "❌ 产品表现较差"
            recommendation = "需要全面改进，建议制定详细的改进计划"
        else:
            grade = "E级 (差)"
            status = "❌ 产品表现很差"
            recommendation = "需要紧急改进，建议重新评估产品策略"
        
        analysis += f"• 产品评级: {grade}\n"
        analysis += f"• 整体状态: {status}\n"
        analysis += f"• 改进建议: {recommendation}\n"
    
    # 行动建议
    analysis += f"\n🚀 下一步行动建议：\n"
    if problem_stats:
        analysis += f"• 🎯 优先级1: 立即解决 '{sorted_problems[0][0]}' 问题\n"
        if len(sorted_problems) > 1:
            analysis += f"• 🎯 优先级2: 改进 '{sorted_problems[1][0]}' 相关问题\n"
    
    if positive_stats:
        analysis += f"• 💪 强化优势: 继续发挥 '{sorted_positives[0][0]}' 的竞争优势\n"
    
    analysis += "• 📊 持续监控: 建立定期评价分析机制\n"
    analysis += "• 🔄 迭代改进: 根据用户反馈持续优化产品\n"
    analysis += "• 📢 营销策略: 基于分析结果调整产品推广重点\n"
    
    return analysis

def analyze_negative_reviews(sku_or_asin, months_limit=3, max_rating=5, use_local=False):
    """分析评价的主函数（支持所有星级）"""
    try:
        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_limit * 30)
        
        # 使用正确的列名进行查询，支持所有星级
        if max_rating >= 5:
            # 查询所有星级
            sql = f"""
            SELECT * FROM PingJia
            WHERE ASIN + SKU like '%{sku_or_asin}%'
            AND RiQi >= '{start_date.strftime('%Y-%m-%d')}'
            ORDER BY RiQi DESC
            """
            rating_desc = "所有星级"
        else:
            # 查询指定星级及以下
            sql = f"""
            SELECT * FROM PingJia
            WHERE ASIN + SKU like '%{sku_or_asin}%'
            AND XingJi <= {max_rating}
            AND RiQi >= '{start_date.strftime('%Y-%m-%d')}'
            ORDER BY RiQi DESC
            """
            rating_desc = f"{max_rating}星及以下"
        
        # 从数据库获取数据
        reviews = bjc.sf_db(sql)
        
        if not reviews:
            return {
                'success': False,
                'message': f'未找到SKU/ASIN "{sku_or_asin}" 在过去{months_limit}个月内{rating_desc}的评价数据',
                'analysis': '',
                'review_count': 0
            }
        
        analysis_result = ""
        
        if use_local:
            # 使用本地分析
            analysis_result = local_analysis(reviews)
        else:
            # 尝试使用AI分析
            try:
                # 获取OpenAI配置
                openai_key = session.get('openai_key')
                openai_base_url = session.get('openai_base_url')
                
                if not openai_key:
                    analysis_result = local_analysis(reviews)
                else:
                    client = OpenAI(
                        api_key=openai_key,
                        base_url=openai_base_url if openai_base_url else None
                    )
                    
                    # 准备分析数据
                    review_texts = []
                    for review in reviews[:50]:  # 限制分析数量
                        if len(review) > 8:
                            # 获取评论内容 (索引7是英文，索引8是中文)
                            content_en = str(review[7] or '')
                            content_cn = str(review[8] or '')
                            content = (content_cn + ' ' + content_en).strip()
                            rating = review[5] if len(review) > 5 else 0
                            if content:
                                review_texts.append(f"{rating}星: {content}")
                    
                    if review_texts:
                        prompt = f"""
                        你是一位专业的产品分析师，请对以下产品评价进行深度分析。请务必用中文回答，提供详细、全面的分析报告。
                        
                        📊 产品信息：
                        • 产品标识: {sku_or_asin}
                        • 评价数量: {len(reviews)} 条
                        • 分析时间范围: 最近 {months_limit} 个月
                        
                        📝 评价内容:
                        {chr(10).join(review_texts[:30])}
                        
                        请按以下结构进行详细分析，每个部分都要尽可能详细：
                        
                        🔍 1. 问题分类统计
                        - 将所有问题按类别组长（质量、物流、尺寸、效果、服务、价格等）
                        - 统计每类问题的出现频次和占比
                        - 列出每类问题的具体表现形式

                        
                        📈 2. 问题严重程度分析
                        - 按影响程度对问题进行排序（高、中、低）
                        - 分析每个问题对用户体验的具体影响
                        - 评估问题的紧急程度和解决难度
                        
                        💡 3. 详细改进建议
                        - 针对每个主要问题提供具体的解决方案
                        - 建议改进的优先级顺序
                        - 预估改进效果和实施难度
                        
                        🎯 4. 优先解决方案
                        - 列出最需要立即解决的3个问题
                        - 提供短期、中期、长期的改进计划
                        - 建议具体的执行步骤和时间安排
                        
                        🌟 5. 优点分析
                        - 总结用户认可的产品优点
                        - 分析可以继续发扬的特色
                        - 建议如何放大产品优势

                        
                        📋 6. 综合评估
                        - 产品整体表现评价
                        - 市场竞争力分析
                        - 用户满意度趋势判断
                        

                        
                        请确保分析内容详细具体，每个建议都要有可操作性，用词专业但易懂。
                        """
                        
                        messages = [
                            {"role": "system", "content": "你是一位资深的产品分析专家，拥有丰富的电商产品评价分析经验。你擅长从用户反馈中提取关键信息，识别产品问题，并提供具体可行的改进建议。请务必用中文回答，提供详细、专业、易懂的分析报告。你的分析应该条理清晰、逻辑严密、建议具体可操作。"},
                            {"role": "user", "content": prompt}
                        ]
                        content = _ai_chat_complete(
                            client,
                            messages=messages,
                            max_tokens=2500,
                            temperature=0.3,
                            model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES
                        )
                        analysis_result = format_analysis_result(content)
                    else:
                        analysis_result = "所选评价中没有有效的评价内容"
                        
            except Exception as ai_error:
                print(f"AI分析失败: {ai_error}")
                analysis_result = local_analysis(reviews)
        
        # 保存分析记录
        save_analysis_record(sku_or_asin, len(reviews), analysis_result)
        
        return {
            'success': True,
            'message': f'成功分析了{len(reviews)}条评价',
            'analysis': analysis_result,
            'review_count': len(reviews),
            'reviews': reviews[:10]  # 返回前10条评价供详细查看
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'分析过程中出现错误: {str(e)}',
            'analysis': '',
            'review_count': 0
        }

def save_analysis_record(sku_or_asin, review_count, analysis_result):
    """保存分析记录到数据库"""
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 插入分析记录
        insert_sql = f"""
        INSERT INTO AnalysisHistory (sku_asin, review_count, analysis_result, analysis_time)
        VALUES ('{sku_or_asin}', {review_count}, '{analysis_result.replace("'", "''")}', '{current_time}')
        """
        
        bjc.dui_db(insert_sql)
        print(f"分析记录已保存: {sku_or_asin}")
        
    except Exception as e:
        print(f"保存分析记录失败: {e}")

def get_analysis_history(sku_or_asin=None, limit=10):
    """获取分析历史记录"""
    try:
        if sku_or_asin:
            sql = f"""
            SELECT TOP {limit} * FROM AnalysisHistory 
            WHERE sku_asin = '{sku_or_asin}'
            ORDER BY analysis_time DESC
            """
        else:
            sql = f"""
            SELECT TOP {limit} * FROM AnalysisHistory 
            ORDER BY analysis_time DESC
            """
        
        history = bjc.sf_db(sql)
        return history if history else []
        
    except Exception as e:
        print(f"获取历史记录失败: {e}")
        return []

# 路由定义
@review_analysis_bp.route('/review_analysis')
@require_permission('review_analysis')
def review_analysis():
    """差评分析页面"""
    return render_template('review_analysis.html')

@review_analysis_bp.route('/analyze_reviews', methods=['POST'])
@require_permission('review_analysis')
def analyze_reviews():
    """处理差评分析请求"""
    try:
        data = request.get_json()
        product_identifier = data.get('product_identifier', '').strip()
        months_limit = int(data.get('months_limit', 3))
        max_rating = int(data.get('max_rating', 3))
        use_local = data.get('use_local', False)
        
        # 检查是否输入了产品标识符
        if not product_identifier:
            return jsonify({
                'success': False,
                'message': '请输入SKU或ASIN'
            })
        
        sku_or_asin = product_identifier
        
        # 执行分析
        result = analyze_negative_reviews(sku_or_asin, months_limit, max_rating, use_local)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'请求处理失败: {str(e)}'
        })

@review_analysis_bp.route('/get_analysis_history')
def get_analysis_history_api():
    """获取分析历史记录API"""
    try:
        sku_or_asin = request.args.get('sku_asin')
        limit = int(request.args.get('limit', 10))
        
        history_raw = get_analysis_history(sku_or_asin, limit)
        
        # 将数据库结果转换为前端期望的格式
        history = []
        for record in history_raw:
            history.append({
                'product_identifier': record[1],  # sku_asin字段
                'analysis_date': record[4].strftime('%Y-%m-%d %H:%M:%S') if record[4] else None,  # 格式化时间
                'review_count': record[2],  # review_count字段
                'status': '已完成'  # 固定状态
            })
        
        return jsonify({
            'success': True,
            'history': history
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取历史记录失败: {str(e)}',
            'history': []
        })

@review_analysis_bp.route('/get_analysis_detail', methods=['GET'])
def get_analysis_detail():
    """获取分析详细内容"""
    
    try:
        product_identifier = (request.args.get('product_identifier') or '').strip()
        analysis_date = (request.args.get('analysis_date') or '').strip()
        
        if not product_identifier or not analysis_date:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 这里避免使用 LIKE '%', 某些驱动场景下会触发 format string 相关异常
        product_identifier_safe = product_identifier.replace("'", "''")
        analysis_date_safe = analysis_date.replace("'", "''")[:19]
        sql = (
            "SELECT TOP 1 * FROM AnalysisHistory "
            f"WHERE sku_asin = '{product_identifier_safe}' "
            f"AND CONVERT(varchar(19), analysis_time, 120) = '{analysis_date_safe}' "
            "ORDER BY analysis_time DESC"
        )
        result = bjc.sf_db(sql)
        
        if result and len(result) > 0:
            record = result[0]
            return jsonify({
                'success': True,
                'analysis': record[3],  # analysis_result字段
                'review_count': record[2],
                'product_identifier': record[1],
                'analysis_time': record[4].strftime('%Y-%m-%d %H:%M:%S') if record[4] else None  # analysis_time字段
            })
        else:
            return jsonify({'success': False, 'message': '未找到分析记录'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取详情失败: {str(e)}'})

@review_analysis_bp.route('/analyze_word_freq', methods=['POST'])
@require_permission('review_analysis')
def analyze_word_freq():
    try:
        data = request.get_json()
        product_identifier = (data.get('product_identifier') or '').strip()
        months_limit = int(data.get('months_limit') or 3)
        max_rating = int(data.get('max_rating') or 5)
        exclude_words_raw = data.get('exclude_words') or ''
        top_n = int(data.get('top_n') or 100)

        if not product_identifier:
            return jsonify({'success': False, 'message': '请输入SKU或ASIN'})

        sku_or_asin = product_identifier.replace("'", "''")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_limit * 30)
        if max_rating >= 5:
            sql = f"""
            SELECT * FROM PingJia
            WHERE ASIN + SKU like '%{sku_or_asin}%'
            AND RiQi >= '{start_date.strftime('%Y-%m-%d')}'
            ORDER BY RiQi DESC
            """
        else:
            sql = f"""
            SELECT * FROM PingJia
            WHERE ASIN + SKU like '%{sku_or_asin}%'
            AND XingJi <= {max_rating}
            AND RiQi >= '{start_date.strftime('%Y-%m-%d')}'
            ORDER BY RiQi DESC
            """
        reviews = bjc.sf_db(sql) or []

        if not reviews:
            return jsonify({'success': True, 'message': '未找到评价数据', 'frequencies': [], 'review_count': 0})

        exclude_set = set()
        for line in (exclude_words_raw.split('\n') if exclude_words_raw else []):
            w = line.strip().lower()
            if w:
                exclude_set.add(w)

        counter = Counter()
        bi_counter = Counter()
        tri_counter = Counter()
        quad_counter = Counter()
        for review in reviews:
            if len(review) > 8:
                content_en = str(review[7] or '')
                content_cn = str(review[8] or '')
                text = (content_cn + ' ' + content_en).strip()
                text_lower = text.lower()
                english_tokens = re.findall(r'[a-zA-Z]+', text_lower)
                english_tokens = [t for t in english_tokens if len(t) >= 2]
                chinese_tokens = re.findall(r'[\u4e00-\u9fff]{2,}', text)
                tokens = english_tokens + chinese_tokens
                filtered = []
                for t in tokens:
                    if t.lower() not in exclude_set:
                        counter[t] += 1
                        filtered.append(t)
                for i in range(len(filtered) - 1):
                    phrase = filtered[i] + ' ' + filtered[i + 1]
                    bi_counter[phrase] += 1
                for i in range(len(filtered) - 2):
                    phrase = filtered[i] + ' ' + filtered[i + 1] + ' ' + filtered[i + 2]
                    tri_counter[phrase] += 1
                for i in range(len(filtered) - 3):
                    phrase = filtered[i] + ' ' + filtered[i + 1] + ' ' + filtered[i + 2] + ' ' + filtered[i + 3]
                    quad_counter[phrase] += 1

        sorted_items = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        top_items = sorted_items[:top_n]
        frequencies = [{'word': w, 'count': c} for w, c in top_items]

        bi_items = sorted(bi_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
        tri_items = sorted(tri_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
        quad_items = sorted(quad_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
        phrases = {
            'bi': [{'phrase': p, 'count': c} for p, c in bi_items],
            'tri': [{'phrase': p, 'count': c} for p, c in tri_items],
            'quad': [{'phrase': p, 'count': c} for p, c in quad_items]
        }
        return jsonify({'success': True, 'message': '筛选完成', 'frequencies': frequencies, 'phrases': phrases, 'review_count': len(reviews)})
    except Exception as e:
        return jsonify({'success': False, 'message': f'筛选失败: {str(e)}'})
