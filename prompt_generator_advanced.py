# -*- coding: utf-8 -*-
"""
🎨 智能提示词生成器 v3.0
多线程 + 多类型 + 创意设计 + 自动归类
支持代码生成、文生文、文生图三大类型
"""

import json
import requests
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

# ==================== 配置 ====================
class Config:
    REQUEST_TIMEOUT = 120
    MAX_RETRIES = 3
    BASE_DELAY = 2
    MAX_DELAY = 30


# ==================== 爆款提示词策略系统 ====================

# 代码生成策略
CODE_GEN_STRATEGIES = {
    "技术炫技型": {
        "weight": 25,
        "formula": "[高难度实现] + [视觉震撼] + [单文件完整]",
        "examples": [
            "3D粒子系统 + 物理引擎 + 中文UI",
            "WebGL着色器编程 + 实时光线追踪",
            "Canvas游戏引擎 + 完整关卡系统"
        ]
    },
    "实用利他型": {
        "weight": 30,
        "formula": "[真实需求] + [降低门槛] + [即时可用]",
        "examples": [
            "待办事项管理 + 本地存储 + 拖拽排序",
            "简历生成器 + PDF导出 + 模板切换",
            "番茄钟 + 统计图表 + 专注模式"
        ]
    },
    "反差爽感型": {
        "weight": 15,
        "formula": "[严肃×娱乐] OR [传统×现代]",
        "examples": [
            "霸道总裁决策游戏",
            "古诗词连连看",
            "赛博朋克算命先生"
        ]
    },
    "教育工具型": {
        "weight": 20,
        "formula": "[教学需求] + [可视化] + [交互演示]",
        "examples": [
            "数据结构可视化 + 动画演示",
            "物理实验模拟器",
            "编程语法可视化教学"
        ]
    },
    "创意脑洞型": {
        "weight": 10,
        "formula": "[荒诞设定] + [认真实现] + [细节完整]",
        "examples": [
            "猫咪代码审查助手",
            "反重力俄罗斯方块",
            "时间倒流的井字棋"
        ]
    }
}

# 文生文策略
WRITING_STRATEGIES = {
    "专业实用型": {
        "weight": 30,
        "formula": "[职场需求] + [格式规范] + [即用模板]",
        "examples": [
            "技术文档撰写指南",
            "商业计划书模板",
            "专业邮件写作范例"
        ]
    },
    "创意文学型": {
        "weight": 25,
        "formula": "[文学形式] + [主题深度] + [情感共鸣]",
        "examples": [
            "科幻微小说创作",
            "现代诗歌创作",
            "悬疑推理故事"
        ]
    },
    "知识科普型": {
        "weight": 25,
        "formula": "[专业知识] + [通俗表达] + [案例丰富]",
        "examples": [
            "量子计算科普",
            "艺术史讲解",
            "金融知识入门"
        ]
    },
    "反差创意型": {
        "weight": 10,
        "formula": "[严肃×轻松] OR [古典×现代]",
        "examples": [
            "用rap讲解量子力学",
            "文言文版产品发布会",
            "古人穿越到现代的日记"
        ]
    },
    "情感治愈型": {
        "weight": 10,
        "formula": "[情感洞察] + [共鸣场景] + [正能量]",
        "examples": [
            "给焦虑者的一封信",
            "深夜食堂故事",
            "城市独居者的温暖瞬间"
        ]
    }
}

# 文生图策略
IMAGE_GEN_STRATEGIES = {
    "中文文字炫技": {
        "weight": 25,
        "formula": "[复杂中文] + [视觉设计] + [文化准确]",
        "examples": [
            "赛博朋克中文招牌",
            "古籍插画+书法标注",
            "多语言美食菜单设计"
        ]
    },
    "视觉冲击型": {
        "weight": 20,
        "formula": "[强烈对比] + [史诗构图] + [戏剧光线]",
        "examples": [
            "霓虹雨夜都市",
            "末日废墟中的生命",
            "微观世界的宏大"
        ]
    },
    "文化融合型": {
        "weight": 20,
        "formula": "[传统×科技] OR [东方×西方]",
        "examples": [
            "赛博朋克京剧",
            "蒸汽朋克茶室",
            "未来考古博物馆"
        ]
    },
    "实用教育型": {
        "weight": 15,
        "formula": "[教学需求] + [清晰图示] + [专业准确]",
        "examples": [
            "物理原理图解",
            "编程概念可视化",
            "历史事件时间轴"
        ]
    },
    "细节极致型": {
        "weight": 15,
        "formula": "[超写实] + [光线追踪] + [材质精准]",
        "examples": [
            "珠宝微距特写",
            "美食摄影",
            "建筑细节纹理"
        ]
    },
    "反差脑洞型": {
        "weight": 5,
        "formula": "[违和组合] + [荒诞认真] + [细节完整]",
        "examples": [
            "猫咪CEO办公室",
            "反重力咖啡馆",
            "赛博朋克菜市场"
        ]
    }
}


# ==================== 智能提示词生成系统 ====================

class AdvancedPromptGenerator:
    """智能提示词生成器"""

    # 系统提示词模板
    CODE_SYSTEM_PROMPT = """# 你是顶级AI代码测评专家 + 产品设计师

## 核心使命
为AI模型设计代码生成测试提示词，要求：
- **实用性**: 真实需求，能解决实际问题
- **技术深度**: 测试AI的技术边界
- **创意性**: 有反差感、意外性、不落俗套
- **完整性**: 单文件可运行，包含HTML+CSS+JS

## 生成策略（随机选择）
{strategies}

## 提示词标准

✅ **必须包含**:
1. 明确的功能需求（3-5个核心功能）
2. 技术约束（单文件HTML、不依赖外部库等）
3. UI/UX要求（布局、交互、视觉风格）
4. 特殊挑战点（测试AI能力边界）
5. 中文标注要求（如适用）

✅ **避免**:
- 需要后端支持的功能
- 需要外部库的实现
- 过于简单的Demo
- 与已有案例重复

## 输出格式（JSON数组）

```json
[
  {{
    "name": "案例名称（简短精准）",
    "category": "分类（交互游戏/实用工具/动画效果等）",
    "difficulty": "简单|中|高",
    "tags": ["标签1", "标签2", "标签3"],
    "icon": "emoji图标",
    "prompt": "详细的测试提示词（200-400字）...",
    "hook": "为什么要测这个？（一句话）",
    "test_points": ["测试点1", "测试点2", "测试点3"]
  }}
]
```

## 当前任务
请生成 {count} 个代码生成测试提示词。
要求：策略多样化，创意突出，难度分布合理（简单30% 中40% 高30%）

直接输出JSON数组，不要额外说明。
"""

    WRITING_SYSTEM_PROMPT = """# 你是顶级AI写作测评专家 + 内容策划师

## 核心使命
为AI模型设计文生文测试提示词，要求：
- **场景真实**: 贴近实际写作需求
- **风格多样**: 涵盖多种文体和语言风格
- **深度测试**: 考验AI的语言理解和创作能力
- **创意设计**: 有反差感、不落俗套的写作任务

## 生成策略（随机选择）
{strategies}

## 提示词标准

✅ **必须包含**:
1. 明确的写作任务（文体、主题、篇幅）
2. 格式要求（结构、风格、语气）
3. 内容要点（必须包含的元素）
4. 特殊约束（测试AI能力边界）
5. 目标读者定位

✅ **避免**:
- 过于宽泛的主题
- 没有约束的自由发挥
- 与已有案例重复

## 输出格式（JSON数组）

```json
[
  {{
    "name": "案例名称",
    "category": "分类（新闻写作/创意写作/技术写作等）",
    "difficulty": "简单|中|高",
    "tags": ["标签1", "标签2", "标签3"],
    "icon": "emoji图标",
    "prompt": "详细的写作任务描述（150-300字）...",
    "hook": "为什么要写这个？",
    "test_points": ["测试点1", "测试点2", "测试点3"]
  }}
]
```

## 当前任务
请生成 {count} 个文生文测试提示词。
要求：文体多样，创意突出，难度合理（简单30% 中40% 高30%）

直接输出JSON数组，不要额外说明。
"""

    IMAGE_SYSTEM_PROMPT = """# 你是顶级AI图像测评专家 + 视觉设计师

## 核心使命
为AI图像生成模型设计测试提示词，要求：
- **视觉冲击**: 强烈的画面感和吸引力
- **技术挑战**: 测试模型的技术边界
- **文化深度**: 融合文化元素和创意
- **实用价值**: 可直接用于设计、教育等场景

## 模型特性（必须利用）
✅ 中文文字渲染能力极强
✅ 多语言支持（中日韩、阿拉伯语等）
✅ 视觉设计精准
✅ 细节极致（材质、光线、物理真实）

## 生成策略（随机选择）
{strategies}

## 提示词标准

✅ **必须包含**:
1. 主体描述（清晰明确）
2. 视觉风格（画风、材质、光线）
3. 构图与视角
4. 色彩方案
5. 特殊要求（文字内容、细节等）
6. 氛围与情绪

✅ **避免**:
- 模糊描述（"好看的"、"漂亮的"）
- 过于简单
- 无测试价值

## 输出格式（JSON数组）

```json
[
  {{
    "name": "案例名称",
    "category": "分类",
    "difficulty": "简单|中|高|极高",
    "tags": ["标签1", "标签2", "标签3"],
    "icon": "emoji图标",
    "prompt": "详细的图像生成提示词（英文，200-400字）...",
    "hook": "为什么要生成这张图？",
    "test_points": ["测试点1", "测试点2", "测试点3"],
    "expected_weakness": "最可能失败的地方"
  }}
]
```

## 当前任务
请生成 {count} 个文生图测试提示词。
要求：创意突出，视觉冲击力强，测试价值高

直接输出JSON数组，不要额外说明。
"""

    def __init__(self, api_url: str, api_key: str, model: str, base_dir: Path):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.base_dir = base_dir
        self.session = self._create_session()

    def _create_session(self):
        """创建HTTP会话"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        })
        return session

    def _format_strategies(self, strategies: Dict) -> str:
        """格式化策略说明"""
        lines = []
        for name, info in strategies.items():
            lines.append(f"### {name} ({info['weight']}%权重)")
            lines.append(f"**公式**: {info['formula']}")
            lines.append(f"**示例**: {', '.join(info['examples'][:2])}")
            lines.append("")
        return "\n".join(lines)

    def _call_api(self, prompt: str, system_prompt: str) -> Optional[str]:
        """调用API生成提示词"""
        endpoint = f"{self.api_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 8192,
            "temperature": 0.9  # 高创意性
        }

        for attempt in range(Config.MAX_RETRIES):
            try:
                response = self.session.post(
                    endpoint,
                    json=payload,
                    timeout=Config.REQUEST_TIMEOUT
                )
                response.encoding = 'utf-8'
                response.raise_for_status()

                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0]['message']['content'].strip()
                    return content

            except Exception as e:
                if attempt < Config.MAX_RETRIES - 1:
                    delay = Config.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                else:
                    raise Exception(f"API调用失败: {str(e)}")

        return None

    def _extract_json(self, content: str) -> List[Dict]:
        """从响应中提取JSON"""
        import re

        # 尝试提取JSON数组
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 如果失败，尝试修复常见问题
        try:
            # 移除markdown代码块标记
            content = re.sub(r'```json\s*|\s*```', '', content)
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析失败: {str(e)}")

    def generate_code_prompts(self, count: int, log_callback=None) -> List[Dict]:
        """生成代码生成提示词"""
        log = log_callback or print

        strategies = self._format_strategies(CODE_GEN_STRATEGIES)
        system_prompt = self.CODE_SYSTEM_PROMPT.format(
            strategies=strategies,
            count=count
        )

        log(f"🔨 正在生成 {count} 个代码生成提示词...")

        try:
            content = self._call_api("", system_prompt)
            if not content:
                raise Exception("API返回空内容")

            prompts = self._extract_json(content)
            log(f"✅ 成功生成 {len(prompts)} 个代码提示词")
            return prompts

        except Exception as e:
            log(f"❌ 代码提示词生成失败: {str(e)}")
            return []

    def generate_writing_prompts(self, count: int, log_callback=None) -> List[Dict]:
        """生成文生文提示词"""
        log = log_callback or print

        strategies = self._format_strategies(WRITING_STRATEGIES)
        system_prompt = self.WRITING_SYSTEM_PROMPT.format(
            strategies=strategies,
            count=count
        )

        log(f"✍️ 正在生成 {count} 个文生文提示词...")

        try:
            content = self._call_api("", system_prompt)
            if not content:
                raise Exception("API返回空内容")

            prompts = self._extract_json(content)
            log(f"✅ 成功生成 {len(prompts)} 个文生文提示词")
            return prompts

        except Exception as e:
            log(f"❌ 文生文提示词生成失败: {str(e)}")
            return []

    def generate_image_prompts(self, count: int, log_callback=None) -> List[Dict]:
        """生成文生图提示词"""
        log = log_callback or print

        strategies = self._format_strategies(IMAGE_GEN_STRATEGIES)
        system_prompt = self.IMAGE_SYSTEM_PROMPT.format(
            strategies=strategies,
            count=count
        )

        log(f"🎨 正在生成 {count} 个文生图提示词...")

        try:
            content = self._call_api("", system_prompt)
            if not content:
                raise Exception("API返回空内容")

            prompts = self._extract_json(content)
            log(f"✅ 成功生成 {len(prompts)} 个文生图提示词")
            return prompts

        except Exception as e:
            log(f"❌ 文生图提示词生成失败: {str(e)}")
            return []

    def generate_all_parallel(self, code_count=5, writing_count=5, image_count=5,
                            log_callback=None) -> Dict[str, List[Dict]]:
        """并行生成三种类型的提示词"""
        log = log_callback or print

        log(f"\n{'='*80}")
        log(f"🚀 智能提示词生成器 v3.0 - 多线程并行生成")
        log(f"{'='*80}")
        log(f"📝 代码生成: {code_count} 个")
        log(f"✍️ 文生文: {writing_count} 个")
        log(f"🎨 文生图: {image_count} 个")
        log(f"{'='*80}\n")

        results = {
            "code": [],
            "writing": [],
            "image": []
        }

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            if code_count > 0:
                futures[executor.submit(self.generate_code_prompts, code_count, log)] = "code"
            if writing_count > 0:
                futures[executor.submit(self.generate_writing_prompts, writing_count, log)] = "writing"
            if image_count > 0:
                futures[executor.submit(self.generate_image_prompts, image_count, log)] = "image"

            for future in as_completed(futures):
                prompt_type = futures[future]
                try:
                    prompts = future.result()
                    results[prompt_type] = prompts
                except Exception as e:
                    log(f"❌ {prompt_type} 生成失败: {str(e)}")

        elapsed = time.time() - start_time
        total_count = sum(len(v) for v in results.values())

        log(f"\n{'='*80}")
        log(f"✅ 生成完成！")
        log(f"⏱️  总耗时: {elapsed:.1f}秒")
        log(f"📊 总数量: {total_count} 个提示词")
        log(f"{'='*80}\n")

        return results
