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
        image_results = self.collect_results("image")

        # 生成精简数据文件
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
            simplified.append(simple_r)
        return simplified

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
                    <span class="stat-label">文生文测试</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value">{data['meta']['total_image']}</span>
                    <span class="stat-label">文生图测试</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value">{data['meta']['total_text'] + data['meta']['total_image']}</span>
                    <span class="stat-label">总测试数</span>
                </div>
            </div>
        </header>

        <!-- 搜索和筛选栏 -->
        <div class="filter-bar">
            <input type="text" class="search-box" id="searchBox" placeholder="🔍 搜索测试案例...（支持名称、标签、ID）">

            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <label style="font-size: 0.9rem; color: var(--text-muted); font-weight: 500;">筛选条件:</label>
                <button onclick="resetFilters()" style="padding: 4px 12px; border: none; background: var(--bg-light); border-radius: 6px; cursor: pointer; font-size: 0.85rem;">重置</button>
            </div>

            <div class="filter-buttons">
                <button class="filter-btn active" data-filter="all">全部</button>
                <button class="filter-btn" data-filter="text">文生文</button>
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

        <!-- 文生文结果 -->
        <div id="textSection">
            <h2 class="section-title">
                <span>文生文测评结果</span>
                <span class="result-count" id="textCount">{len(data['text_results'])} 个案例</span>
            </h2>
            <div class="gallery-grid" id="textGallery">
                {self.generate_text_cards(data['text_results'])}
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
            let visibleImageCount = 0;

            // 筛选文生文
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
            document.getElementById('imageCount').textContent = `${{visibleImageCount}} 个案例`;

            // 显示/隐藏区域
            document.getElementById('textSection').style.display =
                (currentFilter === 'all' || currentFilter === 'text') && visibleTextCount > 0 ? '' : 'none';
            document.getElementById('imageSection').style.display =
                (currentFilter === 'all' || currentFilter === 'image') && visibleImageCount > 0 ? '' : 'none';

            // 显示空状态
            const totalVisible = visibleTextCount + visibleImageCount;
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

        document.getElementById('lightbox').addEventListener('click', function(e) {{
            if (e.target === this) closeLightbox();
        }});

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeLightbox();
        }});
    </script>
</body>
</html>'''
        return html

    def generate_text_cards(self, results):
        """生成文生文卡片（带图标）"""
        cards = []
        for r in results:
            icon = r.get('icon', '📄')
            difficulty = r.get('difficulty', '中')
            category = r.get('category', '未分类')
            tags = r.get('tags', [])
            tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in tags[:3]])

            html_btn = ""
            if r.get("html_file"):
                html_btn = f'<a href="{r["html_file"]}" target="_blank" class="btn btn-primary">查看演示</a>'

            card = f'''
            <div class="gallery-item" data-name="{r.get('name', '')}" data-id="{r.get('id', '')}" data-tags="{' '.join(tags)}" data-difficulty="{difficulty}">
                <div class="icon-bg">
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
