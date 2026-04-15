#!/usr/bin/env python3
"""
CSV Analyzer Script
用途：自动分析 CSV 文件，生成统计报告和可视化图表
用法：python analyze.py --input <csv_path> --output <output_dir>
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")  # 无头模式，不需要显示器
import seaborn as sns


def load_csv(path: str) -> pd.DataFrame:
    """加载 CSV，自动检测编码"""
    for encoding in ["utf-8", "utf-8-sig", "gbk", "latin1"]:
        try:
            df = pd.read_csv(path, encoding=encoding)
            print(f"✓ 成功读取文件（编码: {encoding}），共 {len(df)} 行 × {len(df.columns)} 列")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法解码文件：{path}")


def generate_report(df: pd.DataFrame, input_path: str) -> str:
    """生成 Markdown 格式的统计报告"""
    lines = []
    filename = Path(input_path).name

    # 标题
    lines += [
        f"# CSV 数据分析报告",
        f"",
        f"**文件**: `{filename}`  ",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**数据规模**: {len(df):,} 行 × {len(df.columns)} 列",
        f"",
    ]

    # 列概览
    lines += ["## 列概览", "", "| 列名 | 类型 | 非空数 | 缺失率 |", "|------|------|--------|--------|"]
    for col in df.columns:
        dtype = str(df[col].dtype)
        non_null = df[col].notna().sum()
        missing_pct = (df[col].isna().sum() / len(df)) * 100
        lines.append(f"| {col} | {dtype} | {non_null:,} | {missing_pct:.1f}% |")
    lines.append("")

    # 数值列统计
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if num_cols:
        lines += ["## 数值列统计", ""]
        stats = df[num_cols].describe().round(3)
        lines.append(stats.to_markdown())
        lines.append("")

    # 字符串列频次 Top 5
    str_cols = df.select_dtypes(include="object").columns.tolist()
    if str_cols:
        lines += ["## 分类列 Top 5 频次", ""]
        for col in str_cols[:5]:  # 最多展示5列
            top = df[col].value_counts().head(5)
            lines += [f"### `{col}`", ""]
            lines += [f"| 值 | 数量 | 占比 |", "|---|------|------|"]
            for val, cnt in top.items():
                pct = cnt / len(df) * 100
                lines.append(f"| {val} | {cnt:,} | {pct:.1f}% |")
            lines.append("")

    # 缺失值汇总
    missing = df.isna().sum()
    missing = missing[missing > 0]
    if len(missing) > 0:
        lines += ["## 缺失值汇总", ""]
        lines += ["| 列名 | 缺失数量 | 缺失率 |", "|------|----------|--------|"]
        for col, cnt in missing.items():
            pct = cnt / len(df) * 100
            lines += [f"| {col} | {cnt:,} | {pct:.1f}% |"]
        lines.append("")
    else:
        lines += ["## 缺失值", "", "✅ 无缺失值", ""]

    return "\n".join(lines)


def generate_charts(df: pd.DataFrame, output_dir: str):
    """生成可视化图表"""
    num_cols = df.select_dtypes(include="number").columns.tolist()[:8]  # 最多8列
    str_cols = df.select_dtypes(include="object").columns.tolist()[:3]  # 最多3列

    has_num = len(num_cols) > 0
    has_str = len(str_cols) > 0

    if not has_num and not has_str:
        print("⚠ 没有可绘制的列，跳过图表生成")
        return

    # 计算子图布局
    n_plots = 0
    if has_num:
        n_plots += len(num_cols)      # 每个数值列一个直方图
        if len(num_cols) > 1:
            n_plots += 1              # 相关性热力图
    if has_str:
        n_plots += len(str_cols)      # 每个字符串列一个条形图

    ncols = 2
    nrows = (n_plots + 1) // 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 4 * nrows))
    axes = axes.flatten() if n_plots > 1 else [axes]

    ax_idx = 0
    sns.set_theme(style="whitegrid", palette="muted")

    # 数值列：直方图
    for col in num_cols:
        ax = axes[ax_idx]
        df[col].dropna().hist(ax=ax, bins=30, color="#4C78A8", edgecolor="white")
        ax.set_title(f"{col} 分布", fontsize=11)
        ax.set_xlabel(col)
        ax.set_ylabel("频次")
        ax_idx += 1

    # 数值列：相关性热力图
    if len(num_cols) > 1:
        ax = axes[ax_idx]
        corr = df[num_cols].corr()
        sns.heatmap(corr, ax=ax, annot=True, fmt=".2f", cmap="coolwarm",
                    center=0, square=True, linewidths=0.5)
        ax.set_title("数值列相关性", fontsize=11)
        ax_idx += 1

    # 字符串列：条形图
    for col in str_cols:
        ax = axes[ax_idx]
        top = df[col].value_counts().head(10)
        top.plot(kind="barh", ax=ax, color="#54A24B")
        ax.set_title(f"{col} Top 10", fontsize=11)
        ax.set_xlabel("数量")
        ax.invert_yaxis()
        ax_idx += 1

    # 隐藏多余的子图
    for i in range(ax_idx, len(axes)):
        axes[i].set_visible(False)

    plt.tight_layout(pad=2.0)
    chart_path = os.path.join(output_dir, "charts.png")
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ 图表已保存：{chart_path}")


def main():
    parser = argparse.ArgumentParser(description="CSV 数据分析工具")
    parser.add_argument("--input", required=True, help="输入 CSV 文件路径")
    parser.add_argument("--output", required=True, help="输出目录")
    args = parser.parse_args()

    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"❌ 文件不存在：{args.input}")
        sys.exit(1)

    # 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 加载数据
    df = load_csv(args.input)

    # 生成报告
    print("📊 正在生成统计报告...")
    report = generate_report(df, args.input)
    report_path = os.path.join(args.output, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✓ 报告已保存：{report_path}")

    # 生成图表
    print("📈 正在生成可视化图表...")
    generate_charts(df, args.output)

    print("\n✅ 分析完成！")


if __name__ == "__main__":
    main()