# -*- coding: utf-8 -*-
"""
网站生成器 - 生成测评结果展示网站
"""

import json
from pathlib import Path
from datetime import datetime


class WebsiteGenerator:
    def __init__(self, output_dir, model_name="AI Model"):
        self.output_dir = Path(output_dir)
        self.model_name = model_name

    def generate(self):
        """生成展示网站"""
        # 收集结果数据
        text_results = self.collect_results("text")
        image_results = self.collect_results("image")

        # 生成精简数据文件（不包含完整response，避免文件过大）
        data = {
            "meta": {
                "model": self.model_name,
                "generated_at": datetime.now().isoformat(),
                "total_text": len(text_results),
                "total_image": len(image_results)
            },
            "text_results": self.simplify_results(text_results),
            "image_results": self.simplify_results(image_results)
        }

        data_path = self.output_dir / "website" / "data.json"
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 生成HTML
        html_content = self.generate_html(data)
        html_path = self.output_dir / "website" / "index.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return html_path

    def simplify_results(self, results):
        """精简结果数据，移除response避免文件过大"""
        simplified = []
        for r in results:
            # 只保留必要字段
            simple_r = {
                "id": r.get("id", ""),
                "name": r.get("name", ""),
                "prompt": r.get("prompt", "")[:300],  # 只保留前300字
                "success": r.get("success", True),
                "timestamp": r.get("timestamp", "")
            }
            # 保留文件路径
            if "html_file" in r:
                simple_r["html_file"] = r["html_file"]
            if "image_file" in r:
                simple_r["image_file"] = r["image_file"]
            simplified.append(simple_r)
        return simplified

    def collect_results(self, test_type):
        """收集测试结果"""
        result_dir = self.output_dir / test_type
        results = []

        if not result_dir.exists():
            return results

        for json_file in result_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 检查是否有对应的HTML或图片文件
                base_name = json_file.stem

                if test_type == "text":
                    html_file = result_dir / f"{base_name}.html"
                    if html_file.exists():
                        data["html_file"] = f"../text/{html_file.name}"
                else:
                    for ext in ["png", "jpg", "jpeg"]:
                        img_file = result_dir / f"{base_name}.{ext}"
                        if img_file.exists():
                            data["image_file"] = f"../image/{img_file.name}"
                            break

                results.append(data)
            except Exception as e:
                print(f"读取结果失败 {json_file}: {e}")

        return sorted(results, key=lambda x: x.get("id", ""))

    def generate_html(self, data):
        """生成HTML页面"""
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI模型测评结果 - {self.model_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            padding: 40px 20px;
            color: white;
        }}

        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}

        .stat-card h3 {{
            font-size: 2.5em;
            color: #667eea;
            margin-bottom: 5px;
        }}

        .stat-card p {{
            color: #666;
            font-size: 1.1em;
        }}

        .section {{
            margin-bottom: 40px;
        }}

        .section-title {{
            color: white;
            font-size: 1.8em;
            margin-bottom: 20px;
            padding-left: 15px;
            border-left: 4px solid #ffd700;
        }}

        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }}

        .card {{
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}

        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.3);
        }}

        .card-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
        }}

        .card-header h3 {{
            font-size: 1.1em;
            margin-bottom: 5px;
        }}

        .card-header .id {{
            font-size: 0.9em;
            opacity: 0.8;
        }}

        .card-body {{
            padding: 20px;
        }}

        .card-body .prompt {{
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            font-size: 0.9em;
            color: #333;
            max-height: 150px;
            overflow-y: auto;
            margin-bottom: 15px;
        }}

        .card-body img {{
            width: 100%;
            border-radius: 8px;
            margin-bottom: 15px;
        }}

        .card-actions {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .btn {{
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.9em;
            text-decoration: none;
            cursor: pointer;
            border: none;
            transition: all 0.3s ease;
        }}

        .btn-primary {{
            background: #667eea;
            color: white;
        }}

        .btn-primary:hover {{
            background: #5a6fd6;
        }}

        .btn-secondary {{
            background: #e0e0e0;
            color: #333;
        }}

        .btn-secondary:hover {{
            background: #d0d0d0;
        }}

        .status {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            margin-left: 10px;
        }}

        .status-success {{
            background: #c8e6c9;
            color: #2e7d32;
        }}

        .status-error {{
            background: #ffcdd2;
            color: #c62828;
        }}

        /* Modal */
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }}

        .modal.active {{
            display: flex;
        }}

        .modal-content {{
            background: white;
            border-radius: 15px;
            max-width: 90%;
            max-height: 90%;
            overflow: auto;
            padding: 20px;
        }}

        .modal-close {{
            position: absolute;
            top: 20px;
            right: 30px;
            color: white;
            font-size: 2em;
            cursor: pointer;
        }}

        footer {{
            text-align: center;
            color: white;
            padding: 30px;
            opacity: 0.8;
        }}

        @media (max-width: 768px) {{
            .cards {{
                grid-template-columns: 1fr;
            }}

            header h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>AI模型测评结果</h1>
            <p>{self.model_name}</p>
            <p style="font-size: 0.9em; margin-top: 10px;">生成时间: {data['meta']['generated_at'][:19]}</p>
        </header>

        <div class="stats">
            <div class="stat-card">
                <h3>{data['meta']['total_text']}</h3>
                <p>文生文测试</p>
            </div>
            <div class="stat-card">
                <h3>{data['meta']['total_image']}</h3>
                <p>文生图测试</p>
            </div>
            <div class="stat-card">
                <h3>{data['meta']['total_text'] + data['meta']['total_image']}</h3>
                <p>总测试数</p>
            </div>
        </div>

        {'<div class="section"><h2 class="section-title">文生文测评结果</h2><div class="cards">' + self.generate_text_cards(data['text_results']) + '</div></div>' if data['text_results'] else ''}

        {'<div class="section"><h2 class="section-title">文生图测评结果</h2><div class="cards">' + self.generate_image_cards(data['image_results']) + '</div></div>' if data['image_results'] else ''}

        <footer>
            <p>AI模型一键测评工具生成</p>
        </footer>
    </div>

    <div class="modal" id="modal">
        <span class="modal-close" onclick="closeModal()">&times;</span>
        <div class="modal-content" id="modal-content"></div>
    </div>

    <script>
        function showResponse(id) {{
            // 从对应的JSON文件加载完整响应
            const isText = id.startsWith('T');
            const type = isText ? 'text' : 'image';

            fetch(`../${{type}}/${{id}}_*.json`)
                .catch(() => {{
                    // 如果fetch失败，显示提示
                    document.getElementById('modal-content').innerHTML =
                        '<p style="padding: 20px;">完整响应请查看对应的JSON文件：<br><code>output/' + type + '/' + id + '_*.json</code></p>';
                    document.getElementById('modal').classList.add('active');
                }});
        }}

        function closeModal() {{
            document.getElementById('modal').classList.remove('active');
        }}

        document.getElementById('modal').addEventListener('click', function(e) {{
            if (e.target === this) closeModal();
        }});

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeModal();
        }});
    </script>
</body>
</html>'''
        return html

    def generate_text_cards(self, results):
        """生成文生文卡片"""
        cards = []
        for r in results:
            status = "success" if r.get("success", True) else "error"
            status_text = "成功" if r.get("success", True) else "失败"

            html_btn = ""
            if r.get("html_file"):
                html_btn = f'<a href="{r["html_file"]}" target="_blank" class="btn btn-primary">查看演示</a>'

            card = f'''
            <div class="card">
                <div class="card-header">
                    <h3>{r.get('name', '未命名')}<span class="status status-{status}">{status_text}</span></h3>
                    <div class="id">{r.get('id', '')}</div>
                </div>
                <div class="card-body">
                    <div class="prompt">{r.get('prompt', '')[:200]}{'...' if len(r.get('prompt', '')) > 200 else ''}</div>
                    <div class="card-actions">
                        <button class="btn btn-secondary" onclick="showResponse('{r.get('id', '')}')">查看响应</button>
                        {html_btn}
                    </div>
                </div>
            </div>
            '''
            cards.append(card)
        return "".join(cards)

    def generate_image_cards(self, results):
        """生成文生图卡片"""
        cards = []
        for r in results:
            status = "success" if r.get("success", True) else "error"
            status_text = "成功" if r.get("success", True) else "失败"

            img_html = ""
            if r.get("image_file"):
                img_html = f'<img src="{r["image_file"]}" alt="{r.get("name", "")}">'

            card = f'''
            <div class="card">
                <div class="card-header">
                    <h3>{r.get('name', '未命名')}<span class="status status-{status}">{status_text}</span></h3>
                    <div class="id">{r.get('id', '')}</div>
                </div>
                <div class="card-body">
                    {img_html}
                    <div class="prompt">{r.get('prompt', '')[:200]}{'...' if len(r.get('prompt', '')) > 200 else ''}</div>
                    <div class="card-actions">
                        <button class="btn btn-secondary" onclick="showResponse('{r.get('id', '')}')">查看响应</button>
                    </div>
                </div>
            </div>
            '''
            cards.append(card)
        return "".join(cards)
