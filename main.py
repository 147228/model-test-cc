# -*- coding: utf-8 -*-
"""
AI模型一键测评工具 - 主GUI应用
支持文生文、文生图测评，一键生成展示网站
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import json
import os
import threading
from pathlib import Path
from datetime import datetime

from test_engine import TestEngine
from website_generator import WebsiteGenerator
from prompt_manager import PromptManager


class AIModelTester:
    def __init__(self, root):
        self.root = root
        self.root.title("AI模型一键测评工具 v1.0")
        self.root.geometry("1000x750")
        self.root.configure(bg="#f5f5f5")

        # 配置变量
        self.api_url = tk.StringVar(value="https://yunwu.ai/v1")
        self.api_key = tk.StringVar()
        self.text_model = tk.StringVar(value="gemini-3-pro-preview")
        self.image_model = tk.StringVar(value="gemini-3-pro-image-preview")
        self.max_threads = tk.IntVar(value=10)

        # 测试状态
        self.is_running = False
        self.test_engine = None

        # 项目路径
        self.base_dir = Path(__file__).parent
        self.output_dir = self.base_dir / "output"

        # 提示词管理器
        self.prompt_manager = PromptManager(self.base_dir)

        self.create_ui()
        self.load_config()

    def create_ui(self):
        """创建界面"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # API配置区
        config_frame = ttk.LabelFrame(main_frame, text="API配置", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))

        # API URL
        ttk.Label(config_frame, text="API URL:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(config_frame, textvariable=self.api_url, width=60).grid(row=0, column=1, columnspan=3, sticky=tk.W, pady=2)

        # API Key
        ttk.Label(config_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(config_frame, textvariable=self.api_key, width=60, show="*").grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=2)

        # 文生文模型
        ttk.Label(config_frame, text="文生文模型:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(config_frame, textvariable=self.text_model, width=30).grid(row=2, column=1, sticky=tk.W, pady=2)

        # 文生图模型
        ttk.Label(config_frame, text="文生图模型:").grid(row=2, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        ttk.Entry(config_frame, textvariable=self.image_model, width=30).grid(row=2, column=3, sticky=tk.W, pady=2)

        # 并发数
        ttk.Label(config_frame, text="并发线程:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(config_frame, from_=1, to=30, textvariable=self.max_threads, width=10).grid(row=3, column=1, sticky=tk.W, pady=2)

        # 保存配置按钮
        ttk.Button(config_frame, text="保存配置", command=self.save_config).grid(row=3, column=3, sticky=tk.E, pady=2)

        # 测试选项区
        test_frame = ttk.LabelFrame(main_frame, text="测试选项", padding="10")
        test_frame.pack(fill=tk.X, pady=(0, 10))

        self.test_text = tk.BooleanVar(value=True)
        self.test_image = tk.BooleanVar(value=True)

        ttk.Checkbutton(test_frame, text="文生文测评", variable=self.test_text).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(test_frame, text="文生图测评", variable=self.test_image).pack(side=tk.LEFT, padx=10)

        # 提示词管理按钮
        ttk.Button(test_frame, text="提示词管理", command=self.open_prompt_manager).pack(side=tk.RIGHT, padx=10)

        # 控制按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(btn_frame, text="开始测评", command=self.start_test, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.stop_test, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 重试失败按钮（初始隐藏）
        self.retry_btn = ttk.Button(btn_frame, text="重试失败案例 (0)", command=self.retry_failed, state=tk.DISABLED)
        self.retry_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="生成网站", command=self.generate_website).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="打开输出目录", command=self.open_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT, padx=5)

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # 状态标签
        self.status_label = ttk.Label(main_frame, text="就绪")
        self.status_label.pack(anchor=tk.W)

        # 日志区
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)

    def save_config(self):
        """保存配置"""
        config = {
            "api_url": self.api_url.get(),
            "api_key": self.api_key.get(),
            "text_model": self.text_model.get(),
            "image_model": self.image_model.get(),
            "max_threads": self.max_threads.get()
        }
        config_path = self.base_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        self.log("配置已保存")
        messagebox.showinfo("成功", "配置已保存")

    def load_config(self):
        """加载配置"""
        config_path = self.base_dir / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.api_url.set(config.get("api_url", "https://yunwu.ai/v1"))
                self.api_key.set(config.get("api_key", ""))
                self.text_model.set(config.get("text_model", "gemini-3-pro-preview"))
                self.image_model.set(config.get("image_model", "gemini-3-pro-image-preview"))
                self.max_threads.set(config.get("max_threads", 10))
                self.log("配置已加载")
            except Exception as e:
                self.log(f"加载配置失败: {e}")

    def validate_config(self):
        """验证配置"""
        if not self.api_url.get():
            messagebox.showerror("错误", "请输入API URL")
            return False
        if not self.api_key.get():
            messagebox.showerror("错误", "请输入API Key")
            return False
        if not self.test_text.get() and not self.test_image.get():
            messagebox.showerror("错误", "请至少选择一种测评类型")
            return False
        return True

    def start_test(self):
        """开始测评"""
        if not self.validate_config():
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)

        # 在新线程中执行测试
        thread = threading.Thread(target=self.run_tests)
        thread.daemon = True
        thread.start()

    def run_tests(self):
        """执行测试"""
        try:
            self.log("=" * 50)
            self.log("开始AI模型测评")
            self.log("=" * 50)

            # 创建测试引擎
            self.test_engine = TestEngine(
                api_url=self.api_url.get(),
                api_key=self.api_key.get(),
                text_model=self.text_model.get(),
                image_model=self.image_model.get(),
                max_threads=self.max_threads.get(),
                output_dir=self.output_dir,
                log_callback=self.log,
                progress_callback=self.update_progress
            )

            total_tasks = 0
            completed = 0
            failed_count = 0

            # 文生文测评
            if self.test_text.get() and self.is_running:
                self.status_label.config(text="正在执行文生文测评...")
                text_results = self.test_engine.run_text_tests()
                completed += len(text_results)
                text_failed = len([r for r in text_results if not r.get("success", True) or not r.get("html_file")])
                failed_count += text_failed
                self.log(f"文生文测评完成: {len(text_results)} 个案例，{text_failed} 个失败/未提取HTML")

            # 文生图测评
            if self.test_image.get() and self.is_running:
                self.status_label.config(text="正在执行文生图测评...")
                image_results = self.test_engine.run_image_tests()
                completed += len(image_results)
                image_failed = len([r for r in image_results if not r.get("success", True) or not r.get("has_image")])
                failed_count += image_failed
                self.log(f"文生图测评完成: {len(image_results)} 个案例，{image_failed} 个失败/未提取图片")

            if self.is_running:
                self.log("=" * 50)
                self.log(f"测评完成! 共完成 {completed} 个测试案例")
                if failed_count > 0:
                    self.log(f"⚠️ 有 {failed_count} 个案例失败或未成功提取内容")
                self.log("=" * 50)
                self.status_label.config(text=f"测评完成 - {completed} 个案例，{failed_count} 个失败")
                self.progress_var.set(100)

                # 更新重试按钮状态
                self.root.after(0, lambda: self.update_retry_button(failed_count))

                # 自动生成网站
                self.log("正在生成展示网站...")
                self.generate_website_internal()

        except Exception as e:
            self.log(f"测评出错: {str(e)}")
            self.status_label.config(text=f"错误: {str(e)}")
        finally:
            self.is_running = False
            self.root.after(0, self.reset_buttons)

    def update_retry_button(self, failed_count):
        """更新重试按钮状态"""
        if failed_count > 0:
            self.retry_btn.config(text=f"重试失败案例 ({failed_count})", state=tk.NORMAL)
        else:
            self.retry_btn.config(text="重试失败案例 (0)", state=tk.DISABLED)

    def retry_failed(self):
        """重试失败的案例"""
        if not self.test_engine:
            messagebox.showwarning("警告", "请先运行一次测评")
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.retry_btn.config(state=tk.DISABLED)

        def do_retry():
            try:
                self.log("=" * 50)
                self.log("开始重试失败案例")
                self.log("=" * 50)

                retry_count = self.test_engine.retry_failed_tests("all")

                self.log("=" * 50)
                self.log(f"重试完成! 成功重试 {retry_count} 个案例")
                self.log("=" * 50)

                # 重新统计失败数量
                failed_count = 0
                for r in self.test_engine.results.get("text", []):
                    if not r.get("success", True) or not r.get("html_file"):
                        failed_count += 1
                for r in self.test_engine.results.get("image", []):
                    if not r.get("success", True) or not r.get("has_image"):
                        failed_count += 1

                self.root.after(0, lambda: self.update_retry_button(failed_count))

                # 重新生成网站
                if retry_count > 0:
                    self.log("正在重新生成展示网站...")
                    self.generate_website_internal()

            except Exception as e:
                self.log(f"重试出错: {str(e)}")
            finally:
                self.is_running = False
                self.root.after(0, self.reset_buttons)

        threading.Thread(target=do_retry, daemon=True).start()

    def reset_buttons(self):
        """重置按钮状态"""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def stop_test(self):
        """停止测评"""
        self.is_running = False
        if self.test_engine:
            self.test_engine.stop()
        self.log("测评已停止")
        self.status_label.config(text="已停止")

    def update_progress(self, value):
        """更新进度条"""
        self.progress_var.set(value)
        self.root.update_idletasks()

    def generate_website(self):
        """生成网站"""
        self.log("正在生成展示网站...")
        threading.Thread(target=self.generate_website_internal, daemon=True).start()

    def generate_website_internal(self):
        """生成网站内部方法"""
        try:
            generator = WebsiteGenerator(
                output_dir=self.output_dir,
                model_name=f"{self.text_model.get()} / {self.image_model.get()}"
            )
            html_path = generator.generate()
            self.log(f"网站生成成功: {html_path}")
            self.status_label.config(text="网站已生成")

            # 询问是否打开
            if messagebox.askyesno("成功", "网站生成成功！是否立即打开？"):
                os.startfile(html_path)

        except Exception as e:
            self.log(f"生成网站失败: {str(e)}")

    def open_output(self):
        """打开输出目录"""
        os.startfile(self.output_dir)

    def open_prompt_manager(self):
        """打开提示词管理窗口"""
        PromptManagerWindow(self.root, self.prompt_manager, self.api_url, self.api_key, self.text_model, self.log)


class PromptManagerWindow:
    """提示词管理窗口"""

    def __init__(self, parent, prompt_manager, api_url, api_key, model, log_callback):
        self.prompt_manager = prompt_manager
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.log = log_callback

        # 创建顶层窗口
        self.window = tk.Toplevel(parent)
        self.window.title("提示词管理")
        self.window.geometry("900x600")
        self.window.transient(parent)

        self.current_type = tk.StringVar(value="text")

        self.create_ui()
        self.load_cases()

    def create_ui(self):
        """创建界面"""
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部工具栏
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        # 类型选择
        ttk.Label(toolbar, text="类型:").pack(side=tk.LEFT, padx=(0, 5))
        type_combo = ttk.Combobox(toolbar, textvariable=self.current_type, values=["text", "image"], state="readonly", width=10)
        type_combo.pack(side=tk.LEFT)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self.load_cases())

        # 生成提示词数量
        ttk.Label(toolbar, text="生成数量:").pack(side=tk.LEFT, padx=(20, 5))
        self.gen_count = tk.IntVar(value=5)
        ttk.Spinbox(toolbar, from_=1, to=20, textvariable=self.gen_count, width=5).pack(side=tk.LEFT)

        # 按钮
        ttk.Button(toolbar, text="AI生成提示词", command=self.generate_prompts).pack(side=tk.LEFT, padx=10)
        ttk.Button(toolbar, text="添加", command=self.add_case).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="删除选中", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="刷新", command=self.load_cases).pack(side=tk.LEFT, padx=5)

        # 列表区
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 创建Treeview
        columns = ("ID", "名称", "分类", "难度")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100 if col != "名称" else 200)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 双击编辑
        self.tree.bind("<Double-1>", self.edit_case)

        # 编辑区
        edit_frame = ttk.LabelFrame(main_frame, text="编辑提示词", padding="10")
        edit_frame.pack(fill=tk.X, pady=(10, 0))

        # ID和名称
        row1 = ttk.Frame(edit_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="ID:").pack(side=tk.LEFT)
        self.edit_id = tk.StringVar()
        ttk.Entry(row1, textvariable=self.edit_id, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="名称:").pack(side=tk.LEFT, padx=(20, 0))
        self.edit_name = tk.StringVar()
        ttk.Entry(row1, textvariable=self.edit_name, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="分类:").pack(side=tk.LEFT, padx=(20, 0))
        self.edit_category = tk.StringVar()
        ttk.Entry(row1, textvariable=self.edit_category, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="难度:").pack(side=tk.LEFT, padx=(20, 0))
        self.edit_difficulty = ttk.Combobox(row1, values=["简单", "中", "高"], width=8)
        self.edit_difficulty.pack(side=tk.LEFT, padx=5)

        # 提示词
        ttk.Label(edit_frame, text="提示词:").pack(anchor=tk.W, pady=(5, 2))
        self.edit_prompt = scrolledtext.ScrolledText(edit_frame, height=5)
        self.edit_prompt.pack(fill=tk.X)

        # 保存按钮
        ttk.Button(edit_frame, text="保存修改", command=self.save_case).pack(anchor=tk.E, pady=(5, 0))

    def load_cases(self):
        """加载测试用例"""
        # 清空列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 加载数据
        data = self.prompt_manager.load_cases(self.current_type.get())
        for case in data.get("cases", []):
            self.tree.insert("", tk.END, values=(
                case.get("id", ""),
                case.get("name", ""),
                case.get("category", ""),
                case.get("difficulty", "")
            ))

    def add_case(self):
        """添加新案例"""
        next_id = self.prompt_manager.get_next_id(self.current_type.get())
        self.edit_id.set(next_id)
        self.edit_name.set("")
        self.edit_category.set("")
        self.edit_difficulty.set("中")
        self.edit_prompt.delete("1.0", tk.END)

    def edit_case(self, event):
        """编辑选中的案例"""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.tree.item(item, "values")
        case_id = values[0]

        # 加载完整数据
        data = self.prompt_manager.load_cases(self.current_type.get())
        for case in data.get("cases", []):
            if case.get("id") == case_id:
                self.edit_id.set(case.get("id", ""))
                self.edit_name.set(case.get("name", ""))
                self.edit_category.set(case.get("category", ""))
                self.edit_difficulty.set(case.get("difficulty", "中"))
                self.edit_prompt.delete("1.0", tk.END)
                self.edit_prompt.insert("1.0", case.get("prompt", ""))
                break

    def save_case(self):
        """保存案例"""
        case = {
            "id": self.edit_id.get(),
            "name": self.edit_name.get(),
            "category": self.edit_category.get(),
            "difficulty": self.edit_difficulty.get(),
            "prompt": self.edit_prompt.get("1.0", tk.END).strip()
        }

        if not case["id"] or not case["name"] or not case["prompt"]:
            messagebox.showerror("错误", "请填写ID、名称和提示词")
            return

        # 检查是新增还是更新
        data = self.prompt_manager.load_cases(self.current_type.get())
        existing = False
        for i, c in enumerate(data.get("cases", [])):
            if c.get("id") == case["id"]:
                data["cases"][i] = case
                existing = True
                break

        if not existing:
            data["cases"].append(case)

        self.prompt_manager.save_cases(self.current_type.get(), data)
        self.load_cases()
        messagebox.showinfo("成功", "保存成功")

    def delete_selected(self):
        """删除选中的案例"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的案例")
            return

        if not messagebox.askyesno("确认", f"确定要删除选中的 {len(selection)} 个案例吗？"):
            return

        for item in selection:
            values = self.tree.item(item, "values")
            case_id = values[0]
            self.prompt_manager.delete_case(self.current_type.get(), case_id)

        self.load_cases()
        messagebox.showinfo("成功", "删除成功")

    def generate_prompts(self):
        """生成提示词"""
        if not self.api_key.get():
            messagebox.showerror("错误", "请先配置API Key")
            return

        count = self.gen_count.get()
        test_type = self.current_type.get()

        def do_generate():
            prompts = self.prompt_manager.generate_prompts(
                self.api_url.get(),
                self.api_key.get(),
                self.model.get(),
                test_type,
                count,
                self.log
            )

            if prompts:
                # 添加生成的提示词
                data = self.prompt_manager.load_cases(test_type)
                for prompt in prompts:
                    # 确保ID唯一
                    existing_ids = [c.get("id") for c in data.get("cases", [])]
                    if prompt.get("id") in existing_ids:
                        prompt["id"] = self.prompt_manager.get_next_id(test_type)
                    data["cases"].append(prompt)

                self.prompt_manager.save_cases(test_type, data)

                # 刷新列表
                self.window.after(0, self.load_cases)
                self.window.after(0, lambda: messagebox.showinfo("成功", f"成功生成 {len(prompts)} 个提示词"))
            else:
                self.window.after(0, lambda: messagebox.showerror("失败", "生成提示词失败"))

        threading.Thread(target=do_generate, daemon=True).start()


def main():
    root = tk.Tk()

    # 设置样式
    style = ttk.Style()
    style.theme_use("clam")

    app = AIModelTester(root)
    root.mainloop()


if __name__ == "__main__":
    main()
