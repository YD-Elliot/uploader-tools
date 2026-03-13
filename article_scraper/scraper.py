#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文章抓取模块
负责从 URL 抓取文章内容并保存到 output 文件夹
"""

import os
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path


class ArticleScraper:
    def __init__(self, output_dir='output'):
        self.output_dir = Path(output_dir)
        self._ensure_output_dir()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, title):
        """清理文件名中的非法字符"""
        title = title.strip() or 'untitled'
        title = re.sub(r'[<>:"/\\|？*]', '_', title)
        return title[:100]

    def _extract_content(self, soup):
        """从 HTML 中提取标题和正文"""
        # 提取标题
        title = soup.find('h1')
        if not title:
            title = soup.find('title')
        title_text = title.get_text(strip=True) if title else 'untitled'

        # 提取正文
        content_tags = [
            'article',
            'main',
            {'name': 'div', 'class': lambda x: x and 'content' in x},
            {'name': 'div', 'class': lambda x: x and 'post' in x},
            {'name': 'div', 'class': lambda x: x and 'article' in x},
        ]
        
        content = None
        for tag in content_tags:
            if isinstance(tag, str):
                content = soup.find(tag)
            elif isinstance(tag, dict):
                content = soup.find(tag['name'], class_=tag['class'])
            
            if content:
                break

        if not content:
            content = soup.find('body')

        text = content.get_text(separator='\n', strip=True) if content else ''
        return title_text, text

    def scrape(self, url):
        """抓取单篇文章"""
        try:
            print(f"🌐 正在抓取：{url}")
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            # 自动检测编码
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'html.parser')
            title, content = self._extract_content(soup)

            filename = self._sanitize_filename(title)
            filepath = self.output_dir / f"{filename}.txt"

            # 保存文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"标题：{title}\n")
                f.write(f"来源：{url}\n")
                f.write(f"抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                f.write(content)

            print(f"✅ 保存成功：{filepath}")
            return {
                'success': True,
                'filepath': str(filepath),
                'title': title,
                'url': url
            }

        except Exception as e:
            print(f"❌ 抓取失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'url': url
            }

    def scrape_batch(self, urls, delay=1):
        """批量抓取文章"""
        import time
        
        results = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] 处理：{url}")
            result = self.scrape(url)
            results.append(result)
            
            # 添加延时避免请求过快
            if i < len(urls) and delay > 0:
                time.sleep(delay)
        
        success_count = sum(1 for r in results if r['success'])
        print(f"\n{'='*50}")
        print(f"📊 抓取完成：成功 {success_count}/{len(urls)} 篇")
        
        return results


# 独立运行测试
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        urls = sys.argv[1:]
        scraper = ArticleScraper()
        scraper.scrape_batch(urls)
    else:
        print("用法：python scraper.py <url1> [url2] [url3] ...")