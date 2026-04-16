---
name: csv-analyzer
description: Analyze CSV files and generate statistical reports with charts. Use this skill whenever the user uploads or mentions a CSV file and wants insights, statistics, summaries, visualizations, or data analysis. Trigger for phrases like "分析这个表格", "这个CSV里面数据", "看看这个表格数据趋势", "分析一下", or any time tabular data needs to be explored or summarized.
---

# CSV Analyzer Skill

用 Python 脚本对 CSV 文件做自动化数据分析，生成统计报告和可视化图表。

## 工作流程

1. 找到用户提供的 CSV 文件路径（通常在 `/mnt/user-data/uploads/`）
2. 运行分析脚本
3. 将结果报告和图表输出到 `/mnt/user-data/outputs/`
4. 用 `present_files` 工具展示给用户

## 运行分析

```bash
python /home/claude/csv-analyzer/scripts/analyze.py \
  --input <CSV文件路径> \
  --output /mnt/user-data/outputs/
```

脚本会自动生成：
- `report.md` — 统计摘要报告（行数、列类型、缺失值、数值统计）
- `charts.png` — 数据分布图（数值列直方图 + 相关性热力图）

## 注意事项

- 如果列超过 20 个，只分析前 20 列
- 字符串列自动做频次统计（Top 10）
- 日期列自动识别并按时间排序分析
- 如果用户有特定分析需求（比如"只看某几列"、"按某列分组"），在运行脚本后用 pandas 补充处理

## 依赖

```
pandas, matplotlib, seaborn — 标准数据科学库，一般已预装
```

如果缺少依赖：
```bash
pip install pandas matplotlib seaborn --break-system-packages -q
```
