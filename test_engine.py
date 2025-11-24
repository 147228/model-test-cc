# -*- coding: utf-8 -*-
"""
测试引擎 - 执行文生文和文生图测试
"""

import json
import requests
import base64
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


class TestEngine:
    def __init__(self, api_url, api_key, text_model, image_model,
                 max_threads, output_dir, log_callback=None, progress_callback=None):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.text_model = text_model
        self.image_model = image_model
        self.max_threads = max_threads
        self.output_dir = Path(output_dir)
        self.log = log_callback or print
        self.update_progress = progress_callback or (lambda x: None)

        self.is_running = True
        self.results = {"text": [], "image": []}

        # 确保输出目录存在
        (self.output_dir / "text").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "image").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "website").mkdir(parents=True, exist_ok=True)

    def stop(self):
        """停止测试"""
        self.is_running = False

    def load_test_cases(self, test_type):
        """加载测试用例"""
        base_dir = Path(__file__).parent
        if test_type == "text":
            case_file = base_dir / "test_cases" / "text_cases.json"
        else:
            case_file = base_dir / "test_cases" / "image_cases.json"

        if not case_file.exists():
            self.log(f"警告: 测试用例文件不存在 {case_file}")
            return []

        with open(case_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cases", [])

    def call_api(self, prompt, model, is_image=False):
        """调用API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8192 if not is_image else 4096
        }

        endpoint = f"{self.api_url}/chat/completions"

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=300
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"API调用失败: {str(e)}")

    def run_text_tests(self):
        """执行文生文测试"""
        cases = self.load_test_cases("text")
        if not cases:
            return []

        self.log(f"开始文生文测试，共 {len(cases)} 个案例")
        results = []

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = {}
            for case in cases:
                if not self.is_running:
                    break
                future = executor.submit(self.run_single_text_test, case)
                futures[future] = case

            for i, future in enumerate(as_completed(futures)):
                if not self.is_running:
                    break
                case = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.log(f"[文生文] {case['id']} {case['name']} - 成功")
                except Exception as e:
                    self.log(f"[文生文] {case['id']} {case['name']} - 失败: {str(e)}")
                    results.append({
                        "id": case["id"],
                        "name": case["name"],
                        "success": False,
                        "error": str(e)
                    })

                progress = (i + 1) / len(cases) * 50  # 文生文占50%
                self.update_progress(progress)

        self.results["text"] = results
        return results

    def run_single_text_test(self, case):
        """执行单个文生文测试"""
        response = self.call_api(case["prompt"], self.text_model, is_image=False)

        content = response["choices"][0]["message"]["content"]

        # 保存响应（包含所有测试案例元数据）
        output_file = self.output_dir / "text" / f"{case['id']}_{case['name']}.json"
        result = {
            "id": case["id"],
            "name": case["name"],
            "category": case.get("category", "未分类"),
            "difficulty": case.get("difficulty", "中"),
            "tags": case.get("tags", []),
            "icon": case.get("icon", "📄"),
            "prompt": case["prompt"],
            "response": content,
            "timestamp": datetime.now().isoformat(),
            "success": True
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 提取HTML（如果有）
        html_content = self.extract_html(content)
        if html_content:
            html_file = self.output_dir / "text" / f"{case['id']}_{case['name']}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            result["html_file"] = str(html_file)

        return result

    def extract_html(self, content):
        """从响应中提取HTML代码"""
        patterns = [
            r'```html\n(.*?)\n```',
            r'```\n(<!DOCTYPE html>.*?</html>)\n```',
            r'(<!DOCTYPE html>.*?</html>)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def run_image_tests(self):
        """执行文生图测试"""
        cases = self.load_test_cases("image")
        if not cases:
            return []

        self.log(f"开始文生图测试，共 {len(cases)} 个案例")
        results = []

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = {}
            for case in cases:
                if not self.is_running:
                    break
                future = executor.submit(self.run_single_image_test, case)
                futures[future] = case

            for i, future in enumerate(as_completed(futures)):
                if not self.is_running:
                    break
                case = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.log(f"[文生图] {case['id']} {case['name']} - 成功")
                except Exception as e:
                    self.log(f"[文生图] {case['id']} {case['name']} - 失败: {str(e)}")
                    results.append({
                        "id": case["id"],
                        "name": case["name"],
                        "success": False,
                        "error": str(e)
                    })

                progress = 50 + (i + 1) / len(cases) * 50  # 文生图占后50%
                self.update_progress(progress)

        self.results["image"] = results
        return results

    def run_single_image_test(self, case):
        """执行单个文生图测试"""
        response = self.call_api(case["prompt"], self.image_model, is_image=True)

        content = response["choices"][0]["message"]["content"]

        # 提取并保存图片
        image_path = self.extract_and_save_image(content, case["id"], case["name"])

        # 保存响应（移除base64图片数据，避免文件过大，并包含所有测试案例元数据）
        output_file = self.output_dir / "image" / f"{case['id']}_{case['name']}.json"

        # 从content中移除base64数据
        clean_content = self.remove_base64_from_content(content)

        result = {
            "id": case["id"],
            "name": case["name"],
            "category": case.get("category", "未分类"),
            "difficulty": case.get("difficulty", "中"),
            "tags": case.get("tags", []),
            "icon": case.get("icon", "🖼️"),
            "prompt": case["prompt"],
            "response": clean_content,  # 保存清理后的内容
            "has_image": image_path is not None,
            "timestamp": datetime.now().isoformat(),
            "success": True
        }

        if image_path:
            result["image_file"] = str(image_path)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    def remove_base64_from_content(self, content):
        """从内容中移除base64数据，避免JSON文件过大"""
        # 移除base64图片数据
        patterns = [
            r'(data:image/(?:jpeg|png|jpg);base64,)[A-Za-z0-9+/=]{100,}',
        ]

        clean_content = content
        for pattern in patterns:
            clean_content = re.sub(pattern, r'\1[图片数据已移除]', clean_content)

        return clean_content

    def extract_and_save_image(self, content, case_id, case_name):
        """提取并保存base64图片"""
        # 匹配base64图片
        patterns = [
            r'data:image/(jpeg|png|jpg);base64,([A-Za-z0-9+/=]+)',
            r'!\[.*?\]\(data:image/(jpeg|png|jpg);base64,([A-Za-z0-9+/=]+)\)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                if len(match.groups()) == 2:
                    img_format, img_data = match.groups()
                else:
                    img_format = "png"
                    img_data = match.group(1)

                try:
                    img_bytes = base64.b64decode(img_data)
                    ext = "jpg" if img_format == "jpeg" else img_format
                    img_path = self.output_dir / "image" / f"{case_id}_{case_name}.{ext}"

                    with open(img_path, "wb") as f:
                        f.write(img_bytes)
                    return img_path
                except Exception as e:
                    self.log(f"保存图片失败: {str(e)}")

        return None
