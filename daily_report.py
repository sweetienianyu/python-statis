"""批量读取 data/ 下的月度销售 Excel，清洗后生成一份汇总日报。

用法：
    py daily_report.py                       # 处理 data/ 下所有 Excel
    py daily_report.py --data-dir data --out-dir output
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
DATE_COL, STORE_COL, PRODUCT_COL = "订单日期", "门店", "商品"
QTY_COL, PRICE_COL, AMOUNT_COL = "数量", "单价", "金额"


def read_all(data_dir: Path) -> pd.DataFrame:
    """把目录下所有 xlsx 读成一张长表，并记录来源文件。"""
    files = sorted(data_dir.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(f"{data_dir} 下没有 xlsx，请先运行 generate_data.py")

    frames = []
    for file in files:
        one = pd.read_excel(file)
        one["来源文件"] = file.name
        frames.append(one)
    return pd.concat(frames, ignore_index=True)


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """清洗并返回 (干净数据, 各步骤丢弃行数统计)。"""
    df = raw.copy()
    total = len(df)

    # 1) 文本列去空格（含中间空格、全角空格），统一门店/商品写法
    for col in (STORE_COL, PRODUCT_COL):
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].str.replace(r"\s+", "", regex=True)

    # 2) 日期统一，兼容 "2026/8/3" 这类字符串
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")

    # 3) 数量/单价转数值，非法文本变 NaN
    df[QTY_COL] = pd.to_numeric(df[QTY_COL], errors="coerce")
    df[PRICE_COL] = pd.to_numeric(df[PRICE_COL], errors="coerce")

    # 4) 关键字段缺失的行无法修复，直接丢弃
    df = df.dropna(subset=[DATE_COL, QTY_COL, PRICE_COL])
    df = df[df[QTY_COL] != 0]
    after_valid = len(df)

    # 5) 同一日期+门店+商品+数量+单价视为重复录入
    df = df.drop_duplicates(subset=[DATE_COL, STORE_COL, PRODUCT_COL, QTY_COL, PRICE_COL])

    # 6) 计算金额（负数量是退货，金额自然为负）并补上月份
    df[AMOUNT_COL] = (df[QTY_COL] * df[PRICE_COL]).round(2)
    df["月份"] = df[DATE_COL].dt.to_period("M").astype(str)

    stats = {
        "原始行数": total,
        "有效行数": len(df),
        "丢弃-缺失或非法": total - after_valid,
        "丢弃-重复": after_valid - len(df),
    }
    return df.sort_values(DATE_COL).reset_index(drop=True), stats


def summarize(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """产出多张汇总表，对应日报的多个 sheet。"""
    by_month = (
        df.groupby("月份")
        .agg(订单数=(QTY_COL, "count"), 销量=(QTY_COL, "sum"), 销售额=(AMOUNT_COL, "sum"))
        .round(2)
        .reset_index()
    )

    by_store = (
        df.groupby(STORE_COL)
        .agg(订单数=(QTY_COL, "count"), 销售额=(AMOUNT_COL, "sum"), 客单价=(AMOUNT_COL, "mean"))
        .round(2)
        .sort_values("销售额", ascending=False)
        .reset_index()
    )

    # 商品排行只看正向销售，避免退货把排名搅乱
    top_product = (
        df[df[QTY_COL] > 0]
        .groupby(PRODUCT_COL)
        .agg(销量=(QTY_COL, "sum"), 销售额=(AMOUNT_COL, "sum"))
        .round(2)
        .sort_values("销售额", ascending=False)
        .reset_index()
    )

    store_month_pivot = (
        df.pivot_table(index=STORE_COL, columns="月份", values=AMOUNT_COL, aggfunc="sum")
        .round(2)
        .reset_index()
    )

    return {
        "明细": df,
        "月度汇总": by_month,
        "门店汇总": by_store,
        "商品排行": top_product,
        "门店月度透视": store_month_pivot,
    }


def build_text_report(sheets: dict[str, pd.DataFrame], stats: dict[str, int]) -> str:
    """生成纯文本日报，方便直接推送到群里。"""
    by_month = sheets["月度汇总"]
    by_store = sheets["门店汇总"]
    top_product = sheets["商品排行"]

    lines = [
        f"销售日报 | 生成时间 {datetime.now():%Y-%m-%d %H:%M}",
        f"清洗：原始 {stats['原始行数']} 行 → 有效 {stats['有效行数']} 行"
        f"（缺失/非法 {stats['丢弃-缺失或非法']}，重复 {stats['丢弃-重复']}）",
        "",
        "月度趋势：",
    ]
    for row in by_month.itertuples(index=False):
        lines.append(f"  {row.月份}  销售额 {row.销售额:>10,.2f}  销量 {row.销量:>5}")

    lines += ["", "门店排名："]
    for rank, row in enumerate(by_store.itertuples(index=False), start=1):
        lines.append(f"  {rank}. {row.门店}  销售额 {row.销售额:>10,.2f}  客单价 {row.客单价:>8,.2f}")

    lines += ["", "商品 Top3："]
    for rank, row in enumerate(top_product.head(3).itertuples(index=False), start=1):
        lines.append(f"  {rank}. {row.商品}  销售额 {row.销售额:>10,.2f}  销量 {row.销量:>5}")

    return "\n".join(lines)


def write_excel(sheets: dict[str, pd.DataFrame], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"销售日报_{datetime.now():%Y%m%d}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


def run(data_dir: Path = BASE_DIR / "data", out_dir: Path = BASE_DIR / "output") -> str:
    """完整跑一次日报，返回文本内容。"""
    dirty = read_all(data_dir)
    clean_df, stats = clean(dirty)
    sheets = summarize(clean_df)
    path = write_excel(sheets, out_dir)
    report = build_text_report(sheets, stats)
    return f"{report}\n\n明细已写入 {path.relative_to(BASE_DIR)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="批量处理销售 Excel 并生成日报")
    parser.add_argument("--data-dir", type=Path, default=BASE_DIR / "data")
    parser.add_argument("--out-dir", type=Path, default=BASE_DIR / "output")
    args = parser.parse_args()
    print(run(args.data_dir, args.out_dir))


if __name__ == "__main__":
    main()