# -*- coding: utf-8 -*-
"""
测试引擎 - 执行代码生成、文生文和文生图测试（带重试机制）
版本 2.2 - 增强版：支持代码生成、写作能力、文生图三类测评
"""

import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    # Windows和Linux都不允许的字符
    invalid_chars = r'<>:"/\|?*'
    # 中文括号转英文括号
    name = name.replace('（', '(').replace('）', ')')
    # 替换非法字符为下划线
    for char in invalid_chars:
        name = name.replace(char, '_')
    # 去除首尾空格和点
    name = name.strip(' .')
    # 限制文件名长度
    if len(name) > 100:
        name = name[:100]
    return name


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
    total_time_seconds: float = 0.0  # 多线程总耗时（墙钟时间）
    sum_case_time_seconds: float = 0.0  # 单case耗时总和（真实累计时间）
    avg_time_per_case: float = 0.0  # 单case平均耗时
    avg_output_tokens_per_case: float = 0.0  # 单case平均输出tokens
    avg_tokens_per_second: float = 0.0  # 平均输出速率 (tokens/s)
    timeout_count: int = 0
    retry_count: int = 0
    incomplete_count: int = 0  # 输出不完整次数

    def to_dict(self) -> Dict:
        return {
            "total_cases": self.total_cases,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "html_extracted_count": self.html_extracted_count,
            "no_html_count": self.no_html_count,
            "total_tokens": asdict(self.total_tokens),
            "total_time_seconds": round(self.total_time_seconds, 2),
            "sum_case_time_seconds": round(self.sum_case_time_seconds, 2),
            "avg_time_per_case": round(self.avg_time_per_case, 2),
            "avg_output_tokens_per_case": round(self.avg_output_tokens_per_case, 2),
            "avg_tokens_per_second": round(self.avg_tokens_per_second, 2),
            "timeout_count": self.timeout_count,
            "retry_count": self.retry_count,
            "incomplete_count": self.incomplete_count
        }


class TestEngine:
    # 重试配置
    MAX_RETRIES = 3
    BASE_DELAY = 2
    MAX_DELAY = 30
    REQUEST_TIMEOUT = 1200  # 请求超时时间（秒）

    # 不完整响应检测配置
    INCOMPLETE_RETRY_MAX = 2  # 不完整响应最大重试次数
    CONTINUE_CONVERSATION_MAX = 3  # 连续对话最大轮数（用于续写被截断的内容）

    def __init__(self, api_url, api_key, text_model, image_model,
                 max_threads, output_dir, log_callback=None, progress_callback=None,
                 enable_thinking=False, max_tokens=None):
        """
        初始化测试引擎

        Args:
            api_url: API地址
            api_key: API密钥
            text_model: 文生文模型
            image_model: 文生图模型
            max_threads: 最大线程数
            output_dir: 输出目录
            log_callback: 日志回调
            progress_callback: 进度回调
            enable_thinking: 是否启用thinking模式（兼容DeepSeek等支持思维链的模型）
            max_tokens: 最大输出tokens，默认None表示使用最大值
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.text_model = text_model
        self.image_model = image_model
        self.max_threads = max_threads
        self.output_dir = Path(output_dir)
        self.log = log_callback or print
        self.update_progress = progress_callback or (lambda x: None)

        # thinking模式配置
        self.enable_thinking = enable_thinking
        # max_tokens：默认设置为较大值，兼容各家API
        self.max_tokens = max_tokens if max_tokens else 16384  # 默认16K，可配置

        self.is_running = True
        self.results = {"text": [], "image": [], "writing": []}

        # 统计信息
        self.text_stats = TestStats()
        self.image_stats = TestStats()
        self.writing_stats = TestStats()
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

        # 创建带有自动重试机制的HTTP Session
        self.session = self._create_robust_session()

        # 确保输出目录存在
        (self.output_dir / "text").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "image").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "writing").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "website").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "logs").mkdir(parents=True, exist_ok=True)

    def _create_robust_session(self) -> requests.Session:
        """创建带有自动重试和连接池的HTTP Session"""
        session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 总重试次数
            backoff_factor=1,  # 退避因子：1, 2, 4秒
            status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的状态码
            allowed_methods=["POST"],  # 允许重试的方法
            raise_on_status=False  # 不自动抛出异常，让我们手动处理
        )

        # 配置HTTP适配器
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,  # 连接池大小
            pool_maxsize=20,  # 最大连接数
            pool_block=False
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

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
        elif test_type == "writing":
            case_file = base_dir / "test_cases" / "writing_cases.json"
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
        调用API（带重试机制），自动兼容流式和非流式响应

        Args:
            prompt: 提示词
            model: 模型名称
            is_image: 是否为图像生成
            case_id: 案例ID（用于日志）

        Returns:
            包含响应内容、token使用量、耗时等信息的字典
        """
        # 首先尝试流式响应
        try:
            return self._call_api_streaming(prompt, model, is_image, case_id)
        except Exception as e:
            error_str = str(e).lower()
            # 判断是否应该切换到非流式模式
            # 1. 如果明确提示不支持流式
            # 2. 如果是SSE相关错误
            # 3. 如果已经重试多次仍然失败
            should_try_non_stream = any([
                "stream" in error_str and "not" in error_str,
                "sse" in error_str,
                "event-stream" in error_str,
                "chunk" in error_str and "invalid" in error_str,
                "已重试" in error_str  # 已经多次重试失败
            ])

            if should_try_non_stream:
                self.log(f"    💡 [{case_id}] 检测到流式响应不兼容，尝试非流式模式...")
                try:
                    return self._call_api_non_streaming(prompt, model, is_image, case_id)
                except Exception as non_stream_error:
                    # 如果非流式也失败，抛出更详细的错误
                    raise Exception(f"流式和非流式响应均失败。流式错误: {str(e)[:100]}; 非流式错误: {str(non_stream_error)[:100]}")
            else:
                # 如果不是流式相关问题，直接抛出原始错误
                raise

    def _call_api_streaming(self, prompt, model, is_image=False, case_id="") -> Dict[str, Any]:
        """流式API调用（原有逻辑）"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Expect": "",  # 禁用100-continue
            "Connection": "keep-alive",
            "Accept": "text/event-stream"  # SSE流式响应
        }

        # 构建payload，兼容OpenAI格式
        # 对于推理模型使用流式响应，避免中转服务超时
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "stream": True  # 启用流式响应，避免Response ended prematurely
        }

        # 添加thinking模式支持（兼容多种格式）
        if self.enable_thinking:
            # 方式1: DeepSeek V3.2风格
            payload["enable_thinking"] = True
            # 方式2: 也可以通过extra_body传递（某些SDK需要）
            # 这里直接在payload中添加，兼容更多情况

        endpoint = f"{self.api_url}/chat/completions"
        last_exception = None
        total_retry_count = 0
        incomplete_retry_count = 0
        request_start_time = time.time()

        for attempt in range(self.MAX_RETRIES + 1):
            if not self.is_running:
                raise Exception("测试已停止")

            attempt_start_time = time.time()
            response = None

            try:
                self.log(f"    [{case_id}] 开始请求 (第{attempt + 1}次尝试)...")

                # 使用流式响应避免中转服务超时
                response = self.session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=(30, self.REQUEST_TIMEOUT),
                    stream=True
                )

                response.raise_for_status()

                # 显式设置编码为UTF-8 (修复Windows乱码问题)
                response.encoding = 'utf-8'

                # 收集SSE流式响应数据
                collected_content = ""
                collected_reasoning = ""
                token_usage = TokenUsage()
                finish_reason = None

                for line in response.iter_lines(decode_unicode=True):
                    if not self.is_running:
                        raise Exception("测试已停止")

                    if not line:
                        continue

                    # SSE格式: data: {...}
                    if line.startswith("data: "):
                        data_str = line[6:]  # 去掉 "data: " 前缀

                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)

                            # 提取delta内容
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})

                                # 收集content
                                if "content" in delta and delta["content"]:
                                    collected_content += delta["content"]

                                # 收集reasoning_content (DeepSeek推理模型)
                                if "reasoning_content" in delta and delta["reasoning_content"]:
                                    collected_reasoning += delta["reasoning_content"]

                                # 获取finish_reason
                                if chunk["choices"][0].get("finish_reason"):
                                    finish_reason = chunk["choices"][0]["finish_reason"]

                            # 提取usage (某些API在最后一个chunk返回)
                            if "usage" in chunk and chunk["usage"]:
                                usage = chunk["usage"]
                                token_usage.prompt_tokens = usage.get("prompt_tokens", 0)
                                token_usage.completion_tokens = usage.get("completion_tokens", 0)
                                token_usage.total_tokens = usage.get("total_tokens", 0)

                        except json.JSONDecodeError:
                            continue

                attempt_duration = time.time() - attempt_start_time
                self.log(f"    [{case_id}] 请求完成，耗时 {attempt_duration:.1f}秒")

                # 如果content为空但reasoning_content有内容，使用reasoning_content
                if not collected_content and collected_reasoning:
                    collected_content = collected_reasoning
                    self.log(f"    📝 [{case_id}] 使用reasoning_content作为响应内容")

                # 构建兼容的response_json格式
                response_json = {
                    "choices": [{
                        "message": {
                            "content": collected_content,
                            "reasoning_content": collected_reasoning if collected_reasoning else None
                        },
                        "finish_reason": finish_reason
                    }],
                    "usage": {
                        "prompt_tokens": token_usage.prompt_tokens,
                        "completion_tokens": token_usage.completion_tokens,
                        "total_tokens": token_usage.total_tokens
                    }
                }

                # 如果没有从流中获取到usage，估算tokens
                if token_usage.total_tokens == 0:
                    # 粗略估算：4个字符约等于1个token
                    estimated_completion = len(collected_content + collected_reasoning) // 4
                    token_usage.completion_tokens = estimated_completion
                    token_usage.total_tokens = estimated_completion
                    self.log(f"    [{case_id}] Tokens (估算): 输出≈{estimated_completion}")
                else:
                    self.log(f"    [{case_id}] Tokens: 输入={token_usage.prompt_tokens}, 输出={token_usage.completion_tokens}, 总计={token_usage.total_tokens}")

                # 检查响应完整性（finish_reason）
                is_incomplete = False
                if finish_reason == "length":
                    is_incomplete = True
                    self.log(f"    ⚠️ [{case_id}] 输出达到max_tokens上限被截断 (finish_reason=length)")
                    self.log(f"    💡 [{case_id}] 提示: 截断无法通过重试解决，将检查HTML是否已完整")

                # 计算输出速率
                tokens_per_second = 0.0
                if attempt_duration > 0 and token_usage.completion_tokens > 0:
                    tokens_per_second = token_usage.completion_tokens / attempt_duration
                    self.log(f"    [{case_id}] 输出速率: {tokens_per_second:.1f} tokens/s")

                # 注意: 不对length截断进行重试，因为重试不能解决max_tokens限制问题
                # 后续会在HTML提取时检测内容是否完整

                total_duration = time.time() - request_start_time
                return {
                    "response": response_json,
                    "token_usage": token_usage,
                    "duration_seconds": round(total_duration, 2),
                    "retry_count": total_retry_count,
                    "incomplete_retry_count": incomplete_retry_count,
                    "is_incomplete": is_incomplete,
                    "finish_reason": finish_reason,
                    "tokens_per_second": round(tokens_per_second, 2),
                    "success": True
                }

            except requests.exceptions.Timeout as e:
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"请求超时 ({self.REQUEST_TIMEOUT}秒): {str(e)}")
                self.log(f"    ⏰ [{case_id}] 请求超时! 已等待 {attempt_duration:.1f}秒 (超时限制: {self.REQUEST_TIMEOUT}秒)")

            except requests.exceptions.ChunkedEncodingError as e:
                # 处理 "Response ended prematurely" 错误
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"响应传输中断: {str(e)}")
                self.log(f"    📡 [{case_id}] 响应传输中断 (Response ended prematurely)，耗时 {attempt_duration:.1f}秒")
                self.log(f"    💡 [{case_id}] 这通常是服务器负载过高导致的，将增加延迟后重试")

            except requests.exceptions.ConnectionError as e:
                attempt_duration = time.time() - attempt_start_time
                error_str = str(e)
                # 检测是否是 Response ended prematurely 类型的错误
                if "ended prematurely" in error_str.lower() or "incomplete" in error_str.lower():
                    last_exception = Exception(f"响应传输中断: {error_str}")
                    self.log(f"    📡 [{case_id}] 响应传输中断，耗时 {attempt_duration:.1f}秒")
                else:
                    last_exception = Exception(f"连接错误: {error_str}")
                    self.log(f"    🔌 [{case_id}] 连接错误，耗时 {attempt_duration:.1f}秒: {error_str[:100]}")

            except requests.exceptions.HTTPError as e:
                attempt_duration = time.time() - attempt_start_time
                status_code = response.status_code if response is not None else 'unknown'

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
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"响应JSON解析失败: {str(e)}")
                self.log(f"    ❌ [{case_id}] 响应JSON解析失败: {str(e)[:100]}")
                # 如果能获取到响应文本，记录下来便于调试
                if response is not None:
                    try:
                        raw_text = response.text[:500] if response.text else "空响应"
                        self.log(f"    📋 [{case_id}] 原始响应: {raw_text}")
                    except:
                        pass

            except Exception as e:
                attempt_duration = time.time() - attempt_start_time
                error_str = str(e)
                # 检测常见的网络中断错误
                if any(keyword in error_str.lower() for keyword in ["prematurely", "incomplete", "broken pipe", "reset by peer"]):
                    last_exception = Exception(f"网络传输中断: {error_str}")
                    self.log(f"    📡 [{case_id}] 网络传输中断，耗时 {attempt_duration:.1f}秒: {error_str[:100]}")
                else:
                    last_exception = Exception(f"未知错误: {error_str}")
                    self.log(f"    ❌ [{case_id}] 未知错误: {error_str[:100]}")

            # 重试逻辑 - 增加延迟时间
            if attempt < self.MAX_RETRIES:
                total_retry_count += 1
                # 使用更长的基础延迟，特别是对于网络中断错误
                base_delay = self.BASE_DELAY * 2 if "传输中断" in str(last_exception) or "prematurely" in str(last_exception).lower() else self.BASE_DELAY
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 2), self.MAX_DELAY)
                self.log(f"    🔄 [{case_id}] 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试 (剩余{self.MAX_RETRIES - attempt}次)...")
                time.sleep(delay)

        total_duration = time.time() - request_start_time
        # 记录失败日志到文件
        self._log_failure(case_id, prompt, model, last_exception, total_duration)
        raise Exception(f"API调用失败（已重试{self.MAX_RETRIES}次，总耗时{total_duration:.1f}秒）: {str(last_exception)}")

    def _call_api_non_streaming(self, prompt, model, is_image=False, case_id="") -> Dict[str, Any]:
        """非流式API调用（兼容更多模型）"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "stream": False  # 非流式响应
        }

        # 可选：添加thinking模式（某些模型可能不支持）
        if self.enable_thinking:
            payload["enable_thinking"] = True

        endpoint = f"{self.api_url}/chat/completions"
        last_exception = None
        total_retry_count = 0
        request_start_time = time.time()

        for attempt in range(self.MAX_RETRIES + 1):
            if not self.is_running:
                raise Exception("测试已停止")

            attempt_start_time = time.time()
            response = None

            try:
                self.log(f"    [{case_id}] 开始非流式请求 (第{attempt + 1}次尝试)...")

                response = self.session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=(30, self.REQUEST_TIMEOUT)
                )

                response.raise_for_status()

                # 显式设置编码为UTF-8 (修复Windows乱码问题)
                response.encoding = 'utf-8'

                attempt_duration = time.time() - attempt_start_time
                self.log(f"    [{case_id}] 请求完成，耗时 {attempt_duration:.1f}秒")

                # 解析JSON响应
                response_json = response.json()

                # 兼容多种响应格式
                content = ""
                reasoning_content = ""
                finish_reason = None
                token_usage = TokenUsage()

                # 提取choices和message
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    choice = response_json["choices"][0]

                    # 提取message内容
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    reasoning_content = message.get("reasoning_content", "")

                    # 提取finish_reason
                    finish_reason = choice.get("finish_reason")

                # 如果content为空但reasoning_content有内容，使用reasoning_content
                if not content and reasoning_content:
                    content = reasoning_content
                    self.log(f"    📝 [{case_id}] 使用reasoning_content作为响应内容")

                # 提取usage
                if "usage" in response_json:
                    usage = response_json["usage"]
                    token_usage.prompt_tokens = usage.get("prompt_tokens", 0)
                    token_usage.completion_tokens = usage.get("completion_tokens", 0)
                    token_usage.total_tokens = usage.get("total_tokens", 0)

                # 如果没有usage信息，估算tokens
                if token_usage.total_tokens == 0:
                    estimated_completion = len(content + reasoning_content) // 4
                    token_usage.completion_tokens = estimated_completion
                    token_usage.total_tokens = estimated_completion
                    self.log(f"    [{case_id}] Tokens (估算): 输出≈{estimated_completion}")
                else:
                    self.log(f"    [{case_id}] Tokens: 输入={token_usage.prompt_tokens}, 输出={token_usage.completion_tokens}, 总计={token_usage.total_tokens}")

                # 检查响应完整性
                is_incomplete = False
                if finish_reason == "length":
                    is_incomplete = True
                    self.log(f"    ⚠️ [{case_id}] 输出达到max_tokens上限被截断")

                # 计算输出速率
                tokens_per_second = 0.0
                if attempt_duration > 0 and token_usage.completion_tokens > 0:
                    tokens_per_second = token_usage.completion_tokens / attempt_duration
                    self.log(f"    [{case_id}] 输出速率: {tokens_per_second:.1f} tokens/s")

                total_duration = time.time() - request_start_time
                return {
                    "response": response_json,
                    "token_usage": token_usage,
                    "duration_seconds": round(total_duration, 2),
                    "retry_count": total_retry_count,
                    "incomplete_retry_count": 0,
                    "is_incomplete": is_incomplete,
                    "finish_reason": finish_reason,
                    "tokens_per_second": round(tokens_per_second, 2),
                    "success": True
                }

            except requests.exceptions.Timeout as e:
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"请求超时: {str(e)}")
                self.log(f"    ⏰ [{case_id}] 请求超时! 已等待 {attempt_duration:.1f}秒")

            except requests.exceptions.HTTPError as e:
                attempt_duration = time.time() - attempt_start_time
                status_code = response.status_code if response is not None else 'unknown'

                # 记录详细错误信息
                error_body = ""
                try:
                    if response is not None and response.text:
                        error_body = response.text[:500]
                        self.log(f"    📋 [{case_id}] 错误响应: {error_body}")
                except:
                    pass

                # 可重试的错误
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
                    self.log(f"    🚫 [{case_id}] HTTP {status_code} ({error_desc})")
                else:
                    # 不可重试的错误
                    raise Exception(f"API调用失败: HTTP {status_code} - {error_body if error_body else str(e)}")

            except json.JSONDecodeError as e:
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"响应JSON解析失败: {str(e)}")
                self.log(f"    ❌ [{case_id}] 响应JSON解析失败")
                if response is not None:
                    try:
                        raw_text = response.text[:500] if response.text else "空响应"
                        self.log(f"    📋 [{case_id}] 原始响应: {raw_text}")
                    except:
                        pass

            except Exception as e:
                attempt_duration = time.time() - attempt_start_time
                last_exception = Exception(f"未知错误: {str(e)}")
                self.log(f"    ❌ [{case_id}] 未知错误: {str(e)[:100]}")

            # 重试逻辑
            if attempt < self.MAX_RETRIES:
                total_retry_count += 1
                delay = min(self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 2), self.MAX_DELAY)
                self.log(f"    🔄 [{case_id}] 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试...")
                time.sleep(delay)

        total_duration = time.time() - request_start_time
        # 记录失败日志到文件
        self._log_failure(case_id, prompt, model, last_exception, total_duration)
        raise Exception(f"非流式API调用失败（已重试{self.MAX_RETRIES}次，总耗时{total_duration:.1f}秒）: {str(last_exception)}")

    def _log_failure(self, case_id, prompt, model, exception, duration):
        """记录失败日志到文件"""
        try:
            log_dir = self.output_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"failures_{datetime.now().strftime('%Y%m%d')}.log"

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"时间: {datetime.now().isoformat()}\n")
                f.write(f"案例ID: {case_id}\n")
                f.write(f"模型: {model}\n")
                f.write(f"耗时: {duration:.1f}秒\n")
                f.write(f"错误: {str(exception)}\n")
                f.write(f"提示词前100字: {prompt[:100]}...\n")
                f.write(f"{'='*80}\n")
        except Exception as e:
            self.log(f"    ⚠️ 写入失败日志失败: {str(e)}")

    def continue_conversation(self, messages: List[Dict], model: str, case_id: str = "") -> Dict[str, Any]:
        """
        连续对话 - 用于续写被截断的内容（带重试）

        Args:
            messages: 对话历史
            model: 模型名称
            case_id: 案例ID（用于日志）

        Returns:
            包含响应内容、token使用量等信息的字典
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Expect": "",
            "Connection": "keep-alive",
            "Accept": "text/event-stream"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": True  # 启用流式响应
        }

        if self.enable_thinking:
            payload["enable_thinking"] = True

        endpoint = f"{self.api_url}/chat/completions"

        # 续写请求也支持重试
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                self.log(f"    🔄 [{case_id}] 发送续写请求 (第{attempt + 1}次)...")
                start_time = time.time()

                response = self.session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=(30, self.REQUEST_TIMEOUT),
                    stream=True
                )

                response.raise_for_status()

                # 显式设置编码为UTF-8 (修复Windows乱码问题)
                response.encoding = 'utf-8'

                # 收集SSE流式响应数据
                collected_content = ""
                token_usage = TokenUsage()
                finish_reason = None

                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]

                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)

                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})

                                if "content" in delta and delta["content"]:
                                    collected_content += delta["content"]

                                if "reasoning_content" in delta and delta["reasoning_content"]:
                                    collected_content += delta["reasoning_content"]

                                if chunk["choices"][0].get("finish_reason"):
                                    finish_reason = chunk["choices"][0]["finish_reason"]

                            if "usage" in chunk and chunk["usage"]:
                                usage = chunk["usage"]
                                token_usage.prompt_tokens = usage.get("prompt_tokens", 0)
                                token_usage.completion_tokens = usage.get("completion_tokens", 0)
                                token_usage.total_tokens = usage.get("total_tokens", 0)

                        except json.JSONDecodeError:
                            continue

                duration = time.time() - start_time
                self.log(f"    🔄 [{case_id}] 续写完成，耗时 {duration:.1f}秒，输出 {token_usage.completion_tokens} tokens")

                return {
                    "content": collected_content,
                    "token_usage": token_usage,
                    "duration_seconds": round(duration, 2),
                    "finish_reason": finish_reason,
                    "success": True
                }

            except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as e:
                error_str = str(e)
                if attempt < max_retries:
                    delay = (attempt + 1) * 5  # 5, 10秒
                    self.log(f"    📡 [{case_id}] 续写传输中断，{delay}秒后重试...")
                    time.sleep(delay)
                else:
                    self.log(f"    ❌ [{case_id}] 续写请求失败: {error_str[:100]}")
                    return {
                        "content": "",
                        "token_usage": TokenUsage(),
                        "duration_seconds": 0,
                        "finish_reason": "error",
                        "success": False
                    }

            except Exception as e:
                self.log(f"    ❌ [{case_id}] 续写请求失败: {str(e)[:100]}")
                return {
                    "content": "",
                    "token_usage": TokenUsage(),
                    "duration_seconds": 0,
                    "finish_reason": "error",
                    "success": False
                }

        return {
            "content": "",
            "token_usage": TokenUsage(),
            "duration_seconds": 0,
            "finish_reason": "error",
            "success": False
        }

    def run_text_tests(self):
        """执行代码生成测试"""
        cases = self.load_test_cases("text")
        if not cases:
            self.log("未找到代码生成测试用例")
            return []

        self.log(f"开始代码生成测试，共 {len(cases)} 个案例，使用模型: {self.text_model}")
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

                    # 累加单case实际耗时（用于计算真实平均值）
                    case_duration = result.get("duration_seconds", 0)
                    self.text_stats.sum_case_time_seconds += case_duration

                    # 统计HTML提取情况
                    if result.get("html_file"):
                        self.text_stats.html_extracted_count += 1
                    elif result.get("txt_file"):
                        self.text_stats.no_html_count += 1

                    # 统计重试次数
                    self.text_stats.retry_count += result.get("retry_count", 0)

                    # 统计不完整响应
                    if result.get("is_incomplete"):
                        self.text_stats.incomplete_count += 1

                    self.log(f"✅ [代码生成] {case['id']} {case['name']} - 成功 (耗时{case_duration}秒, {result.get('tokens_per_second', 0):.1f} tok/s)")
                except Exception as e:
                    error_msg = str(e)
                    self.text_stats.failed_count += 1

                    # 检测是否为超时错误
                    if "超时" in error_msg or "timeout" in error_msg.lower():
                        self.text_stats.timeout_count += 1

                    self.log(f"❌ [代码生成] {case['id']} {case['name']} - 失败: {error_msg}")
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
        if self.text_stats.success_count > 0:
            # 使用单case实际耗时总和计算平均值（正确反映单case能力）
            self.text_stats.avg_time_per_case = self.text_stats.sum_case_time_seconds / self.text_stats.success_count
            # 计算平均输出tokens
            self.text_stats.avg_output_tokens_per_case = self.text_stats.total_tokens.completion_tokens / self.text_stats.success_count
            # 计算平均输出速率
            if self.text_stats.sum_case_time_seconds > 0:
                self.text_stats.avg_tokens_per_second = self.text_stats.total_tokens.completion_tokens / self.text_stats.sum_case_time_seconds

        # 输出统计摘要
        self.log(f"📊 代码生成测试完成:")
        self.log(f"    成功: {self.text_stats.success_count}/{self.text_stats.total_cases}")
        self.log(f"    HTML提取: {self.text_stats.html_extracted_count}, 未提取: {self.text_stats.no_html_count}")
        self.log(f"    总Tokens: {self.text_stats.total_tokens.total_tokens} (输入: {self.text_stats.total_tokens.prompt_tokens}, 输出: {self.text_stats.total_tokens.completion_tokens})")
        self.log(f"    多线程总耗时: {self.text_stats.total_time_seconds:.1f}秒")
        self.log(f"    单case平均耗时: {self.text_stats.avg_time_per_case:.1f}秒 (基于{self.text_stats.success_count}个成功案例)")
        self.log(f"    单case平均输出: {self.text_stats.avg_output_tokens_per_case:.0f} tokens")
        self.log(f"    平均输出速率: {self.text_stats.avg_tokens_per_second:.1f} tokens/s")
        if self.text_stats.timeout_count > 0:
            self.log(f"    ⏰ 超时次数: {self.text_stats.timeout_count}")
        if self.text_stats.retry_count > 0:
            self.log(f"    🔄 重试次数: {self.text_stats.retry_count}")
        if self.text_stats.incomplete_count > 0:
            self.log(f"    ⚠️ 不完整响应: {self.text_stats.incomplete_count}")

        # 保存统计信息
        stats_file = self.output_dir / "text" / "_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(self.text_stats.to_dict(), f, ensure_ascii=False, indent=2)

        self.results["text"] = results
        return results

    def run_single_text_test(self, case) -> Dict[str, Any]:
        """执行单个代码生成测试（带重试）"""
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
        tokens_per_second = api_result.get("tokens_per_second", 0)
        is_incomplete = api_result.get("is_incomplete", False)
        finish_reason = api_result.get("finish_reason", "")

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

        # 保存响应（清理文件名中的非法字符）
        safe_name = sanitize_filename(case['name'])
        output_file = self.output_dir / "text" / f"{case['id']}_{safe_name}.json"
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
            "tokens_per_second": tokens_per_second,
            "is_incomplete": is_incomplete,
            "finish_reason": finish_reason,
            "model": self.text_model
        }

        # 如果有原始响应（说明解析异常），也保存
        if raw_response:
            result["raw_response"] = raw_response

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 提取HTML
        html_content, html_is_complete = self.extract_html(content)

        # 如果HTML不完整，尝试使用连续对话续写
        if html_content and not html_is_complete and is_incomplete:
            self.log(f"    🔄 [{case['id']}] HTML不完整，尝试连续对话续写...")

            # 构建对话历史
            messages = [
                {"role": "user", "content": case["prompt"]},
                {"role": "assistant", "content": content},
                {"role": "user", "content": "请继续输出，从上次截断的地方继续，不要重复已输出的内容，直接输出剩余的代码部分。"}
            ]

            combined_content = content
            total_continuation_tokens = TokenUsage()
            total_continuation_time = 0

            for round_num in range(self.CONTINUE_CONVERSATION_MAX):
                if not self.is_running:
                    break

                continuation = self.continue_conversation(messages, self.text_model, case["id"])

                if not continuation["success"] or not continuation["content"]:
                    self.log(f"    ⚠️ [{case['id']}] 第{round_num + 1}轮续写失败或无内容")
                    break

                # 累加续写内容
                combined_content += "\n" + continuation["content"]
                total_continuation_tokens.add(continuation["token_usage"])
                total_continuation_time += continuation["duration_seconds"]

                # 更新对话历史
                messages.append({"role": "assistant", "content": continuation["content"]})
                messages.append({"role": "user", "content": "请继续输出，从上次截断的地方继续。"})

                # 检查是否已完整
                _, new_html_is_complete = self.extract_html(combined_content)
                if new_html_is_complete:
                    self.log(f"    ✅ [{case['id']}] 经过{round_num + 1}轮续写，HTML已完整")
                    html_content, html_is_complete = self.extract_html(combined_content)
                    # 更新统计
                    token_usage.add(total_continuation_tokens)
                    duration_seconds += total_continuation_time
                    result["response"] = combined_content
                    result["continuation_rounds"] = round_num + 1
                    break

                # 如果这轮续写也被截断了，继续下一轮
                if continuation["finish_reason"] == "length":
                    self.log(f"    🔄 [{case['id']}] 第{round_num + 1}轮续写仍被截断，继续...")
                else:
                    # 如果不是因为length截断，可能是正常结束但没有完整的HTML
                    self.log(f"    ⚠️ [{case['id']}] 第{round_num + 1}轮续写结束 (finish_reason={continuation['finish_reason']})")
                    break

            # 最终再次提取HTML
            html_content, html_is_complete = self.extract_html(combined_content)

        if html_content:
            html_file = self.output_dir / "text" / f"{case['id']}_{safe_name}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            result["html_file"] = str(html_file)
            result["html_complete"] = html_is_complete

            # 如果API返回了截断标记但HTML实际上是完整的，更新状态
            if is_incomplete and html_is_complete:
                result["is_incomplete"] = False
                self.log(f"    ✅ [{case['id']}] HTML已完整提取")
            elif not html_is_complete:
                result["is_incomplete"] = True
                self.log(f"    ⚠️ [{case['id']}] HTML仍不完整（缺少</html>结束标签）")
        else:
            # 如果没有提取到HTML，保存原始响应到txt文件
            txt_file = self.output_dir / "text" / f"{case['id']}_{safe_name}_raw.txt"
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(content if content else raw_response if raw_response else "响应为空")
            result["txt_file"] = str(txt_file)
            result["html_extracted"] = False
            self.log(f"    ⚠️ [{case['id']}] 未能提取HTML，原始响应已保存到 {txt_file.name}")

        # 返回token_usage对象供统计使用
        result["token_usage"] = token_usage
        return result

    def extract_html(self, content):
        """
        从响应中提取HTML代码

        Returns:
            tuple: (html_content, is_complete)
                   html_content: 提取的HTML内容，如果没有则为None
                   is_complete: HTML是否完整（以</html>结尾）
        """
        # 首先尝试匹配完整的HTML
        patterns_complete = [
            r'```html\n(.*?</html>)\s*\n```',
            r'```\n(<!DOCTYPE html>.*?</html>)\s*\n```',
            r'(<!DOCTYPE html>.*?</html>)',
        ]

        for pattern in patterns_complete:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                html = match.group(1).strip()
                return html, True  # 完整的HTML

        # 如果没有完整的HTML，尝试提取可能被截断的HTML
        patterns_partial = [
            r'```html\n(<!DOCTYPE html>.*?)(?:\n```|$)',  # 代码块中的HTML，可能没有结束标签
            r'```html\n(<html.*?)(?:\n```|$)',
            r'(<!DOCTYPE html>.*?)$',  # 从开头到结尾
        ]

        for pattern in patterns_partial:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                html = match.group(1).strip()
                # 检查是否以</html>结尾
                is_complete = html.lower().rstrip().endswith('</html>')
                return html, is_complete

        return None, False

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

                    # 累加单case实际耗时
                    case_duration = result.get("duration_seconds", 0)
                    self.image_stats.sum_case_time_seconds += case_duration

                    # 统计图片提取情况
                    if result.get("has_image"):
                        self.image_stats.html_extracted_count += 1  # 复用字段表示图片提取成功
                    else:
                        self.image_stats.no_html_count += 1

                    # 统计重试次数
                    self.image_stats.retry_count += result.get("retry_count", 0)

                    # 统计不完整响应
                    if result.get("is_incomplete"):
                        self.image_stats.incomplete_count += 1

                    self.log(f"✅ [文生图] {case['id']} {case['name']} - 成功 (耗时{case_duration}秒, {result.get('tokens_per_second', 0):.1f} tok/s)")
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
        if self.image_stats.success_count > 0:
            # 使用单case实际耗时总和计算平均值
            self.image_stats.avg_time_per_case = self.image_stats.sum_case_time_seconds / self.image_stats.success_count
            # 计算平均输出tokens
            self.image_stats.avg_output_tokens_per_case = self.image_stats.total_tokens.completion_tokens / self.image_stats.success_count
            # 计算平均输出速率
            if self.image_stats.sum_case_time_seconds > 0:
                self.image_stats.avg_tokens_per_second = self.image_stats.total_tokens.completion_tokens / self.image_stats.sum_case_time_seconds

        # 输出统计摘要
        self.log(f"📊 文生图测试完成:")
        self.log(f"    成功: {self.image_stats.success_count}/{self.image_stats.total_cases}")
        self.log(f"    图片提取: {self.image_stats.html_extracted_count}, 未提取: {self.image_stats.no_html_count}")
        self.log(f"    总Tokens: {self.image_stats.total_tokens.total_tokens} (输入: {self.image_stats.total_tokens.prompt_tokens}, 输出: {self.image_stats.total_tokens.completion_tokens})")
        self.log(f"    多线程总耗时: {self.image_stats.total_time_seconds:.1f}秒")
        self.log(f"    单case平均耗时: {self.image_stats.avg_time_per_case:.1f}秒 (基于{self.image_stats.success_count}个成功案例)")
        self.log(f"    单case平均输出: {self.image_stats.avg_output_tokens_per_case:.0f} tokens")
        self.log(f"    平均输出速率: {self.image_stats.avg_tokens_per_second:.1f} tokens/s")
        if self.image_stats.timeout_count > 0:
            self.log(f"    ⏰ 超时次数: {self.image_stats.timeout_count}")
        if self.image_stats.retry_count > 0:
            self.log(f"    🔄 重试次数: {self.image_stats.retry_count}")
        if self.image_stats.incomplete_count > 0:
            self.log(f"    ⚠️ 不完整响应: {self.image_stats.incomplete_count}")

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
        tokens_per_second = api_result.get("tokens_per_second", 0)
        is_incomplete = api_result.get("is_incomplete", False)
        finish_reason = api_result.get("finish_reason", "")

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

        # 提取并保存图片（清理文件名中的非法字符）
        safe_name = sanitize_filename(case["name"])
        image_path = self.extract_and_save_image(content, case["id"], safe_name)

        # 保存响应
        output_file = self.output_dir / "image" / f"{case['id']}_{safe_name}.json"
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
            "tokens_per_second": tokens_per_second,
            "is_incomplete": is_incomplete,
            "finish_reason": finish_reason,
            "model": self.image_model
        }

        if image_path:
            result["image_file"] = str(image_path)
        else:
            # 如果没有提取到图片，保存原始响应到txt文件
            txt_file = self.output_dir / "image" / f"{case['id']}_{safe_name}_raw.txt"
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

    def run_writing_tests(self):
        """执行文生文（写作能力）测试"""
        cases = self.load_test_cases("writing")
        if not cases:
            self.log("未找到文生文测试用例")
            return []

        self.log(f"开始文生文测试，共 {len(cases)} 个案例，使用模型: {self.text_model}")
        self.writing_stats = TestStats()
        self.writing_stats.total_cases = len(cases)
        test_start_time = time.time()
        results = []

        # 记录失败的案例
        failed_cases = []

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = {}
            for case in cases:
                if not self.is_running:
                    break
                future = executor.submit(self.run_single_writing_test, case)
                futures[future] = case

            for i, future in enumerate(as_completed(futures)):
                if not self.is_running:
                    break
                case = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.writing_stats.success_count += 1

                    # 统计tokens
                    if "token_usage" in result:
                        self.writing_stats.total_tokens.add(result["token_usage"])

                    # 累加单case实际耗时
                    case_duration = result.get("duration_seconds", 0)
                    self.writing_stats.sum_case_time_seconds += case_duration

                    # 统计重试次数
                    self.writing_stats.retry_count += result.get("retry_count", 0)

                    # 统计不完整响应
                    if result.get("is_incomplete"):
                        self.writing_stats.incomplete_count += 1

                    self.log(f"✅ [文生文] {case['id']} {case['name']} - 成功 (耗时{case_duration}秒, {result.get('tokens_per_second', 0):.1f} tok/s)")
                except Exception as e:
                    error_msg = str(e)
                    self.writing_stats.failed_count += 1

                    # 检测是否为超时错误
                    if "超时" in error_msg or "timeout" in error_msg.lower():
                        self.writing_stats.timeout_count += 1

                    self.log(f"❌ [文生文] {case['id']} {case['name']} - 失败: {error_msg}")
                    failed_result = {
                        "id": case["id"],
                        "name": case["name"],
                        "category": case.get("category", "未分类"),
                        "difficulty": case.get("difficulty", "中"),
                        "tags": case.get("tags", []),
                        "icon": case.get("icon", "📝"),
                        "prompt": case["prompt"],
                        "success": False,
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat()
                    }
                    results.append(failed_result)
                    failed_cases.append(case)

                progress = (i + 1) / len(cases) * 100
                self.update_progress(progress)

        # 计算统计信息
        self.writing_stats.total_time_seconds = time.time() - test_start_time
        if self.writing_stats.success_count > 0:
            self.writing_stats.avg_time_per_case = self.writing_stats.sum_case_time_seconds / self.writing_stats.success_count
            self.writing_stats.avg_output_tokens_per_case = self.writing_stats.total_tokens.completion_tokens / self.writing_stats.success_count
            if self.writing_stats.sum_case_time_seconds > 0:
                self.writing_stats.avg_tokens_per_second = self.writing_stats.total_tokens.completion_tokens / self.writing_stats.sum_case_time_seconds

        # 输出统计摘要
        self.log(f"📊 文生文测试完成:")
        self.log(f"    成功: {self.writing_stats.success_count}/{self.writing_stats.total_cases}")
        self.log(f"    总Tokens: {self.writing_stats.total_tokens.total_tokens} (输入: {self.writing_stats.total_tokens.prompt_tokens}, 输出: {self.writing_stats.total_tokens.completion_tokens})")
        self.log(f"    多线程总耗时: {self.writing_stats.total_time_seconds:.1f}秒")
        self.log(f"    单case平均耗时: {self.writing_stats.avg_time_per_case:.1f}秒")
        self.log(f"    单case平均输出: {self.writing_stats.avg_output_tokens_per_case:.0f} tokens")
        self.log(f"    平均输出速率: {self.writing_stats.avg_tokens_per_second:.1f} tokens/s")
        if self.writing_stats.timeout_count > 0:
            self.log(f"    ⏰ 超时次数: {self.writing_stats.timeout_count}")
        if self.writing_stats.retry_count > 0:
            self.log(f"    🔄 重试次数: {self.writing_stats.retry_count}")
        if self.writing_stats.incomplete_count > 0:
            self.log(f"    ⚠️ 不完整响应: {self.writing_stats.incomplete_count}")

        # 保存统计信息
        stats_file = self.output_dir / "writing" / "_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(self.writing_stats.to_dict(), f, ensure_ascii=False, indent=2)

        self.results["writing"] = results
        return results

    def run_single_writing_test(self, case) -> Dict[str, Any]:
        """执行单个文生文（写作能力）测试"""
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
        tokens_per_second = api_result.get("tokens_per_second", 0)
        is_incomplete = api_result.get("is_incomplete", False)
        finish_reason = api_result.get("finish_reason", "")

        # 安全提取内容
        content = ""
        reasoning_content = ""

        try:
            message = response_json.get("choices", [{}])[0].get("message", {})
            content = message.get("content") or ""
            reasoning_content = message.get("reasoning_content") or ""

            if not content and reasoning_content:
                content = reasoning_content
                self.log(f"    📝 [{case['id']}] 使用reasoning_content作为响应内容")

        except (KeyError, IndexError, TypeError) as e:
            self.log(f"    ⚠️ [{case['id']}] 响应格式异常: {str(e)}")
            content = json.dumps(response_json, ensure_ascii=False, indent=2)

        # 保存响应（清理文件名中的非法字符）
        safe_name = sanitize_filename(case['name'])
        output_file = self.output_dir / "writing" / f"{case['id']}_{safe_name}.json"
        result = {
            "id": case["id"],
            "name": case["name"],
            "category": case.get("category", "未分类"),
            "difficulty": case.get("difficulty", "中"),
            "tags": case.get("tags", []),
            "icon": case.get("icon", "📝"),
            "prompt": case["prompt"],
            "response": content,
            "reasoning_content": reasoning_content if reasoning_content else None,
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "token_usage": asdict(token_usage),
            "duration_seconds": duration_seconds,
            "retry_count": retry_count,
            "tokens_per_second": tokens_per_second,
            "is_incomplete": is_incomplete,
            "finish_reason": finish_reason,
            "model": self.text_model
        }

        # 计算字数统计
        result["char_count"] = len(content)
        result["word_count"] = len(content.split())

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 同时保存纯文本文件便于查看
        txt_file = self.output_dir / "writing" / f"{case['id']}_{safe_name}.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(f"=== {case['name']} ===\n\n")
            f.write(f"【提示词】\n{case['prompt']}\n\n")
            f.write(f"【模型响应】\n{content}\n")

        result["txt_file"] = str(txt_file)
        result["token_usage"] = token_usage
        return result

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
                self.log(f"🔄 重试 {len(failed_text)} 个失败的代码生成案例...")
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

        # 执行代码生成测试
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
