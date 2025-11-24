# -*- coding: utf-8 -*-
"""
导入之前的提示词数据
"""
import json
from pathlib import Path

# 读取旧的提示词数据
old_prompts_file = Path(r"C:\Users\bisu5\Desktop\夕小瑶科技\gemini3 画图\data\prompts_mega_collection.json")
with open(old_prompts_file, "r", encoding="utf-8") as f:
    old_data = json.load(f)

# 读取当前的image_cases
new_file = Path(r"C:\Users\bisu5\Desktop\夕小瑶科技\AI模型一键测评工具\test_cases\image_cases.json")
with open(new_file, "r", encoding="utf-8") as f:
    new_data = json.load(f)

# 转换格式
converted_cases = []
for prompt in old_data.get("prompts", []):
    if prompt.get("type") == "text2img":  # 只导入文生图的
        case = {
            "id": f"I{prompt['id']:03d}",  # 格式化为 I001, I002...
            "name": prompt.get("name", ""),
            "category": prompt.get("subcategory", prompt.get("category", "")),
            "difficulty": prompt.get("difficulty", "中"),
            "prompt": prompt.get("prompt", "")
        }
        converted_cases.append(case)

# 合并到新数据
existing_ids = {c["id"] for c in new_data.get("cases", [])}
for case in converted_cases:
    if case["id"] not in existing_ids:
        new_data["cases"].append(case)

# 更新meta信息
new_data["meta"] = {
    "description": "文生图测试用例集 - 图像生成能力测评",
    "total": len(new_data["cases"]),
    "version": "2.0"
}

# 保存
with open(new_file, "w", encoding="utf-8") as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)

print(f"成功导入 {len(converted_cases)} 个提示词")
print(f"当前共有 {len(new_data['cases'])} 个测试案例")
