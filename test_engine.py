# -*- coding: utf-8 -*-
"""
测试引擎 - 执行文生文和文生图测试（带重试机制）
版本 2.0
"""

import json
import requests
import base64
import re
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import wraps


def retry_on_failure(max_retries=3, base_delay=2, max_delay=30):
    """
    重试装饰器，支持指数退避

    Args:
        max_retries: 最大重试次数
        base_delay: 初始延迟时间（秒）
        max_delay: 最大延迟时间（秒）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt < max_retries:
                        # 指数退避 + 随机抖动
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)

                        # 获取日志函数（如果有）
                        log_func = None
                        if args and hasattr(args[0], 'log'):
                            log_func = args[0].log

                        if log_func:
                            log_func(f"    ⚠️ 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试...")

                        time.sleep(delay)
                    else:
                        raise last_exception

            raise last_exception
        return wrapper
    return decorator


class TestEngine:
    # 重试配置
    MAX_RETRIES = 3
    BASE_DELAY = 2
    MAX_DELAY = 30

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

    def call_api_with_retry(self, prompt, model, is_image=False, case_id=""):
        """
        调用API（带重试机制）

        Args:
            prompt: 提示词
            model: 模型名称
            is_image: 是否为图像生成
            case_id: 案例ID（用于日志）
        """
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
        last_exception = None

        for attempt in range(self.MAX_RETRIES + 1):
            if not self.is_running:
                raise Exception("测试已停止")

            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=300
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout as e:
                last_exception = Exception(f"请求超时: {str(e)}")
            except requests.exceptions.ConnectionError as e:
                last_exception = Exception(f"连接错误: {str(e)}")
            except requests.exceptions.HTTPError as e:
                # 检查是否是可重试的错误
                if response.status_code in [429, 500, 502, 503, 504]:
                    last_exception = Exception(f"HTTP错误 {response.status_code}: {str(e)}")
                else:
                    # 不可重试的错误，直接抛出
                    raise Exception(f"API调用失败: HTTP {response.status_code} - {str(e)}")
            except Exception as e:
                last_exception = Exception(f"未知错误: {str(e)}")

            # 重试逻辑
            if attempt < self.MAX_RETRIES:
                delay = min(self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), self.MAX_DELAY)
                self.log(f"    ⚠️ [{case_id}] 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试...")
                time.sleep(delay)

        raise Exception(f"API调用失败（已重试{self.MAX_RETRIES}次）: {str(last_exception)}")

    def run_text_tests(self):
        """执行文生文测试"""
        cases = self.load_test_cases("text")
        if not cases:
            return []

        self.log(f"开始文生文测试，共 {len(cases)} 个案例")
        results = []

        # 记录失败的案例，用于最后统计
        failed_cases = []

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
                    self.log(f"✅ [文生文] {case['id']} {case['name']} - 成功")
                except Exception as e:
                    error_msg = str(e)
                    self.log(f"❌ [文生文] {case['id']} {case['name']} - 失败: {error_msg}")
                    failed_result = {
                        "id": case["id"],
                        "name": case["name"],
                        "category": case.get("category", "未分类"),
                        "difficulty": case.get("difficulty", "中"),
                        "tags": case.get("tags", []),
                        "icon": case.get("icon", "📄"),
                        "prompt": case["prompt"],
                        "success": False,
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat()
                    }
                    results.append(failed_result)
                    failed_cases.append(case)

                progress = (i + 1) / len(cases) * 50
                self.update_progress(progress)

        # 如果有失败的案例，提示用户
        if failed_cases:
            self.log(f"⚠️ 文生文测试有 {len(failed_cases)} 个案例失败")

        self.results["text"] = results
        return results

    def run_single_text_test(self, case):
        """执行单个文生文测试（带重试）"""
        response = self.call_api_with_retry(
            case["prompt"],
            self.text_model,
            is_image=False,
            case_id=case["id"]
        )

        content = response["choices"][0]["message"]["content"]

        # 保存响应
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

        # 提取HTML
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
        failed_cases = []

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
                    self.log(f"✅ [文生图] {case['id']} {case['name']} - 成功")
                except Exception as e:
                    error_msg = str(e)
                    self.log(f"❌ [文生图] {case['id']} {case['name']} - 失败: {error_msg}")
                    failed_result = {
                        "id": case["id"],
                        "name": case["name"],
                        "category": case.get("category", "未分类"),
                        "difficulty": case.get("difficulty", "中"),
                        "tags": case.get("tags", []),
                        "icon": case.get("icon", "🖼️"),
                        "prompt": case["prompt"],
                        "success": False,
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat()
                    }
                    results.append(failed_result)
                    failed_cases.append(case)

                progress = 50 + (i + 1) / len(cases) * 50
                self.update_progress(progress)

        if failed_cases:
            self.log(f"⚠️ 文生图测试有 {len(failed_cases)} 个案例失败")

        self.results["image"] = results
        return results

    def run_single_image_test(self, case):
        """执行单个文生图测试（带重试）"""
        response = self.call_api_with_retry(
            case["prompt"],
            self.image_model,
            is_image=True,
            case_id=case["id"]
        )

        content = response["choices"][0]["message"]["content"]

        # 提取并保存图片
        image_path = self.extract_and_save_image(content, case["id"], case["name"])

        # 保存响应
        output_file = self.output_dir / "image" / f"{case['id']}_{case['name']}.json"
        clean_content = self.remove_base64_from_content(content)

        result = {
            "id": case["id"],
            "name": case["name"],
            "category": case.get("category", "未分类"),
            "difficulty": case.get("difficulty", "中"),
            "tags": case.get("tags", []),
            "icon": case.get("icon", "🖼️"),
            "prompt": case["prompt"],
            "response": clean_content,
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
        """从内容中移除base64数据"""
        patterns = [
            r'(data:image/(?:jpeg|png|jpg);base64,)[A-Za-z0-9+/=]{100,}',
        ]

        clean_content = content
        for pattern in patterns:
            clean_content = re.sub(pattern, r'\1[图片数据已移除]', clean_content)

        return clean_content

    def extract_and_save_image(self, content, case_id, case_name):
        """提取并保存base64图片"""
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

    def retry_failed_tests(self, test_type="all"):
        """
        重试失败的测试案例

        Args:
            test_type: "text", "image", 或 "all"
        """
        retry_count = 0

        if test_type in ["text", "all"]:
            failed_text = [r for r in self.results.get("text", []) if not r.get("success", True)]
            if failed_text:
                self.log(f"🔄 重试 {len(failed_text)} 个失败的文生文案例...")
                for result in failed_text:
                    case = {
                        "id": result["id"],
                        "name": result["name"],
                        "category": result.get("category", "未分类"),
                        "difficulty": result.get("difficulty", "中"),
                        "tags": result.get("tags", []),
                        "icon": result.get("icon", "📄"),
                        "prompt": result["prompt"]
                    }
                    try:
                        new_result = self.run_single_text_test(case)
                        # 更新结果
                        idx = next(i for i, r in enumerate(self.results["text"]) if r["id"] == case["id"])
                        self.results["text"][idx] = new_result
                        self.log(f"✅ [重试成功] {case['id']} {case['name']}")
                        retry_count += 1
                    except Exception as e:
                        self.log(f"❌ [重试失败] {case['id']} {case['name']}: {str(e)}")

        if test_type in ["image", "all"]:
            failed_image = [r for r in self.results.get("image", []) if not r.get("success", True)]
            if failed_image:
                self.log(f"🔄 重试 {len(failed_image)} 个失败的文生图案例...")
                for result in failed_image:
                    case = {
                        "id": result["id"],
                        "name": result["name"],
                        "category": result.get("category", "未分类"),
                        "difficulty": result.get("difficulty", "中"),
                        "tags": result.get("tags", []),
                        "icon": result.get("icon", "🖼️"),
                        "prompt": result["prompt"]
                    }
                    try:
                        new_result = self.run_single_image_test(case)
                        idx = next(i for i, r in enumerate(self.results["image"]) if r["id"] == case["id"])
                        self.results["image"][idx] = new_result
                        self.log(f"✅ [重试成功] {case['id']} {case['name']}")
                        retry_count += 1
                    except Exception as e:
                        self.log(f"❌ [重试失败] {case['id']} {case['name']}: {str(e)}")

        return retry_count
