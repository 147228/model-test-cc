# -*- coding: utf-8 -*-
"""
增强版网站生成器 - 支持筛选、搜索、图标系统和模型对比
版本 2.0
"""

import json
from pathlib import Path
from datetime import datetime


class EnhancedWebsiteGenerator:
    def __init__(self, output_dir, model_name="AI Model"):
        self.output_dir = Path(output_dir)
        self.model_name = model_name

    def generate(self):
        """生成展示网站"""
        # 收集结果数据
        text_results = self.collect_results("text")
        writing_results = self.collect_results("writing")
        image_results = self.collect_results("image")

        # 加载统计数据
        text_stats = self.load_stats("text")
        writing_stats = self.load_stats("writing")
        image_stats = self.load_stats("image")

        # 生成精简数据文件
        data = {
            "meta": {
                "model": self.model_name,
                "generated_at": datetime.now().isoformat(),
                "total_text": len(text_results),
                "total_writing": len(writing_results),
                "total_image": len(image_results)
            },
            "text_results": self.simplify_results(text_results),
            "writing_results": self.simplify_results(writing_results),
            "image_results": self.simplify_results(image_results),
            "stats": {
                "text": text_stats,
                "writing": writing_stats,
                "image": image_stats
            }
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
        """精简结果数据"""
        simplified = []
        for r in results:
            simple_r = {
                "id": r.get("id", ""),
                "name": r.get("name", ""),
                "category": r.get("category", "未分类"),
                "difficulty": r.get("difficulty", "中"),
                "tags": r.get("tags", []),
                "icon": r.get("icon", "📄"),
                "prompt": r.get("prompt", "")[:300],
                "success": r.get("success", True),
                "timestamp": r.get("timestamp", "")
            }
            if "html_file" in r:
                simple_r["html_file"] = r["html_file"]
            if "image_file" in r:
                simple_r["image_file"] = r["image_file"]
            if "txt_file" in r:
                simple_r["txt_file"] = r["txt_file"]
            if "response" in r:
                # 截取响应内容用于预览
                simple_r["response"] = r["response"][:500] if r.get("response") else ""
            if "char_count" in r:
                simple_r["char_count"] = r["char_count"]
            simplified.append(simple_r)
        return simplified

    def load_stats(self, test_type):
        """加载统计数据"""
        stats_file = self.output_dir / test_type / "_stats.json"
        if not stats_file.exists():
            return {}
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def collect_results(self, test_type):
        """收集测试结果（只收集成功的案例）"""
        result_dir = self.output_dir / test_type
        results = []
        skipped = []

        if not result_dir.exists():
            return results

        for json_file in result_dir.glob("*.json"):
            # 跳过统计文件
            if json_file.name.startswith("_"):
                continue

            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 检查是否成功
                if not data.get("success", True):
                    skipped.append(data.get("id", json_file.stem))
                    continue

                base_name = json_file.stem

                if test_type == "text":
                    # 检查是否有HTML文件
                    html_file = result_dir / f"{base_name}.html"
                    if html_file.exists():
                        data["html_file"] = f"../text/{html_file.name}"
                    else:
                        # 没有HTML文件，跳过
                        skipped.append(data.get("id", base_name))
                        continue
                elif test_type == "writing":
                    # 文生文测试，检查txt文件
                    txt_file = result_dir / f"{base_name}.txt"
                    if txt_file.exists():
                        data["txt_file"] = f"../writing/{txt_file.name}"
                    # 文生文不强制要求txt文件，因为response已经在json中
                    results.append(data)
                    continue
                else:
                    # 检查是否有图片文件
                    found_image = False
                    for ext in ["png", "jpg", "jpeg"]:
                        img_file = result_dir / f"{base_name}.{ext}"
                        if img_file.exists():
                            data["image_file"] = f"../image/{img_file.name}"
                            found_image = True
                            break
                    if not found_image:
                        # 没有图片文件，跳过
                        skipped.append(data.get("id", base_name))
                        continue

                results.append(data)
            except Exception as e:
                print(f"读取结果失败 {json_file}: {e}")

        if skipped:
            print(f"[{test_type}] 跳过 {len(skipped)} 个失败/无输出的案例: {', '.join(skipped)}")

        return sorted(results, key=lambda x: x.get("id", ""))

    def generate_html(self, data):
        """生成增强版HTML页面"""
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI模型测评结果 - {self.model_name} | 夕小瑶科技</title>
    <style>
        :root {{
            --primary-color: #ff758c;
            --secondary-color: #ff7eb3;
            --accent-color: #726cf8;
            --bg-light: #fdf2f8;
            --bg-card: #ffffff;
            --text-main: #374151;
            --text-muted: #6b7280;
            --gradient-brand: linear-gradient(135deg, #fce7f3 0%, #fbcfe8 100%);
            --gradient-bg: linear-gradient(180deg, #fdf2f8 0%, #fce7f3 100%);
            --glass-bg: rgba(255, 255, 255, 0.8);
            --glass-border: rgba(255, 192, 203, 0.3);
            --shadow-soft: 0 10px 30px -10px rgba(255, 117, 140, 0.2);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--gradient-bg);
            color: var(--text-main);
            line-height: 1.6;
            overflow-x: hidden;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 20px;
        }}

        /* 头部设计 */
        header {{
            padding: 60px 0 40px;
            text-align: center;
            position: relative;
        }}

        .brand-avatar {{
            width: 100px;
            height: 100px;
            border-radius: 50%;
            margin: 0 auto 20px;
            overflow: hidden;
            box-shadow: 0 0 30px rgba(255, 117, 140, 0.3);
            animation: float 6s ease-in-out infinite;
        }}

        .brand-avatar img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        @keyframes float {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-10px); }}
        }}

        h1 {{
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 10px;
            background: linear-gradient(to right, #ec4899, #f472b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -1px;
        }}

        .subtitle {{
            font-size: 1.1rem;
            color: var(--text-muted);
            margin-bottom: 20px;
            font-weight: 300;
        }}

        /* 统计数据卡片 */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
            max-width: 1000px;
            margin-left: auto;
            margin-right: auto;
        }}

        .stat-card {{
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            padding: 20px;
            border-radius: 16px;
            text-align: center;
            transition: transform 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
            border-color: var(--primary-color);
        }}

        .stat-value {{
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--primary-color);
            display: block;
        }}

        .stat-label {{
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        /* 搜索和筛选栏 */
        .filter-bar {{
            background: var(--bg-card);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            border: 1px solid var(--glass-border);
        }}

        .search-box {{
            width: 100%;
            padding: 12px 20px;
            border: 2px solid var(--glass-border);
            border-radius: 12px;
            font-size: 1rem;
            transition: all 0.3s ease;
            margin-bottom: 15px;
        }}

        .search-box:focus {{
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(255, 117, 140, 0.1);
        }}

        .filter-buttons {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }}

        .filter-btn {{
            padding: 8px 16px;
            border: 2px solid var(--glass-border);
            background: var(--bg-light);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9rem;
            font-weight: 500;
        }}

        .filter-btn:hover {{
            border-color: var(--primary-color);
            background: white;
        }}

        .filter-btn.active {{
            background: linear-gradient(135deg, #ff758c 0%, #ff7eb3 100%);
            color: white;
            border-color: var(--primary-color);
        }}

        /* 分类标题 */
        .section-title {{
            color: var(--text-main);
            font-size: 1.8em;
            margin: 50px 0 20px;
            padding-left: 15px;
            border-left: 4px solid var(--primary-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .result-count {{
            font-size: 0.6em;
            color: var(--text-muted);
            font-weight: normal;
        }}

        /* 画廊网格 */
        .gallery-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 24px;
            padding-bottom: 50px;
        }}

        .gallery-item {{
            position: relative;
            border-radius: 16px;
            overflow: hidden;
            cursor: pointer;
            background: var(--bg-card);
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transition: transform 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
        }}

        .gallery-item:hover {{
            transform: scale(1.02) translateY(-5px);
            z-index: 2;
            box-shadow: 0 15px 40px rgba(255, 117, 140, 0.3);
        }}

        .gallery-img {{
            width: 100%;
            height: 250px;
            object-fit: cover;
            transition: transform 0.5s ease;
        }}

        .gallery-item:hover .gallery-img {{
            transform: scale(1.1);
        }}

        /* 图标背景 */
        .icon-bg {{
            width: 100%;
            height: 220px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--gradient-brand);
            position: relative;
            overflow: hidden;
        }}

        .icon-bg::before {{
            content: '';
            position: absolute;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 1px, transparent 1px);
            background-size: 20px 20px;
            animation: slide 20s linear infinite;
        }}

        @keyframes slide {{
            0% {{ transform: translate(0, 0); }}
            100% {{ transform: translate(20px, 20px); }}
        }}

        /* 不同类型的渐变背景 */
        .icon-bg.game {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}

        .icon-bg.tool {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}

        .icon-bg.animation {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }}

        .icon-bg.graphics {{
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        }}

        .icon-bg.audio {{
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }}

        .icon-bg.ui {{
            background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        }}

        .icon-bg.data {{
            background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);
        }}

        .icon-emoji {{
            font-size: 5em;
            position: relative;
            z-index: 1;
            animation: iconFloat 3s ease-in-out infinite;
        }}

        @keyframes iconFloat {{
            0%, 100% {{ transform: translateY(0) scale(1); }}
            50% {{ transform: translateY(-10px) scale(1.05); }}
        }}

        /* 图片遮罩信息 */
        .item-overlay {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 30px 20px 20px;
            background: linear-gradient(to top, rgba(15, 17, 26, 0.95), transparent);
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.3s ease;
        }}

        .gallery-item:hover .item-overlay {{
            opacity: 1;
            transform: translateY(0);
        }}

        .item-category {{
            font-size: 0.75rem;
            color: var(--primary-color);
            text-transform: uppercase;
            font-weight: 700;
            margin-bottom: 4px;
            display: block;
        }}

        .item-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: white;
        }}

        /* 卡片信息 */
        .card-info {{
            padding: 20px;
        }}

        .card-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}

        .card-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-main);
            flex: 1;
        }}

        .difficulty-badge {{
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .difficulty-简单 {{ background: #d1fae5; color: #065f46; }}
        .difficulty-中 {{ background: #fed7aa; color: #92400e; }}
        .difficulty-高 {{ background: #fecaca; color: #991b1b; }}

        .card-category {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 8px;
        }}

        .card-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 12px;
        }}

        .tag {{
            padding: 3px 8px;
            background: var(--bg-light);
            border-radius: 4px;
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .card-prompt {{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 12px;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }}

        .card-actions {{
            display: flex;
            gap: 8px;
        }}

        .btn {{
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.85rem;
            text-decoration: none;
            cursor: pointer;
            border: none;
            transition: all 0.3s ease;
            font-weight: 500;
            display: inline-block;
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #ff758c 0%, #ff7eb3 100%);
            color: white;
        }}

        .btn-primary:hover {{
            box-shadow: var(--shadow-soft);
            transform: translateY(-2px);
        }}

        .btn-secondary {{
            background: var(--bg-light);
            color: var(--text-main);
            border: 1px solid var(--glass-border);
        }}

        .btn-secondary:hover {{
            border-color: var(--primary-color);
        }}

        /* Lightbox */
        .lightbox {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
            backdrop-filter: blur(5px);
        }}

        .lightbox.active {{
            opacity: 1;
            pointer-events: all;
        }}

        .lightbox-content {{
            max-width: 90%;
            max-height: 85vh;
            border-radius: 8px;
            box-shadow: 0 0 50px rgba(0,0,0,0.5);
            border: 1px solid var(--glass-border);
        }}

        .close-btn {{
            position: absolute;
            top: 30px;
            right: 40px;
            color: white;
            font-size: 40px;
            cursor: pointer;
            transition: color 0.3s;
        }}

        .close-btn:hover {{
            color: var(--primary-color);
        }}

        /* 空状态 */
        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }}

        .empty-state-icon {{
            font-size: 4em;
            margin-bottom: 20px;
            opacity: 0.3;
        }}

        /* 底部 */
        footer {{
            text-align: center;
            padding: 40px 0;
            border-top: 1px solid var(--glass-border);
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-top: 50px;
        }}

        footer strong {{
            color: var(--primary-color);
        }}

        /* 响应式调整 */
        @media (max-width: 768px) {{
            h1 {{ font-size: 1.8rem; }}
            .stats-grid {{ grid-template-columns: 1fr 1fr; }}
            .gallery-grid {{ grid-template-columns: 1fr; }}
            .filter-buttons {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand-avatar">
                <img src="images/logo.png" alt="夕小瑶科技" onerror="this.style.display='none'">
            </div>
            <h1>AI模型测评结果</h1>
            <p class="subtitle">{self.model_name}</p>
            <p class="subtitle" style="font-size: 0.9em; opacity: 0.7;">生成时间: {data['meta']['generated_at'][:19]}</p>

            <div class="stats-grid">
                <div class="stat-card">
                    <span class="stat-value">{data['meta']['total_text']}</span>
                    <span class="stat-label">代码生成测试</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value">{data['meta'].get('total_writing', 0)}</span>
                    <span class="stat-label">文生文测试</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value">{data['meta']['total_image']}</span>
                    <span class="stat-label">文生图测试</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value">{data['meta']['total_text'] + data['meta'].get('total_writing', 0) + data['meta']['total_image']}</span>
                    <span class="stat-label">总测试数</span>
                </div>
            </div>
        </header>

        <!-- 统计数据可视化 -->
        {self.generate_stats_section(data.get('stats', {}))}

        <!-- 搜索和筛选栏 -->
        <div class="filter-bar">
            <input type="text" class="search-box" id="searchBox" placeholder="🔍 搜索测试案例...（支持名称、标签、ID）">

            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <label style="font-size: 0.9rem; color: var(--text-muted); font-weight: 500;">筛选条件:</label>
                <button onclick="resetFilters()" style="padding: 4px 12px; border: none; background: var(--bg-light); border-radius: 6px; cursor: pointer; font-size: 0.85rem;">重置</button>
            </div>

            <div class="filter-buttons">
                <button class="filter-btn active" data-filter="all">全部</button>
                <button class="filter-btn" data-filter="text">代码生成</button>
                <button class="filter-btn" data-filter="writing">文生文</button>
                <button class="filter-btn" data-filter="image">文生图</button>
            </div>

            <div style="margin-top: 15px;">
                <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 8px;">难度:</label>
                <div class="filter-buttons">
                    <button class="filter-btn active" data-difficulty="all">全部</button>
                    <button class="filter-btn" data-difficulty="简单">简单</button>
                    <button class="filter-btn" data-difficulty="中">中等</button>
                    <button class="filter-btn" data-difficulty="高">困难</button>
                </div>
            </div>
        </div>

        <!-- 代码生成结果 -->
        <div id="textSection">
            <h2 class="section-title">
                <span>代码生成测评结果</span>
                <span class="result-count" id="textCount">{len(data['text_results'])} 个案例</span>
            </h2>
            <div class="gallery-grid" id="textGallery">
                {self.generate_text_cards(data['text_results'])}
            </div>
        </div>

        <!-- 文生文结果 -->
        <div id="writingSection">
            <h2 class="section-title">
                <span>文生文测评结果</span>
                <span class="result-count" id="writingCount">{len(data.get('writing_results', []))} 个案例</span>
            </h2>
            <div class="gallery-grid" id="writingGallery">
                {self.generate_writing_cards(data.get('writing_results', []))}
            </div>
        </div>

        <!-- 文生图结果 -->
        <div id="imageSection">
            <h2 class="section-title">
                <span>文生图测评结果</span>
                <span class="result-count" id="imageCount">{len(data['image_results'])} 个案例</span>
            </h2>
            <div class="gallery-grid" id="imageGallery">
                {self.generate_image_cards(data['image_results'])}
            </div>
        </div>

        <!-- 空状态 -->
        <div id="emptyState" class="empty-state" style="display: none;">
            <div class="empty-state-icon">🔍</div>
            <h3>没有找到匹配的测试案例</h3>
            <p>试试调整搜索词或筛选条件</p>
        </div>

        <footer>
            <p>&copy; 2025 <strong>夕小瑶科技 AI 评测实验室</strong>. All Rights Reserved.</p>
            <p style="margin-top: 5px; font-size: 0.8rem; opacity: 0.6;">低负担解码AI世界，硬核也可爱!</p>
        </footer>
    </div>

    <!-- Lightbox -->
    <div class="lightbox" id="lightbox">
        <span class="close-btn" onclick="closeLightbox()">&times;</span>
        <img src="" alt="" class="lightbox-content" id="lightbox-img">
    </div>

    <!-- Writing Modal -->
    <div class="lightbox" id="writingModal">
        <span class="close-btn" onclick="closeWritingModal()">&times;</span>
        <div style="background: white; max-width: 800px; max-height: 85vh; overflow-y: auto; border-radius: 16px; padding: 30px; margin: 20px;">
            <h2 id="writingModalTitle" style="margin-bottom: 20px; color: var(--text-main);"></h2>
            <div style="background: var(--bg-light); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <strong style="color: var(--primary-color);">提示词：</strong>
                <p id="writingModalPrompt" style="margin-top: 8px; color: var(--text-muted);"></p>
            </div>
            <div style="border-top: 1px solid var(--glass-border); padding-top: 20px;">
                <strong style="color: var(--primary-color);">模型响应：</strong>
                <div id="writingModalContent" style="margin-top: 10px; line-height: 1.8; color: var(--text-main);"></div>
            </div>
        </div>
    </div>

    <script>
        // 搜索和筛选逻辑
        let currentFilter = 'all';
        let currentDifficulty = 'all';

        // 搜索功能
        document.getElementById('searchBox').addEventListener('input', function(e) {{
            filterResults();
        }});

        // 类型筛选
        document.querySelectorAll('[data-filter]').forEach(btn => {{
            btn.addEventListener('click', function() {{
                document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentFilter = this.dataset.filter;
                filterResults();
            }});
        }});

        // 难度筛选
        document.querySelectorAll('[data-difficulty]').forEach(btn => {{
            btn.addEventListener('click', function() {{
                document.querySelectorAll('[data-difficulty]').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentDifficulty = this.dataset.difficulty;
                filterResults();
            }});
        }});

        function filterResults() {{
            const searchTerm = document.getElementById('searchBox').value.toLowerCase();
            let visibleTextCount = 0;
            let visibleWritingCount = 0;
            let visibleImageCount = 0;

            // 筛选代码生成
            document.querySelectorAll('#textGallery .gallery-item').forEach(item => {{
                const matchesSearch = !searchTerm ||
                    item.dataset.name.toLowerCase().includes(searchTerm) ||
                    item.dataset.tags.toLowerCase().includes(searchTerm) ||
                    item.dataset.id.toLowerCase().includes(searchTerm);

                const matchesFilter = currentFilter === 'all' || currentFilter === 'text';
                const matchesDifficulty = currentDifficulty === 'all' || item.dataset.difficulty === currentDifficulty;

                if (matchesSearch && matchesFilter && matchesDifficulty) {{
                    item.style.display = '';
                    visibleTextCount++;
                }} else {{
                    item.style.display = 'none';
                }}
            }});

            // 筛选文生文
            document.querySelectorAll('#writingGallery .gallery-item').forEach(item => {{
                const matchesSearch = !searchTerm ||
                    item.dataset.name.toLowerCase().includes(searchTerm) ||
                    item.dataset.tags.toLowerCase().includes(searchTerm) ||
                    item.dataset.id.toLowerCase().includes(searchTerm);

                const matchesFilter = currentFilter === 'all' || currentFilter === 'writing';
                const matchesDifficulty = currentDifficulty === 'all' || item.dataset.difficulty === currentDifficulty;

                if (matchesSearch && matchesFilter && matchesDifficulty) {{
                    item.style.display = '';
                    visibleWritingCount++;
                }} else {{
                    item.style.display = 'none';
                }}
            }});

            // 筛选文生图
            document.querySelectorAll('#imageGallery .gallery-item').forEach(item => {{
                const matchesSearch = !searchTerm ||
                    item.dataset.name.toLowerCase().includes(searchTerm) ||
                    item.dataset.tags.toLowerCase().includes(searchTerm) ||
                    item.dataset.id.toLowerCase().includes(searchTerm);

                const matchesFilter = currentFilter === 'all' || currentFilter === 'image';
                const matchesDifficulty = currentDifficulty === 'all' || item.dataset.difficulty === currentDifficulty;

                if (matchesSearch && matchesFilter && matchesDifficulty) {{
                    item.style.display = '';
                    visibleImageCount++;
                }} else {{
                    item.style.display = 'none';
                }}
            }});

            // 更新计数
            document.getElementById('textCount').textContent = `${{visibleTextCount}} 个案例`;
            document.getElementById('writingCount').textContent = `${{visibleWritingCount}} 个案例`;
            document.getElementById('imageCount').textContent = `${{visibleImageCount}} 个案例`;

            // 显示/隐藏区域
            document.getElementById('textSection').style.display =
                (currentFilter === 'all' || currentFilter === 'text') && visibleTextCount > 0 ? '' : 'none';
            document.getElementById('writingSection').style.display =
                (currentFilter === 'all' || currentFilter === 'writing') && visibleWritingCount > 0 ? '' : 'none';
            document.getElementById('imageSection').style.display =
                (currentFilter === 'all' || currentFilter === 'image') && visibleImageCount > 0 ? '' : 'none';

            // 显示空状态
            const totalVisible = visibleTextCount + visibleWritingCount + visibleImageCount;
            document.getElementById('emptyState').style.display = totalVisible === 0 ? 'block' : 'none';
        }}

        function resetFilters() {{
            document.getElementById('searchBox').value = '';
            currentFilter = 'all';
            currentDifficulty = 'all';
            document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
            document.querySelector('[data-filter="all"]').classList.add('active');
            document.querySelectorAll('[data-difficulty]').forEach(b => b.classList.remove('active'));
            document.querySelector('[data-difficulty="all"]').classList.add('active');
            filterResults();
        }}

        // Lightbox功能
        function openLightbox(src) {{
            document.getElementById('lightbox-img').src = src;
            document.getElementById('lightbox').classList.add('active');
        }}

        function closeLightbox() {{
            document.getElementById('lightbox').classList.remove('active');
        }}

        // Writing Modal功能
        function showWritingModal(id, title, prompt, content) {{
            document.getElementById('writingModalTitle').textContent = title;
            document.getElementById('writingModalPrompt').textContent = prompt;
            document.getElementById('writingModalContent').innerHTML = content;
            document.getElementById('writingModal').classList.add('active');
        }}

        function closeWritingModal() {{
            document.getElementById('writingModal').classList.remove('active');
        }}

        document.getElementById('writingModal').addEventListener('click', function(e) {{
            if (e.target === this) closeWritingModal();
        }});

        document.getElementById('lightbox').addEventListener('click', function(e) {{
            if (e.target === this) closeLightbox();
        }});

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                closeLightbox();
                closeWritingModal();
            }}
        }});
    </script>
</body>
</html>'''
        return html

    def generate_stats_section(self, stats):
        """生成统计数据可视化部分"""
        text_stats = stats.get('text', {})
        writing_stats = stats.get('writing', {})
        image_stats = stats.get('image', {})

        # 计算平均值
        avg_speed = []
        if text_stats.get('avg_tokens_per_second', 0) > 0:
            avg_speed.append(text_stats['avg_tokens_per_second'])
        if writing_stats.get('avg_tokens_per_second', 0) > 0:
            avg_speed.append(writing_stats['avg_tokens_per_second'])
        if image_stats.get('avg_tokens_per_second', 0) > 0:
            avg_speed.append(image_stats['avg_tokens_per_second'])
        overall_avg_speed = sum(avg_speed) / len(avg_speed) if avg_speed else 0

        html = f'''
        <div style="background: white; border-radius: 16px; padding: 30px; margin-bottom: 40px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <h2 style="font-size: 1.5rem; margin-bottom: 25px; color: var(--text-main); border-left: 4px solid var(--primary-color); padding-left: 15px;">
                📊 性能统计数据
            </h2>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px;">
                <!-- 代码生成统计 -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 12px; color: white;">
                    <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 8px;">🔨 代码生成</div>
                    <div style="font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{text_stats.get('avg_tokens_per_second', 0):.1f} <span style="font-size: 0.8rem;">tok/s</span></div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">平均响应: {text_stats.get('avg_time_per_case', 0):.1f}s</div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">成功率: {(text_stats.get('success_count', 0) / text_stats.get('total_cases', 1) * 100) if text_stats.get('total_cases', 0) > 0 else 0:.1f}%</div>
                </div>

                <!-- 文生文统计 -->
                <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 20px; border-radius: 12px; color: white;">
                    <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 8px;">✍️ 文生文</div>
                    <div style="font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{writing_stats.get('avg_tokens_per_second', 0):.1f} <span style="font-size: 0.8rem;">tok/s</span></div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">平均响应: {writing_stats.get('avg_time_per_case', 0):.1f}s</div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">成功率: {(writing_stats.get('success_count', 0) / writing_stats.get('total_cases', 1) * 100) if writing_stats.get('total_cases', 0) > 0 else 0:.1f}%</div>
                </div>

                <!-- 文生图统计 -->
                <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 20px; border-radius: 12px; color: white;">
                    <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 8px;">🎨 文生图</div>
                    <div style="font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{image_stats.get('avg_tokens_per_second', 0):.1f} <span style="font-size: 0.8rem;">tok/s</span></div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">平均响应: {image_stats.get('avg_time_per_case', 0):.1f}s</div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">成功率: {(image_stats.get('success_count', 0) / image_stats.get('total_cases', 1) * 100) if image_stats.get('total_cases', 0) > 0 else 0:.1f}%</div>
                </div>

                <!-- 综合统计 -->
                <div style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); padding: 20px; border-radius: 12px; color: white;">
                    <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 8px;">⚡ 综合性能</div>
                    <div style="font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{overall_avg_speed:.1f} <span style="font-size: 0.8rem;">tok/s</span></div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">总用时: {text_stats.get('total_time_seconds', 0) + writing_stats.get('total_time_seconds', 0) + image_stats.get('total_time_seconds', 0):.1f}s</div>
                    <div style="font-size: 0.85rem; opacity: 0.8;">总tokens: {text_stats.get('total_tokens', {}).get('total_tokens', 0) + writing_stats.get('total_tokens', {}).get('total_tokens', 0) + image_stats.get('total_tokens', {}).get('total_tokens', 0):,}</div>
                </div>
            </div>

            <!-- Token使用详情 -->
            <div style="background: var(--bg-light); padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                <h3 style="font-size: 1.1rem; margin-bottom: 15px; color: var(--text-main);">💎 Token使用统计</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px;">
                    <div>
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 5px;">输入Tokens</div>
                        <div style="font-size: 1.5rem; font-weight: 600; color: var(--primary-color);">{text_stats.get('total_tokens', {}).get('prompt_tokens', 0) + writing_stats.get('total_tokens', {}).get('prompt_tokens', 0) + image_stats.get('total_tokens', {}).get('prompt_tokens', 0):,}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 5px;">输出Tokens</div>
                        <div style="font-size: 1.5rem; font-weight: 600; color: var(--primary-color);">{text_stats.get('total_tokens', {}).get('completion_tokens', 0) + writing_stats.get('total_tokens', {}).get('completion_tokens', 0) + image_stats.get('total_tokens', {}).get('completion_tokens', 0):,}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 5px;">平均输出/案例</div>
                        <div style="font-size: 1.5rem; font-weight: 600; color: var(--primary-color);">{((text_stats.get('avg_output_tokens_per_case', 0) + writing_stats.get('avg_output_tokens_per_case', 0) + image_stats.get('avg_output_tokens_per_case', 0)) / 3):.0f}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 5px;">总重试次数</div>
                        <div style="font-size: 1.5rem; font-weight: 600; color: var(--primary-color);">{text_stats.get('retry_count', 0) + writing_stats.get('retry_count', 0) + image_stats.get('retry_count', 0)}</div>
                    </div>
                </div>
            </div>

            <!-- 可视化图表 -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <!-- 速度对比图 -->
                <div style="background: white; padding: 20px; border: 1px solid var(--glass-border); border-radius: 12px;">
                    <h4 style="font-size: 1rem; margin-bottom: 15px; color: var(--text-main);">生成速度对比 (tok/s)</h4>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        {self.generate_bar('代码生成', text_stats.get('avg_tokens_per_second', 0), overall_avg_speed if overall_avg_speed > 0 else 100, '#667eea')}
                        {self.generate_bar('文生文', writing_stats.get('avg_tokens_per_second', 0), overall_avg_speed if overall_avg_speed > 0 else 100, '#f5576c')}
                        {self.generate_bar('文生图', image_stats.get('avg_tokens_per_second', 0), overall_avg_speed if overall_avg_speed > 0 else 100, '#00f2fe')}
                    </div>
                </div>

                <!-- 成功率对比图 -->
                <div style="background: white; padding: 20px; border: 1px solid var(--glass-border); border-radius: 12px;">
                    <h4 style="font-size: 1rem; margin-bottom: 15px; color: var(--text-main);">测试成功率 (%)</h4>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        {self.generate_bar('代码生成', (text_stats.get('success_count', 0) / text_stats.get('total_cases', 1) * 100) if text_stats.get('total_cases', 0) > 0 else 0, 100, '#10b981')}
                        {self.generate_bar('文生文', (writing_stats.get('success_count', 0) / writing_stats.get('total_cases', 1) * 100) if writing_stats.get('total_cases', 0) > 0 else 0, 100, '#10b981')}
                        {self.generate_bar('文生图', (image_stats.get('success_count', 0) / image_stats.get('total_cases', 1) * 100) if image_stats.get('total_cases', 0) > 0 else 0, 100, '#10b981')}
                    </div>
                </div>
            </div>
        </div>
        '''
        return html

    def generate_bar(self, label, value, max_value, color):
        """生成单个条形图"""
        percentage = (value / max_value * 100) if max_value > 0 else 0
        return f'''
        <div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 0.85rem; color: var(--text-muted);">{label}</span>
                <span style="font-size: 0.85rem; font-weight: 600; color: var(--text-main);">{value:.1f}</span>
            </div>
            <div style="background: #e5e7eb; height: 8px; border-radius: 4px; overflow: hidden;">
                <div style="background: {color}; height: 100%; width: {percentage:.1f}%; transition: width 1s ease;"></div>
            </div>
        </div>
        '''

    def generate_text_cards(self, results):
        """生成代码生成卡片（带图标）"""
        cards = []
        for r in results:
            icon = r.get('icon', '📄')
            difficulty = r.get('difficulty', '中')
            category = r.get('category', '未分类')
            tags = r.get('tags', [])
            tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in tags[:3]])

            # 根据分类选择背景样式
            bg_class = self.get_category_bg_class(category)

            html_btn = ""
            if r.get("html_file"):
                html_btn = f'<a href="{r["html_file"]}" target="_blank" class="btn btn-primary">查看演示</a>'

            card = f'''
            <div class="gallery-item" data-name="{r.get('name', '')}" data-id="{r.get('id', '')}" data-tags="{' '.join(tags)}" data-difficulty="{difficulty}">
                <div class="icon-bg {bg_class}">
                    <div class="icon-emoji">{icon}</div>
                </div>
                <div class="card-info">
                    <div class="card-header">
                        <div class="card-title">{r.get('name', '未命名')}</div>
                        <span class="difficulty-badge difficulty-{difficulty}">{difficulty}</span>
                    </div>
                    <div class="card-category">📁 {category}</div>
                    <div class="card-tags">{tags_html}</div>
                    <div class="card-prompt">{r.get('prompt', '')[:100]}...</div>
                    <div class="card-actions">
                        {html_btn}
                    </div>
                </div>
            </div>
            '''
            cards.append(card)
        return "".join(cards)

    def get_category_bg_class(self, category):
        """根据分类返回背景样式类"""
        category_map = {
            '交互游戏': 'game',
            '实用工具': 'tool',
            '动画效果': 'animation',
            '3D图形': 'graphics',
            '视觉代码生成': 'graphics',
            '视觉效果': 'graphics',
            '音频可视化': 'audio',
            '多媒体': 'audio',
            'UI布局': 'ui',
            '数据可视化': 'data',
            '算法/模拟': 'data',
            '科学模拟': 'data',
            # 文生文分类
            '新闻写作': 'tool',
            '营销文案': 'ui',
            '技术写作': 'data',
            '创意写作': 'animation',
            '商务写作': 'tool',
            '知识解答': 'data',
            '演讲写作': 'ui',
            '说明文写作': 'tool',
            '评论写作': 'graphics',
            '应用写作': 'tool',
            '科普写作': 'data',
            '产品写作': 'ui',
            '议论写作': 'game',
            '叙事写作': 'animation',
        }
        return category_map.get(category, '')

    def generate_writing_cards(self, results):
        """生成文生文卡片（优化版 - 更美观完整）"""
        cards = []
        for r in results:
            icon = r.get('icon', '📝')
            difficulty = r.get('difficulty', '中')
            category = r.get('category', '未分类')
            tags = r.get('tags', [])
            tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in tags[:4]])

            # 根据分类选择背景样式
            bg_class = self.get_category_bg_class(category)

            # 获取响应内容预览（更长的预览）
            response_preview = r.get('response', '')[:350] if r.get('response') else ''
            response_preview_html = response_preview.replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ').replace('"', '&quot;')
            if len(r.get('response', '')) > 350:
                response_preview_html += '...'

            # 完整响应用于模态框显示（保留换行）
            full_response = r.get('response', '').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>').replace('"', '&quot;')

            # 字数统计
            char_count = r.get('char_count', len(r.get('response', '')))

            # 提示词预览
            prompt_preview = r.get('prompt', '')[:120]
            if len(r.get('prompt', '')) > 120:
                prompt_preview += '...'

            card = f'''
            <div class="gallery-item writing-card" data-name="{r.get('name', '')}" data-id="{r.get('id', '')}" data-tags="{' '.join(tags)}" data-difficulty="{difficulty}">
                <!-- 图标头部 -->
                <div class="icon-bg {bg_class}" style="height: 160px; position: relative;">
                    <div class="icon-emoji" style="font-size: 4.5em; position: relative; z-index: 2;">{icon}</div>
                    <div style="position: absolute; bottom: 15px; left: 0; right: 0; text-align: center; z-index: 2;">
                        <span style="background: rgba(255,255,255,0.95); padding: 6px 16px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; color: var(--text-main);">
                            {category}
                        </span>
                    </div>
                </div>

                <!-- 卡片内容 -->
                <div class="card-info" style="padding: 24px 20px;">
                    <!-- 标题行 -->
                    <div class="card-header" style="margin-bottom: 12px;">
                        <div class="card-title" style="font-size: 1.15rem; line-height: 1.4;">{r.get('name', '未命名')}</div>
                        <span class="difficulty-badge difficulty-{difficulty}">{difficulty}</span>
                    </div>

                    <!-- 统计信息 -->
                    <div style="display: flex; gap: 15px; margin-bottom: 12px; padding: 10px; background: var(--bg-light); border-radius: 8px;">
                        <div style="flex: 1; text-align: center;">
                            <div style="font-size: 1.3rem; font-weight: 700; color: var(--primary-color);">{char_count}</div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">字数</div>
                        </div>
                        <div style="width: 1px; background: var(--glass-border);"></div>
                        <div style="flex: 1; text-align: center;">
                            <div style="font-size: 1.3rem; font-weight: 700; color: var(--accent-color);">{len(tags)}</div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">标签</div>
                        </div>
                        <div style="width: 1px; background: var(--glass-border);"></div>
                        <div style="flex: 1; text-align: center;">
                            <div style="font-size: 1.3rem; font-weight: 700; color: #10b981;">✓</div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">完成</div>
                        </div>
                    </div>

                    <!-- 标签 -->
                    <div class="card-tags" style="margin-bottom: 12px;">
                        {tags_html}
                    </div>

                    <!-- 提示词预览 -->
                    <div style="background: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid var(--primary-color);">
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; font-weight: 600;">📋 提示词</div>
                        <div style="font-size: 0.85rem; color: var(--text-main); line-height: 1.5;">{prompt_preview}</div>
                    </div>

                    <!-- 响应内容预览 -->
                    <div style="background: linear-gradient(to bottom, #ffffff, #f8f9fa); padding: 14px; border-radius: 10px; border: 1px solid var(--glass-border); margin-bottom: 15px;">
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px; font-weight: 600;">✨ 响应内容预览</div>
                        <div style="font-size: 0.9rem; color: var(--text-main); line-height: 1.7; max-height: 105px; overflow: hidden; text-overflow: ellipsis;">{response_preview_html}</div>
                    </div>

                    <!-- 操作按钮 -->
                    <div class="card-actions">
                        <button class="btn btn-primary" onclick="showWritingModal('{r.get('id', '')}', '{r.get('name', '').replace(chr(39), chr(92)+chr(39))}', '{r.get('prompt', '').replace(chr(39), chr(92)+chr(39)).replace(chr(10), ' ')[:200]}', `{full_response}`)" style="width: 100%; justify-content: center; display: flex; align-items: center; gap: 8px;">
                            <span>📖</span>
                            <span>查看完整内容</span>
                        </button>
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
            difficulty = r.get('difficulty', '中')
            category = r.get('category', '未分类')
            tags = r.get('tags', [])

            if r.get("image_file"):
                img_html = f'<img src="{r["image_file"]}" alt="{r.get("name", "")}" class="gallery-img" onclick="openLightbox(\'{r["image_file"]}\')">'
            else:
                icon = r.get('icon', '🖼️')
                img_html = f'<div class="icon-bg"><div class="icon-emoji">{icon}</div></div>'

            card = f'''
            <div class="gallery-item" data-name="{r.get('name', '')}" data-id="{r.get('id', '')}" data-tags="{' '.join(tags)}" data-difficulty="{difficulty}">
                {img_html}
                <div class="item-overlay">
                    <span class="item-category">{category}</span>
                    <div class="item-title">{r.get('name', '未命名')}</div>
                </div>
            </div>
            '''
            cards.append(card)
        return "".join(cards)


# 保持向后兼容
WebsiteGenerator = EnhancedWebsiteGenerator
