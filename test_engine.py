# -*- coding: utf-8 -*-
"""
测试引擎 - 执行文生文和文生图测试（带重试机制）
版本 2.1 - 增强版：超时日志、tokens统计、耗时记录
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
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any


@dataclass
class TokenUsage:
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: 'TokenUsage'):
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


@dataclass
class TestStats:
    """测试统计信息"""
    total_cases: int = 0
    success_count: int = 0
    failed_count: int = 0
    html_extracted_count: int = 0
    no_html_count: int = 0
    total_tokens: TokenUsage = field(default_factory=TokenUsage)
    total_time_seconds: float = 0.0
    avg_time_per_case: float = 0.0
    timeout_count: int = 0
    retry_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "total_cases": self.total_cases,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "html_extracted_count": self.html_extracted_count,
            "no_html_count": self.no_html_count,
            "total_tokens": asdict(self.total_tokens),
            "total_time_seconds": round(self.total_time_seconds, 2),
            "avg_time_per_case": round(self.avg_time_per_case, 2),
            "timeout_count": self.timeout_count,
            "retry_count": self.retry_count
        }


class TestEngine:
    # 重试配置
    MAX_RETRIES = 3
    BASE_DELAY = 2
    MAX_DELAY = 30
    REQUEST_TIMEOUT = 1200  # 请求超时时间（秒）

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

        # 统计信息
        self.text_stats = TestStats()
        self.image_stats = TestStats()
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

        # 确保输出目录存在
        (self.output_dir / "text").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "image").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "website").mkdir(parents=True, exist_ok=True)

    def stop(self):
        """停止测试"""
        self.is_running = False

    def get_stats_summary(self) -> Dict:
        """获取统计摘要"""
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        return {
            "text_stats": self.text_stats.to_dict(),
            "image_stats": self.image_stats.to_dict(),
            "total_time_seconds": round(total_time, 2),
            "total_tokens": {
                "prompt_tokens": self.text_stats.total_tokens.prompt_tokens + self.image_stats.total_tokens.prompt_tokens,
                "completion_tokens": self.text_stats.total_tokens.completion_tokens + self.image_stats.total_tokens.completion_tokens,
                "total_tokens": self.text_stats.total_tokens.total_tokens + self.image_stats.total_tokens.total_tokens
            }
        }

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

    def call_api_with_retry(self, prompt, model, is_image=False, case_id="") -> Dict[str, Any]:
        """
        调用API（带重试机制）

        Args:
            prompt: 提示词
            model: 模型名称
            is_image: 是否为图像生成
            case_id: 案例ID（用于日志）

        Returns:
            包含响应内容、token使用量、耗时等信息的字典
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
        total_retry_count = 0
        request_start_time = time.time()

        for attempt in range(self.MAX_RETRIES + 1):
            if not self.is_running:
                raise Exception("测试已停止")

            attempt_start_time = time.time()
            try:
                self.log(f"    [{case_id}] 开始请求 (第{attempt + 1}次尝试)...")

                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT
                )

                attempt_duration = time.time() - attempt_start_time
                self.log(f"    [{case_id}] 请求完成，耗时 {attempt_duration:.1f}秒")

                response.raise_for_status()
                response_json = response.json()

                # 提取token使用量
                token_usage = TokenUsage()
                if "usage" in response_json:
                    usage = response_json["usage"]
                    token_usage.prompt_tokens = usage.get("prompt_tokens", 0)
                    token_usage.completion_tokens = usage.get("completion_tokens", 0)
                    token_usage.total_tokens = usage.get("total_tokens", 0)
                    self.log(f"    [{case_id}] Tokens: 输入={token_usage.prompt_tokens}, 输出={token_usage.completion_tokens}, 总计={token_usage.total_tokens}")

                total_duration = time.time() - request_start_time
                return {
                    "response": response_json,
                    "token_usage": token_usage,
                    "duration_seconds": round(total_duration, 2),
                    "retry_count": total_retry_count,
                    "success": True
                }

            except requests.exceptions.Timeout as e:
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"请求超时 ({self.REQUEST_TIMEOUT}秒): {str(e)}")
                self.log(f"    ⏰ [{case_id}] 请求超时! 已等待 {attempt_duration:.1f}秒 (超时限制: {self.REQUEST_TIMEOUT}秒)")

            except requests.exceptions.ConnectionError as e:
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"连接错误: {str(e)}")
                self.log(f"    🔌 [{case_id}] 连接错误，耗时 {attempt_duration:.1f}秒: {str(e)[:100]}")

            except requests.exceptions.HTTPError as e:
                attempt_duration = time.time() - attempt_start_time
                status_code = response.status_code if 'response' in locals() else 'unknown'

                # 检查是否是可重试的错误
                if isinstance(status_code, int) and status_code in [429, 500, 502, 503, 504]:
                    error_messages = {
                        429: "请求过于频繁",
                        500: "服务器内部错误",
                        502: "网关错误",
                        503: "服务暂时不可用",
                        504: "网关超时"
                    }
                    error_desc = error_messages.get(status_code, "HTTP错误")
                    last_exception = Exception(f"HTTP {status_code} ({error_desc}): {str(e)}")
                    self.log(f"    🚫 [{case_id}] HTTP {status_code} ({error_desc})，耗时 {attempt_duration:.1f}秒")
                else:
                    # 不可重试的错误，直接抛出
                    raise Exception(f"API调用失败: HTTP {status_code} - {str(e)}")

            except json.JSONDecodeError as e:
                last_exception = Exception(f"响应JSON解析失败: {str(e)}")
                self.log(f"    ❌ [{case_id}] 响应JSON解析失败: {str(e)[:100]}")

            except Exception as e:
                last_exception = Exception(f"未知错误: {str(e)}")
                self.log(f"    ❌ [{case_id}] 未知错误: {str(e)[:100]}")

            # 重试逻辑
            if attempt < self.MAX_RETRIES:
                total_retry_count += 1
                delay = min(self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), self.MAX_DELAY)
                self.log(f"    🔄 [{case_id}] 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试 (剩余{self.MAX_RETRIES - attempt}次)...")
                time.sleep(delay)

        total_duration = time.time() - request_start_time
        raise Exception(f"API调用失败（已重试{self.MAX_RETRIES}次，总耗时{total_duration:.1f}秒）: {str(last_exception)}")

    def run_text_tests(self):
        """执行文生文测试"""
        cases = self.load_test_cases("text")
        if not cases:
            self.log("未找到文生文测试用例")
            return []

        self.log(f"开始文生文测试，共 {len(cases)} 个案例，使用模型: {self.text_model}")
        self.text_stats = TestStats()
        self.text_stats.total_cases = len(cases)
        test_start_time = time.time()
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
                    self.text_stats.success_count += 1

                    # 统计tokens
                    if "token_usage" in result:
                        self.text_stats.total_tokens.add(result["token_usage"])

                    # 统计HTML提取情况
                    if result.get("html_file"):
                        self.text_stats.html_extracted_count += 1
                    elif result.get("txt_file"):
                        self.text_stats.no_html_count += 1

                    # 统计重试次数
                    self.text_stats.retry_count += result.get("retry_count", 0)

                    self.log(f"✅ [文生文] {case['id']} {case['name']} - 成功 (耗时{result.get('duration_seconds', 0)}秒)")
                except Exception as e:
                    error_msg = str(e)
                    self.text_stats.failed_count += 1

                    # 检测是否为超时错误
                    if "超时" in error_msg or "timeout" in error_msg.lower():
                        self.text_stats.timeout_count += 1

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

        # 计算统计信息
        self.text_stats.total_time_seconds = time.time() - test_start_time
        if self.text_stats.total_cases > 0:
            self.text_stats.avg_time_per_case = self.text_stats.total_time_seconds / self.text_stats.total_cases

        # 输出统计摘要
        self.log(f"📊 文生文测试完成:")
        self.log(f"    成功: {self.text_stats.success_count}/{self.text_stats.total_cases}")
        self.log(f"    HTML提取: {self.text_stats.html_extracted_count}, 未提取: {self.text_stats.no_html_count}")
        self.log(f"    总Tokens: {self.text_stats.total_tokens.total_tokens} (输入: {self.text_stats.total_tokens.prompt_tokens}, 输出: {self.text_stats.total_tokens.completion_tokens})")
        self.log(f"    总耗时: {self.text_stats.total_time_seconds:.1f}秒, 平均: {self.text_stats.avg_time_per_case:.1f}秒/案例")
        if self.text_stats.timeout_count > 0:
            self.log(f"    ⏰ 超时次数: {self.text_stats.timeout_count}")
        if self.text_stats.retry_count > 0:
            self.log(f"    🔄 重试次数: {self.text_stats.retry_count}")

        # 保存统计信息
        stats_file = self.output_dir / "text" / "_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(self.text_stats.to_dict(), f, ensure_ascii=False, indent=2)

        self.results["text"] = results
        return results

    def run_single_text_test(self, case) -> Dict[str, Any]:
        """执行单个文生文测试（带重试）"""
        api_result = self.call_api_with_retry(
            case["prompt"],
            self.text_model,
            is_image=False,
            case_id=case["id"]
        )

        response_json = api_result["response"]
        token_usage = api_result["token_usage"]
        duration_seconds = api_result["duration_seconds"]
        retry_count = api_result["retry_count"]

        # 安全提取内容 - 支持多种响应格式
        content = ""
        reasoning_content = ""
        raw_response = ""

        try:
            message = response_json.get("choices", [{}])[0].get("message", {})

            # 尝试获取常规content
            content = message.get("content") or ""

            # 尝试获取reasoning_content (deepseek-reasoner等推理模型)
            reasoning_content = message.get("reasoning_content") or ""

            # 如果content为空但reasoning_content有内容，使用reasoning_content
            if not content and reasoning_content:
                content = reasoning_content
                self.log(f"    📝 [{case['id']}] 使用reasoning_content作为响应内容")

            # 如果两者都为空，保存完整响应用于调试
            if not content and not reasoning_content:
                raw_response = json.dumps(response_json, ensure_ascii=False, indent=2)
                self.log(f"    ⚠️ [{case['id']}] content和reasoning_content均为空，保存原始响应")
                content = raw_response

        except (KeyError, IndexError, TypeError) as e:
            self.log(f"    ⚠️ [{case['id']}] 响应格式异常: {str(e)}")
            # 保存原始响应用于调试
            raw_response = json.dumps(response_json, ensure_ascii=False, indent=2)
            content = raw_response

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
            "reasoning_content": reasoning_content if reasoning_content else None,
            "timestamp": datetime.now().isoformat(),
            "success": True,
            # 新增字段
            "token_usage": asdict(token_usage),
            "duration_seconds": duration_seconds,
            "retry_count": retry_count,
            "model": self.text_model
        }

        # 如果有原始响应（说明解析异常），也保存
        if raw_response:
            result["raw_response"] = raw_response

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 提取HTML
        html_content = self.extract_html(content)
        if html_content:
            html_file = self.output_dir / "text" / f"{case['id']}_{case['name']}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            result["html_file"] = str(html_file)
        else:
            # 如果没有提取到HTML，保存原始响应到txt文件
            txt_file = self.output_dir / "text" / f"{case['id']}_{case['name']}_raw.txt"
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(content if content else raw_response if raw_response else "响应为空")
            result["txt_file"] = str(txt_file)
            result["html_extracted"] = False
            self.log(f"    ⚠️ [{case['id']}] 未能提取HTML，原始响应已保存到 {txt_file.name}")

        # 返回token_usage对象供统计使用
        result["token_usage"] = token_usage
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
            self.log("未找到文生图测试用例")
            return []

        self.log(f"开始文生图测试，共 {len(cases)} 个案例，使用模型: {self.image_model}")
        self.image_stats = TestStats()
        self.image_stats.total_cases = len(cases)
        test_start_time = time.time()
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
                    self.image_stats.success_count += 1

                    # 统计tokens
                    if "token_usage" in result:
                        self.image_stats.total_tokens.add(result["token_usage"])

                    # 统计图片提取情况
                    if result.get("has_image"):
                        self.image_stats.html_extracted_count += 1  # 复用字段表示图片提取成功
                    else:
                        self.image_stats.no_html_count += 1

                    # 统计重试次数
                    self.image_stats.retry_count += result.get("retry_count", 0)

                    self.log(f"✅ [文生图] {case['id']} {case['name']} - 成功 (耗时{result.get('duration_seconds', 0)}秒)")
                except Exception as e:
                    error_msg = str(e)
                    self.image_stats.failed_count += 1

                    # 检测是否为超时错误
                    if "超时" in error_msg or "timeout" in error_msg.lower():
                        self.image_stats.timeout_count += 1

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

        # 计算统计信息
        self.image_stats.total_time_seconds = time.time() - test_start_time
        if self.image_stats.total_cases > 0:
            self.image_stats.avg_time_per_case = self.image_stats.total_time_seconds / self.image_stats.total_cases

        # 输出统计摘要
        self.log(f"📊 文生图测试完成:")
        self.log(f"    成功: {self.image_stats.success_count}/{self.image_stats.total_cases}")
        self.log(f"    图片提取: {self.image_stats.html_extracted_count}, 未提取: {self.image_stats.no_html_count}")
        self.log(f"    总Tokens: {self.image_stats.total_tokens.total_tokens} (输入: {self.image_stats.total_tokens.prompt_tokens}, 输出: {self.image_stats.total_tokens.completion_tokens})")
        self.log(f"    总耗时: {self.image_stats.total_time_seconds:.1f}秒, 平均: {self.image_stats.avg_time_per_case:.1f}秒/案例")
        if self.image_stats.timeout_count > 0:
            self.log(f"    ⏰ 超时次数: {self.image_stats.timeout_count}")
        if self.image_stats.retry_count > 0:
            self.log(f"    🔄 重试次数: {self.image_stats.retry_count}")

        # 保存统计信息
        stats_file = self.output_dir / "image" / "_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(self.image_stats.to_dict(), f, ensure_ascii=False, indent=2)

        self.results["image"] = results
        return results

    def run_single_image_test(self, case) -> Dict[str, Any]:
        """执行单个文生图测试（带重试）"""
        api_result = self.call_api_with_retry(
            case["prompt"],
            self.image_model,
            is_image=True,
            case_id=case["id"]
        )

        response_json = api_result["response"]
        token_usage = api_result["token_usage"]
        duration_seconds = api_result["duration_seconds"]
        retry_count = api_result["retry_count"]

        # 安全提取内容 - 支持多种响应格式
        content = ""
        reasoning_content = ""
        raw_response = ""

        try:
            message = response_json.get("choices", [{}])[0].get("message", {})

            # 尝试获取常规content
            content = message.get("content") or ""

            # 尝试获取reasoning_content (deepseek-reasoner等推理模型)
            reasoning_content = message.get("reasoning_content") or ""

            # 如果content为空但reasoning_content有内容，使用reasoning_content
            if not content and reasoning_content:
                content = reasoning_content
                self.log(f"    📝 [{case['id']}] 使用reasoning_content作为响应内容")

            # 如果两者都为空，保存完整响应用于调试
            if not content and not reasoning_content:
                raw_response = json.dumps(response_json, ensure_ascii=False, indent=2)
                self.log(f"    ⚠️ [{case['id']}] content和reasoning_content均为空，保存原始响应")
                content = raw_response

        except (KeyError, IndexError, TypeError) as e:
            self.log(f"    ⚠️ [{case['id']}] 响应格式异常: {str(e)}")
            raw_response = json.dumps(response_json, ensure_ascii=False, indent=2)
            content = raw_response

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
            "reasoning_content": reasoning_content[:500] + "..." if len(reasoning_content) > 500 else reasoning_content if reasoning_content else None,
            "has_image": image_path is not None,
            "timestamp": datetime.now().isoformat(),
            "success": True,
            # 新增字段
            "token_usage": asdict(token_usage),
            "duration_seconds": duration_seconds,
            "retry_count": retry_count,
            "model": self.image_model
        }

        if image_path:
            result["image_file"] = str(image_path)
        else:
            # 如果没有提取到图片，保存原始响应到txt文件
            txt_file = self.output_dir / "image" / f"{case['id']}_{case['name']}_raw.txt"
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(content if content else raw_response if raw_response else "响应为空")
            result["txt_file"] = str(txt_file)
            self.log(f"    ⚠️ [{case['id']}] 未能提取图片，原始响应已保存到 {txt_file.name}")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 返回token_usage对象供统计使用
        result["token_usage"] = token_usage
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

    def save_summary_stats(self):
        """保存总体统计摘要"""
        self.end_time = time.time()
        summary = self.get_stats_summary()
        summary["timestamp"] = datetime.now().isoformat()
        summary["config"] = {
            "api_url": self.api_url,
            "text_model": self.text_model,
            "image_model": self.image_model,
            "max_threads": self.max_threads
        }

        stats_file = self.output_dir / "_summary_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        self.log(f"📊 总体统计已保存到 {stats_file.name}")
        return summary

    def run_all_tests(self):
        """执行所有测试并保存统计"""
        self.start_time = time.time()

        self.log("=" * 50)
        self.log("开始AI模型测评")
        self.log("=" * 50)

        # 执行文生文测试
        self.run_text_tests()

        # 执行文生图测试
        self.run_image_tests()

        # 保存总体统计
        summary = self.save_summary_stats()

        self.log("=" * 50)
        self.log("测评完成!")
        self.log(f"总耗时: {summary['total_time_seconds']}秒")
        self.log(f"总Tokens: {summary['total_tokens']['total_tokens']}")
        self.log("=" * 50)

        return self.results
