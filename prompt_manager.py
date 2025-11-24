# -*- coding: utf-8 -*-
"""
提示词管理器 - 管理测试用例提示词
"""

import json
import requests
from pathlib import Path


class PromptManager:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.text_cases_file = self.base_dir / "test_cases" / "text_cases.json"
        self.image_cases_file = self.base_dir / "test_cases" / "image_cases.json"

    def load_cases(self, test_type):
        """加载测试用例"""
        file_path = self.text_cases_file if test_type == "text" else self.image_cases_file

        if not file_path.exists():
            return {"meta": {}, "cases": []}

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_cases(self, test_type, data):
        """保存测试用例"""
        file_path = self.text_cases_file if test_type == "text" else self.image_cases_file

        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_case(self, test_type, case):
        """添加测试用例"""
        data = self.load_cases(test_type)
        data["cases"].append(case)
        self.save_cases(test_type, data)

    def update_case(self, test_type, case_id, updated_case):
        """更新测试用例"""
        data = self.load_cases(test_type)
        for i, case in enumerate(data["cases"]):
            if case["id"] == case_id:
                data["cases"][i] = updated_case
                break
        self.save_cases(test_type, data)

    def delete_case(self, test_type, case_id):
        """删除测试用例"""
        data = self.load_cases(test_type)
        data["cases"] = [c for c in data["cases"] if c["id"] != case_id]
        self.save_cases(test_type, data)

    def generate_prompts(self, api_url, api_key, model, test_type, count, log_callback=None):
        """使用AI生成提示词"""
        log = log_callback or print

        if test_type == "text":
            system_prompt = f"""你是一个AI测试专家。请生成{count}个用于测试AI代码生成能力的提示词。
每个提示词应该要求AI生成一个完整可运行的HTML文件，包含CSS和JavaScript。
案例应该涵盖不同难度和类别，如：动画效果、交互游戏、数据可视化、实用工具等。

请以JSON格式返回，格式如下：
[
  {{
    "id": "T<序号>",
    "name": "案例名称",
    "category": "分类",
    "difficulty": "简单|中|高",
    "prompt": "详细的测试提示词，要求生成单文件完整可运行的HTML..."
  }}
]
"""
        else:
            system_prompt = f"""你是一个AI测试专家。请生成{count}个用于测试AI图像生成能力的提示词。
案例应该涵盖不同场景和风格，如：未来科技、自然场景、人物肖像、建筑设计、产品设计等。
提示词应该使用英文，详细描述画面内容、风格、光影等。

请以JSON格式返回，格式如下：
[
  {{
    "id": "I<序号>",
    "name": "案例名称",
    "category": "分类",
    "difficulty": "简单|中|高",
    "prompt": "Detailed English prompt for image generation..."
  }}
]
"""

        log(f"正在使用AI生成{count}个{test_type}提示词...")

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": system_prompt}],
                "max_tokens": 4096
            }

            response = requests.post(
                f"{api_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"]

            # 提取JSON
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                prompts = json.loads(json_match.group())
                log(f"成功生成{len(prompts)}个提示词")
                return prompts
            else:
                log("无法从响应中提取JSON")
                return []

        except Exception as e:
            log(f"生成提示词失败: {str(e)}")
            return []

    def get_next_id(self, test_type):
        """获取下一个可用ID"""
        data = self.load_cases(test_type)
        if not data["cases"]:
            return "T01" if test_type == "text" else "I01"

        # 提取所有ID的数字部分
        ids = [int(c["id"][1:]) for c in data["cases"]]
        next_num = max(ids) + 1

        prefix = "T" if test_type == "text" else "I"
        return f"{prefix}{next_num:02d}"
