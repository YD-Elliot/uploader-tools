#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 分析模块
负责读取 output 文件夹中的文章，调用 AI 进行分析，保存到 summary 文件夹

支持的 LLM 提供商：
- openai: OpenAI GPT 系列
- anthropic: Claude 系列
- qwen: 通义千问（阿里云 DashScope）
- local: 本地模型（如 Ollama）
"""

import os
import json
import yaml
import requests
from pathlib import Path
from datetime import datetime


class ConfigLoader:
    """配置文件加载器"""
    
    def __init__(self, config_path='config.yaml'):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self):
        """加载 YAML 配置"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在：{self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get(self, key, default=None):
        """获取配置值，支持嵌套键（如 'llm.api_key'）"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value


class LLMAnalyzer:
    """LLM 分析器 - 支持多提供商"""
    
    # 提供商默认模型映射
    DEFAULT_MODELS = {
        'openai': 'gpt-3.5-turbo',
        'anthropic': 'claude-3-sonnet-20240229',
        'qwen': 'qwen-plus',
        'local': 'llama2'
    }
    
    # Qwen 默认端点
    QWEN_API_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    
    def __init__(self, config_path='config.yaml'):
        self.config = ConfigLoader(config_path)
        self.provider = self.config.get('llm.provider', 'openai')
        self.model = self.config.get('llm.model') or self.DEFAULT_MODELS.get(self.provider)
        self.api_key = self.config.get('llm.api_key')
        self.api_base = self.config.get('llm.api_base')
        
        # 验证配置
        if not self.api_key:
            raise ValueError("API Key 未配置，请检查 config.yaml 中的 llm.api_key")
        
        if self.provider not in self.DEFAULT_MODELS:
            raise ValueError(f"不支持的 LLM 提供商：{self.provider}，支持：{list(self.DEFAULT_MODELS.keys())}")
        
        # 初始化客户端
        self._init_client()
    
    def _init_client(self):
        """初始化 LLM 客户端"""
        if self.provider in ('openai', 'qwen'):
            # OpenAI 和 Qwen 都使用 OpenAI 兼容接口
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("请安装 openai 库：pip install openai")
            
            # 确定 API 端点
            base_url = self.api_base
            if self.provider == 'qwen' and not base_url:
                base_url = self.QWEN_API_BASE
            
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=base_url
            )
        
        elif self.provider == 'anthropic':
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError("请安装 anthropic 库：pip install anthropic")
            
            self.client = Anthropic(api_key=self.api_key)
        
        elif self.provider == 'local':
            # 本地模型（如 Ollama）使用 HTTP API
            self.api_url = self.api_base or 'http://localhost:11434/api/generate'
            self.client = None
        
        else:
            raise ValueError(f"不支持的 LLM 提供商：{self.provider}")

    def analyze(self, content, prompt_template=None):
        """
        分析文章内容
        
        Args:
            content: 文章正文内容
            prompt_template: 可选的提示词模板，{content} 会被替换为实际内容
        
        Returns:
            str: AI 返回的分析结果，失败时返回 None
        """
        if prompt_template is None:
            prompt_template = self.config.get(
                'llm.prompt_template',
                self._get_default_prompt()
            )
        
        # 限制内容长度，避免超令牌限制
        max_length = self.config.get('llm.max_content_length', 8000)
        if len(content) > max_length:
            print(f"⚠️  内容过长 ({len(content)} 字符)，已截断至 {max_length} 字符")
            content = content[:max_length]
        
        prompt = prompt_template.format(content=content)
        
        try:
            if self.provider in ('openai', 'qwen'):
                return self._analyze_openai_compatible(prompt)
            elif self.provider == 'anthropic':
                return self._analyze_anthropic(prompt)
            elif self.provider == 'local':
                return self._analyze_local(prompt)
        except Exception as e:
            print(f"❌ LLM 分析失败 [{self.provider}]: {type(e).__name__}: {e}")
            return None

    def _get_default_prompt(self):
        """获取默认提示词模板"""
        return """
请对以下文章内容进行整理分析，输出结构化的总结：

1. 核心主题（一句话概括）
2. 主要观点（列出 3-5 个关键点，用 - 开头）
3. 重要数据/事实（如有，用 - 开头）
4. 结论/建议
5. 相关关键词（5-10 个，用逗号分隔）

要求：
- 使用中文回答
- 保持客观，不要添加原文没有的信息
- 格式清晰，便于阅读

文章内容：
{content}
"""

    def _analyze_openai_compatible(self, prompt):
        """
        通过 OpenAI 兼容接口分析（支持 OpenAI / Qwen）
        """
        temperature = self.config.get('llm.temperature', 0.3)
        max_tokens = self.config.get('llm.max_tokens', 1500)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个专业的内容分析助手，擅长提取文章核心信息并生成结构化总结。"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()

    def _analyze_anthropic(self, prompt):
        """
        通过 Anthropic Claude 接口分析
        """
        max_tokens = self.config.get('llm.max_tokens', 1500)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ],
            system="你是一个专业的内容分析助手，擅长提取文章核心信息并生成结构化总结。"
        )
        return response.content[0].text.strip()

    def _analyze_local(self, prompt):
        """
        通过本地模型接口分析（如 Ollama）
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.get('llm.temperature', 0.3),
                "num_predict": self.config.get('llm.max_tokens', 1500)
            }
        }
        
        response = requests.post(
            self.api_url, 
            json=payload, 
            timeout=120,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('response', '').strip()


class SummaryManager:
    """摘要管理器 - 负责文件读写和批量处理"""
    
    def __init__(self, input_dir='output', summary_dir='summary'):
        self.input_dir = Path(input_dir)
        self.summary_dir = Path(summary_dir)
        self._ensure_summary_dir()

    def _ensure_summary_dir(self):
        """确保摘要目录存在"""
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        if not self.input_dir.exists():
            self.input_dir.mkdir(parents=True, exist_ok=True)

    def get_article_files(self):
        """
        获取 input 目录中所有待分析的文章文件
        
        Returns:
            list[Path]: 文章文件路径列表（排除已生成的摘要文件）
        """
        files = []
        for filepath in self.input_dir.glob('*.txt'):
            # 跳过已生成的摘要文件
            if not filepath.name.endswith('_summary.txt'):
                files.append(filepath)
        return sorted(files)

    def read_article(self, filepath):
        """
        读取文章文件，分离元信息和正文
        
        Args:
            filepath: 文章文件路径
        
        Returns:
            tuple: (meta str, body: str)
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取正文（跳过元信息头）
        # 格式约定：元信息以 "=====" 分隔线结束
        lines = content.split('\n')
        body_start = 0
        for i, line in enumerate(lines):
            if line.startswith('=' * 10):
                body_start = i + 1
                break
        
        body = '\n'.join(lines[body_start:]).strip()
        metadata = '\n'.join(lines[:body_start]).strip()
        
        return metadata, body

    def save_summary(self, filename, summary, metadata):
        """
        保存分析摘要到文件
        
        Args:
            filename: 输出文件名
            summary: AI 生成的摘要内容
            meta 原文元信息（标题、来源、时间等）
        
        Returns:
            Path: 保存的文件路径
        """
        filepath = self.summary_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(metadata)
            f.write("\n" + "=" * 50 + "\n")
            f.write("📋 AI 分析摘要\n")
            f.write("=" * 50 + "\n\n")
            f.write(summary)
            f.write("\n\n" + "-" * 50 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return filepath

    def process_all(self, analyzer, skip_existing=True):
        """
        批量处理 input 目录中的所有文章
        
        Args:
            analyzer: LLMAnalyzer 实例
            skip_existing: 是否跳过已处理的文件
        
        Returns:
            list[dict]: 处理结果列表
        """
        files = self.get_article_files()
        if not files:
            print("⚠️  输入文件夹中没有待分析的文章文件")
            print(f"📁 检查目录：{self.input_dir}")
            return []

        results = []
        for i, filepath in enumerate(files, 1):
            filename = filepath.name
            summary_filename = filename.replace('.txt', '_summary.txt')
            summary_path = self.summary_dir / summary_filename

            # 检查是否跳过
            if skip_existing and summary_path.exists():
                print(f"⏭️  跳过已处理：{filename}")
                results.append({'file': filename, 'status': 'skipped', 'path': str(summary_path)})
                continue

            print(f"\n[{i}/{len(files)}] 分析：{filename}")
            
            try:
                metadata, content = self.read_article(filepath)
                
                # 检查内容长度
                if len(content) < 100:
                    print(f"⚠️  内容过短（{len(content)} 字符），跳过：{filename}")
                    results.append({'file': filename, 'status': 'skipped_short'})
                    continue

                # 调用 AI 分析
                print(f"🤖  调用 {analyzer.provider} ({analyzer.model}) 分析中...")
                summary = analyzer.analyze(content)
                
                if summary:
                    saved_path = self.save_summary(summary_filename, summary, metadata)
                    print(f"✅ 摘要保存：{saved_path}")
                    results.append({
                        'file': filename, 
                        'status': 'success', 
                        'summary': str(saved_path),
                        'length': len(summary)
                    })
                else:
                    print(f"❌ 分析返回为空：{filename}")
                    results.append({'file': filename, 'status': 'failed_empty'})

            except KeyboardInterrupt:
                print(f"\n⚠️  用户中断，已处理 {i-1}/{len(files)} 篇")
                break
            except Exception as e:
                print(f"❌ 处理错误 {filename}: {type(e).__name__}: {e}")
                results.append({'file': filename, 'status': 'error', 'error': str(e)})

        # 汇总统计
        success_count = sum(1 for r in results if r['status'] == 'success')
        skipped_count = sum(1 for r in results if r['status'].startswith('skipped'))
        
        print(f"\n{'='*50}")
        print(f"📊 分析完成")
        print(f"   成功：{success_count} 篇")
        print(f"   跳过：{skipped_count} 篇")
        print(f"   失败：{len(results) - success_count - skipped_count} 篇")
        print(f"{'='*50}")
        
        return results


# ==================== 独立运行入口 ====================

def main():
    """独立运行时的主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='🤖 LLM 文章分析器（独立运行）',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-c', '--config', default='config.yaml',
                       help='配置文件路径 (默认：config.yaml)')
    parser.add_argument('-i', '--input', default='output',
                       help='输入文件夹 (默认：output)')
    parser.add_argument('-o', '--output', default='summary',
                       help='摘要输出文件夹 (默认：summary)')
    parser.add_argument('--no-skip', action='store_true',
                       help='重新处理已分析的文件')
    parser.add_argument('--test', action='store_true',
                       help='测试模式：用简短内容测试 API 连接')
    
    args = parser.parse_args()
    
    # 测试模式
    if args.test:
        print("🧪 测试模式：验证 LLM 连接...")
        try:
            analyzer = LLMAnalyzer(config_path=args.config)
            test_prompt = "请用一句话介绍你自己"
            result = analyzer.analyze(test_prompt)
            if result:
                print(f"✅ 连接成功！\n回复示例：{result[:100]}...")
            else:
                print("❌ 连接失败：返回为空")
        except Exception as e:
            print(f"❌ 连接错误：{e}")
        return
    
    # 正常分析模式
    try:
        print(f"🤖 初始化分析器 (提供商: {args.config})")
        analyzer = LLMAnalyzer(config_path=args.config)
        print(f"✅ 已加载：{analyzer.provider} / {analyzer.model}")
        
        manager = SummaryManager(
            input_dir=args.input,
            summary_dir=args.output
        )
        
        results = manager.process_all(analyzer, skip_existing=not args.no_skip)
        
        # 返回退出码
        success = any(r['status'] == 'success' for r in results)
        exit(0 if success else 1)
        
    except FileNotFoundError as e:
        print(f"❌ 文件错误：{e}")
        print("💡 请确保 config.yaml 存在，或复制 config.yaml.example")
        exit(1)
    except ValueError as e:
        print(f"❌ 配置错误：{e}")
        exit(1)
    except ImportError as e:
        print(f"❌ 依赖缺失：{e}")
        exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        exit(130)
    except Exception as e:
        print(f"❌ 未知错误：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == '__main__':
    main()