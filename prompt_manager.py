# -*- coding: utf-8 -*-
"""
提示词管理器 - 管理测试用例提示词
版本 2.1 - 增强版：重试机制、超时日志、tokens统计、缓存
"""

import json
import re
import time
import random
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import requests
except ImportError:
    requests = None


class PromptManager:
    # 重试配置
    MAX_RETRIES = 3
    BASE_DELAY = 2
    MAX_DELAY = 30
    REQUEST_TIMEOUT = 1200  # 请求超时时间（秒）

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.text_cases_file = self.base_dir / "test_cases" / "text_cases.json"
        self.writing_cases_file = self.base_dir / "test_cases" / "writing_cases.json"
        self.image_cases_file = self.base_dir / "test_cases" / "image_cases.json"
        self.cache_file = self.base_dir / "test_cases" / "_prompt_cache.json"
        self.history_file = self.base_dir / "test_cases" / "_generation_history.json"

        # 确保目录存在
        (self.base_dir / "test_cases").mkdir(parents=True, exist_ok=True)

    def load_cases(self, test_type: str) -> Dict:
        """加载测试用例"""
        if test_type == "text":
            file_path = self.text_cases_file
        elif test_type == "writing":
            file_path = self.writing_cases_file
        else:
            file_path = self.image_cases_file

        if not file_path.exists():
            return {"meta": {}, "cases": []}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 确保必要的字段存在
                if "meta" not in data:
                    data["meta"] = {}
                if "cases" not in data:
                    data["cases"] = []
                return data
        except json.JSONDecodeError as e:
            print(f"警告: 测试用例文件格式错误 {file_path}: {e}")
            return {"meta": {}, "cases": []}
        except Exception as e:
            print(f"警告: 无法读取测试用例文件 {file_path}: {e}")
            return {"meta": {}, "cases": []}

    def save_cases(self, test_type: str, data: Dict):
        """保存测试用例"""
        if test_type == "text":
            file_path = self.text_cases_file
        elif test_type == "writing":
            file_path = self.writing_cases_file
        else:
            file_path = self.image_cases_file

        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 添加元数据
        if "meta" not in data:
            data["meta"] = {}
        data["meta"]["last_updated"] = datetime.now().isoformat()
        data["meta"]["case_count"] = len(data.get("cases", []))

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"错误: 无法保存测试用例文件 {file_path}: {e}")
            raise

    def add_case(self, test_type: str, case: Dict):
        """添加测试用例"""
        data = self.load_cases(test_type)

        # 检查ID是否已存在
        existing_ids = [c["id"] for c in data["cases"]]
        if case["id"] in existing_ids:
            print(f"警告: 案例ID {case['id']} 已存在，将覆盖")
            data["cases"] = [c for c in data["cases"] if c["id"] != case["id"]]

        data["cases"].append(case)
        self.save_cases(test_type, data)

    def update_case(self, test_type: str, case_id: str, updated_case: Dict):
        """更新测试用例"""
        data = self.load_cases(test_type)
        found = False
        for i, case in enumerate(data["cases"]):
            if case["id"] == case_id:
                data["cases"][i] = updated_case
                found = True
                break

        if not found:
            print(f"警告: 未找到案例ID {case_id}")
            return False

        self.save_cases(test_type, data)
        return True

    def delete_case(self, test_type: str, case_id: str) -> bool:
        """删除测试用例"""
        data = self.load_cases(test_type)
        original_count = len(data["cases"])
        data["cases"] = [c for c in data["cases"] if c["id"] != case_id]

        if len(data["cases"]) == original_count:
            print(f"警告: 未找到案例ID {case_id}")
            return False

        self.save_cases(test_type, data)
        return True

    def _get_cache_key(self, test_type: str, count: int, model: str) -> str:
        """生成缓存键"""
        content = f"{test_type}_{count}_{model}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _load_cache(self) -> Dict:
        """加载缓存"""
        if not self.cache_file.exists():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _save_cache(self, cache: Dict):
        """保存缓存"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"警告: 无法保存缓存: {e}")

    def _save_to_history(self, test_type: str, prompts: List[Dict], model: str,
                         token_usage: Dict, duration: float):
        """保存生成历史"""
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except:
                history = []

        history.append({
            "timestamp": datetime.now().isoformat(),
            "test_type": test_type,
            "model": model,
            "count": len(prompts),
            "token_usage": token_usage,
            "duration_seconds": round(duration, 2),
            "prompts": prompts
        })

        # 只保留最近50条记录
        history = history[-50:]

        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"警告: 无法保存生成历史: {e}")

    def generate_prompts(self, api_url: str, api_key: str, model: str,
                        test_type: str, count: int, log_callback=None,
                        use_cache: bool = False) -> List[Dict]:
        """
        使用AI生成提示词（带重试和统计）

        Args:
            api_url: API地址
            api_key: API密钥
            model: 模型名称
            test_type: 测试类型 ("text" 或 "image")
            count: 生成数量
            log_callback: 日志回调函数
            use_cache: 是否使用缓存

        Returns:
            生成的提示词列表
        """
        if requests is None:
            raise ImportError("需要安装 requests 库")

        log = log_callback or print

        # 检查缓存
        if use_cache:
            cache_key = self._get_cache_key(test_type, count, model)
            cache = self._load_cache()
            if cache_key in cache:
                cached = cache[cache_key]
                log(f"使用缓存的提示词 (生成于 {cached.get('timestamp', 'unknown')})")
                return cached.get("prompts", [])

        # 构建提示词
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
    "tags": ["标签1", "标签2"],
    "icon": "emoji图标",
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
    "tags": ["标签1", "标签2"],
    "icon": "emoji图标",
    "prompt": "Detailed English prompt for image generation..."
  }}
]
"""

        log(f"正在使用AI生成{count}个{test_type}提示词...")
        log(f"使用模型: {model}")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": system_prompt}],
            "max_tokens": 4096
        }

        endpoint = f"{api_url.rstrip('/')}/chat/completions"
        start_time = time.time()
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for attempt in range(self.MAX_RETRIES + 1):
            attempt_start = time.time()
            try:
                log(f"    开始请求 (第{attempt + 1}次尝试)...")

                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT
                )

                attempt_duration = time.time() - attempt_start
                log(f"    请求完成，耗时 {attempt_duration:.1f}秒")

                response.raise_for_status()
                response_json = response.json()

                # 提取token使用量
                if "usage" in response_json:
                    usage = response_json["usage"]
                    token_usage = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0)
                    }
                    log(f"    Tokens: 输入={token_usage['prompt_tokens']}, 输出={token_usage['completion_tokens']}, 总计={token_usage['total_tokens']}")

                # 提取内容
                content = ""
                try:
                    content = response_json["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    log(f"    响应格式异常: {e}")
                    raise Exception(f"响应格式异常: {e}")

                # 提取JSON
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    try:
                        prompts = json.loads(json_match.group())
                        total_duration = time.time() - start_time
                        log(f"成功生成{len(prompts)}个提示词，总耗时 {total_duration:.1f}秒")

                        # 保存到历史记录
                        self._save_to_history(test_type, prompts, model, token_usage, total_duration)

                        # 保存到缓存
                        if use_cache:
                            cache = self._load_cache()
                            cache_key = self._get_cache_key(test_type, count, model)
                            cache[cache_key] = {
                                "timestamp": datetime.now().isoformat(),
                                "prompts": prompts,
                                "token_usage": token_usage
                            }
                            self._save_cache(cache)

                        return prompts
                    except json.JSONDecodeError as e:
                        log(f"    JSON解析失败: {e}")
                        raise Exception(f"JSON解析失败: {e}")
                else:
                    log("    无法从响应中提取JSON数组")
                    # 保存原始响应用于调试
                    debug_file = self.base_dir / "test_cases" / f"_debug_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    log(f"    原始响应已保存到 {debug_file.name}")
                    raise Exception("无法从响应中提取JSON数组")

            except requests.exceptions.Timeout as e:
                attempt_duration = time.time() - attempt_start
                log(f"    ⏰ 请求超时! 已等待 {attempt_duration:.1f}秒 (超时限制: {self.REQUEST_TIMEOUT}秒)")

            except requests.exceptions.ConnectionError as e:
                log(f"    🔌 连接错误: {str(e)[:100]}")

            except requests.exceptions.HTTPError as e:
                status_code = response.status_code if 'response' in locals() else 'unknown'
                if isinstance(status_code, int) and status_code in [429, 500, 502, 503, 504]:
                    log(f"    🚫 HTTP {status_code} 错误")
                else:
                    log(f"    ❌ HTTP错误: {e}")
                    raise Exception(f"API调用失败: HTTP {status_code}")

            except Exception as e:
                if attempt == self.MAX_RETRIES:
                    log(f"生成提示词失败: {str(e)}")
                    return []

            # 重试逻辑
            if attempt < self.MAX_RETRIES:
                delay = min(self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), self.MAX_DELAY)
                log(f"    🔄 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试...")
                time.sleep(delay)

        log(f"生成提示词失败（已重试{self.MAX_RETRIES}次）")
        return []

    def get_next_id(self, test_type: str) -> str:
        """获取下一个可用ID"""
        data = self.load_cases(test_type)

        # 确定前缀
        if test_type == "text":
            prefix = "T"
        elif test_type == "writing":
            prefix = "W"
        else:
            prefix = "I"

        if not data["cases"]:
            return f"{prefix}01"

        # 提取所有ID的数字部分
        ids = []
        for c in data["cases"]:
            case_id = c.get("id", "")
            if case_id.startswith(prefix) and case_id[1:].isdigit():
                ids.append(int(case_id[1:]))

        if not ids:
            return f"{prefix}01"

        next_num = max(ids) + 1
        return f"{prefix}{next_num:02d}"

    def get_generation_history(self, limit: int = 10) -> List[Dict]:
        """获取生成历史"""
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                return history[-limit:]
        except:
            return []

    def get_stats(self) -> Dict:
        """获取提示词统计信息"""
        text_data = self.load_cases("text")
        writing_data = self.load_cases("writing")
        image_data = self.load_cases("image")

        return {
            "text_count": len(text_data.get("cases", [])),
            "writing_count": len(writing_data.get("cases", [])),
            "image_count": len(image_data.get("cases", [])),
            "text_last_updated": text_data.get("meta", {}).get("last_updated"),
            "writing_last_updated": writing_data.get("meta", {}).get("last_updated"),
            "image_last_updated": image_data.get("meta", {}).get("last_updated"),
            "total_count": len(text_data.get("cases", [])) + len(writing_data.get("cases", [])) + len(image_data.get("cases", []))
        }
