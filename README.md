# Note Generator

一个 Claude Code skill，将课程的语音转文字稿、课件、现有笔记等材料，生成结构化的 Markdown 格式笔记。

## 适用场景

- 课堂录音转文字后，自动整理为书面笔记
- 课件 PPT/PDF 内容提取并结构化
- 多份材料合并去重，形成完整笔记
- 期末复习、开卷考试速查笔记生成

## 支持的课程类型

| 类型 | 说明 |
|------|------|
| 编程类（C/C++、Java、Python 等） | 五大模块结构：核心定义 → 语法示例 → 代码演示 → 规则总结 → 易错点 |
| 非编程类（数学、物理、经济等） | 开卷考试速查模式：关键词索引、公式表、例题导向、易错点 |

## 工作流程

1. 收集材料类型（语音稿/课件/现有笔记/其他）
2. 选择语言模式（纯中文/中文+术语对照/纯英文）
3. 提供文件路径或粘贴内容
4. 选择课程类型，自动加载对应生成规则
5. 输出 Markdown 笔记

## 文件结构

```
note-generator/
├── SKILL.md                          # Skill 核心交互逻辑
├── references/
│   ├── programming.md                # 编程类课程笔记生成规则
│   └── non_programming.md            # 非编程类课程笔记生成规则
└── README.md
```

## 安装

将本仓库克隆到你的 Claude Code skills 目录：

```bash
git clone https://github.com/KayeAdams515/note-generator.git ~/.claude/skills/note-generator
```
