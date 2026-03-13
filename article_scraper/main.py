#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主控制文件
整合文章抓取和 LLM 分析工作流
支持命令行参数控制

默认目录：
- 抓取文章 → output_articles/
- AI 摘要 → output_summary/
"""

import os
import sys
import argparse
import time
from pathlib import Path
from datetime import datetime

# 导入自定义模块
from scraper import ArticleScraper
from analyzer import LLMAnalyzer, SummaryManager, ConfigLoader


# ==================== 全局默认配置 ====================
DEFAULT_OUTPUT_DIR = 'output_articles'    # 抓取文章存放目录
DEFAULT_SUMMARY_DIR = 'output_summary'    # AI 摘要存放目录
DEFAULT_CONFIG_FILE = 'config.yaml'       # 配置文件路径
# ====================================================


def print_banner():
    """打印欢迎横幅"""
    print("=" * 60)
    print("📰 文章抓取 + AI 分析自动化工作流")
    print("=" * 60)
    print(f"⏰ 启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 文章目录：{DEFAULT_OUTPUT_DIR}/")
    print(f"📋 摘要目录：{DEFAULT_SUMMARY_DIR}/")
    print("=" * 60)


def validate_urls(urls):
    """验证 URL 格式"""
    import re
    pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    valid_urls = []
    for url in urls:
        if pattern.match(url):
            valid_urls.append(url)
        else:
            print(f"⚠️  无效 URL 已跳过：{url}")
    
    return valid_urls


def mode_scrape(args):
    """仅抓取模式"""
    print(f"\n🔍 模式：仅抓取文章 → {args.output}/")
    
    urls = validate_urls(args.urls)
    if not urls:
        print("❌ 没有有效的 URL")
        return False
    
    scraper = ArticleScraper(output_dir=args.output)
    results = scraper.scrape_batch(urls, delay=args.delay)
    
    success_count = sum(1 for r in results if r.get('success'))
    return success_count > 0


def mode_analyze(args):
    """仅分析模式"""
    print(f"\n🤖 模式：仅分析文章")
    print(f"   输入：{args.input}/")
    print(f"   输出：{args.output}/")
    
    try:
        analyzer = LLMAnalyzer(config_path=args.config)
        manager = SummaryManager(
            input_dir=args.input,
            summary_dir=args.output
        )
        results = manager.process_all(analyzer, skip_existing=not args.no_skip)
        
        success_count = sum(1 for r in results if r['status'] == 'success')
        return success_count > 0
    
    except Exception as e:
        print(f"❌ 分析失败：{e}")
        return False


def mode_full(args):
    """全流程模式（抓取 + 分析）"""
    print(f"\n🚀 模式：全流程（抓取 + 分析）")
    print(f"   文章保存：{args.output}/")
    print(f"   摘要保存：{args.summary}/")
    
    # 步骤 1: 抓取
    urls = validate_urls(args.urls)
    if not urls:
        print("❌ 没有有效的 URL")
        return False
    
    print("\n" + "=" * 60)
    print("步骤 1/2: 抓取文章")
    print("=" * 60)
    
    scraper = ArticleScraper(output_dir=args.output)
    scrape_results = scraper.scrape_batch(urls, delay=args.delay)
    
    scrape_success = sum(1 for r in scrape_results if r.get('success'))
    if scrape_success == 0:
        print("❌ 抓取阶段失败，终止流程")
        return False
    
    # 步骤 2: 分析
    print("\n" + "=" * 60)
    print("步骤 2/2: AI 分析")
    print("=" * 60)
    
    try:
        analyzer = LLMAnalyzer(config_path=args.config)
        manager = SummaryManager(
            input_dir=args.output,
            summary_dir=args.summary
        )
        analyze_results = manager.process_all(analyzer, skip_existing=not args.no_skip)
        
        analyze_success = sum(1 for r in analyze_results if r['status'] == 'success')
        
        print("\n" + "=" * 60)
        print("📊 全流程总结")
        print("=" * 60)
        print(f"✅ 抓取成功：{scrape_success}/{len(urls)} 篇")
        print(f"✅ 分析成功：{analyze_success}/{len(analyze_results)} 篇")
        print("=" * 60)
        
        return analyze_success > 0
    
    except Exception as e:
        print(f"❌ 分析阶段失败：{e}")
        return False


def mode_status(args):
    """状态检查模式"""
    print("\n📊 模式：状态检查")
    
    config_path = Path(args.config)
    output_dir = Path(args.output)
    summary_dir = Path(args.summary)
    
    checks = []
    
    # 检查配置文件
    if config_path.exists():
        checks.append(("✅ 配置文件", str(config_path)))
        try:
            config = ConfigLoader(args.config)
            provider = config.get('llm.provider', 'unknown')
            api_key = config.get('llm.api_key', '')
            if api_key and api_key != 'your_api_key_here':
                checks.append(("✅ API Key", f"已配置 ({provider})"))
            else:
                checks.append(("⚠️  API Key", "未配置或为默认值"))
        except Exception as e:
            checks.append(("❌ 配置文件", f"读取失败：{e}"))
    else:
        checks.append(("❌ 配置文件", "不存在"))
    
    # 检查目录
    checks.append(("📁 文章目录", f"{output_dir} ({output_dir.exists()})"))
    checks.append(("📁 摘要目录", f"{summary_dir} ({summary_dir.exists()})"))
    
    # 统计文件
    if output_dir.exists():
        article_count = len(list(output_dir.glob('*.txt')))
        checks.append(("📄 文章文件", f"{article_count} 个"))
    
    if summary_dir.exists():
        summary_count = len(list(summary_dir.glob('*_summary.txt')))
        checks.append(("📄 摘要文件", f"{summary_count} 个"))
    
    # 打印检查结果
    print("\n" + "-" * 60)
    for item, status in checks:
        print(f"{item}: {status}")
    print("-" * 60)
    
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='📰 文章抓取 + AI 分析自动化工作流',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例用法:
  # 仅抓取文章（保存到 {DEFAULT_OUTPUT_DIR}/）
  python main.py scrape https://example.com/article1 https://example.com/article2

  # 仅分析已有文章（读取 {DEFAULT_OUTPUT_DIR}/ → 输出到 {DEFAULT_SUMMARY_DIR}/）
  python main.py analyze

  # 全流程（抓取 + 分析）
  python main.py full https://example.com/article1

  # 检查状态
  python main.py status

  # 使用自定义目录
  python main.py full https://example.com/article1 -o my_articles -s my_summaries

  # 使用自定义配置文件
  python main.py full https://example.com/article1 --config my_config.yaml
        """
    )
    
    # 全局参数
    parser.add_argument('-c', '--config', default=DEFAULT_CONFIG_FILE,
                       help=f'配置文件路径 (默认：{DEFAULT_CONFIG_FILE})')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='显示详细信息')
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='工作模式')
    
    # 抓取命令
    scrape_parser = subparsers.add_parser('scrape', help='仅抓取文章')
    scrape_parser.add_argument('urls', nargs='+', help='文章 URL 列表')
    scrape_parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_DIR,
                              help=f'输出文件夹 (默认：{DEFAULT_OUTPUT_DIR})')
    scrape_parser.add_argument('-d', '--delay', type=float, default=1.0,
                              help='请求间隔秒数 (默认：1.0)')
    
    # 分析命令
    analyze_parser = subparsers.add_parser('analyze', help='仅分析文章')
    analyze_parser.add_argument('-i', '--input', default=DEFAULT_OUTPUT_DIR,
                               help=f'输入文件夹 (默认：{DEFAULT_OUTPUT_DIR})')
    analyze_parser.add_argument('-o', '--output', default=DEFAULT_SUMMARY_DIR,
                               help=f'摘要输出文件夹 (默认：{DEFAULT_SUMMARY_DIR})')
    analyze_parser.add_argument('--no-skip', action='store_true',
                               help='重新处理已分析的文件')
    
    # 全流程命令
    full_parser = subparsers.add_parser('full', help='抓取 + 分析全流程')
    full_parser.add_argument('urls', nargs='+', help='文章 URL 列表')
    full_parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_DIR,
                            help=f'文章输出文件夹 (默认：{DEFAULT_OUTPUT_DIR})')
    full_parser.add_argument('-s', '--summary', default=DEFAULT_SUMMARY_DIR,
                            help=f'摘要输出文件夹 (默认：{DEFAULT_SUMMARY_DIR})')
    full_parser.add_argument('-d', '--delay', type=float, default=1.0,
                            help='请求间隔秒数 (默认：1.0)')
    full_parser.add_argument('--no-skip', action='store_true',
                            help='重新处理已分析的文件')
    
    # 状态命令
    status_parser = subparsers.add_parser('status', help='检查系统状态')
    status_parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_DIR,
                              help=f'文章文件夹 (默认：{DEFAULT_OUTPUT_DIR})')
    status_parser.add_argument('-s', '--summary', default=DEFAULT_SUMMARY_DIR,
                              help=f'摘要文件夹 (默认：{DEFAULT_SUMMARY_DIR})')
    
    args = parser.parse_args()
    
    # 打印欢迎信息
    print_banner()
    
    # 检查配置文件
    if not Path(args.config).exists():
        print(f"⚠️  配置文件不存在：{args.config}")
        print("💡 请复制 config.yaml.example 为 config.yaml 并配置 API Key")
        print("\n命令：cp config.yaml.example config.yaml")
        sys.exit(1)
    
    # 执行对应模式
    if args.command == 'scrape':
        success = mode_scrape(args)
    elif args.command == 'analyze':
        success = mode_analyze(args)
    elif args.command == 'full':
        success = mode_full(args)
    elif args.command == 'status':
        success = mode_status(args)
    else:
        parser.print_help()
        sys.exit(0)
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()