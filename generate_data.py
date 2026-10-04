"""生成模拟的月度销售 Excel，用来练习批量读取与数据清洗。

故意混入真实工作里常见的脏数据：
门店名带空格、日期格式不统一、数量是文本、缺失值、重复行、退货负数量。
"""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
MONTHS = ["2026-07", "2026-08", "2026-09"]
STORES = ["上海店", "北京店", "广州店", "成都店"]
PRODUCTS = ["无线耳机", "机械键盘", "显示器", "鼠标", "摄像头"]
ROWS_PER_MONTH = 200


def build_month(month: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = ROWS_PER_MONTH
    year, mon = (int(part) for part in month.split("-"))

    qty = rng.integers(1, 6, n)
    df = pd.DataFrame(
        {
            "订单日期": [date(year, mon, int(d)) for d in rng.integers(1, 29, n)],
            "门店": rng.choice(STORES, n),
            "商品": rng.choice(PRODUCTS, n, p=[0.35, 0.2, 0.15, 0.2, 0.1]),
            "数量": qty,
            "单价": np.round(rng.normal(300, 120, n).clip(19, 1500), 2),
        }
    )

    # 各自独立抽样，避免同一行被叠加多种脏数据后难以核对
    idx_return = rng.choice(n, 8, replace=False)
    idx_text = rng.choice(n, 15, replace=False)
    idx_nan_price = rng.choice(n, 12, replace=False)
    idx_nan_qty = rng.choice(n, 10, replace=False)
    idx_space = rng.choice(n, 25, replace=False)
    idx_date_str = rng.choice(n, 20, replace=False)
    idx_dup = rng.choice(n, 6, replace=False)

    # 退货：负数量
    df.loc[idx_return, "数量"] = -df.loc[idx_return, "数量"]
    # 数量被录成文本
    df["数量"] = df["数量"].astype(object)
    df.loc[idx_text, "数量"] = df.loc[idx_text, "数量"].astype(str)
    # 缺失值
    df.loc[idx_nan_qty, "数量"] = np.nan
    df.loc[idx_nan_price, "单价"] = np.nan
    # 文本列前后空格 / 内部空格
    df.loc[idx_space, "门店"] = " " + df.loc[idx_space, "门店"].astype(str) + "  "
    df.loc[idx_space[:10], "商品"] = " " + df.loc[idx_space[:10], "商品"].astype(str) + " "
    # 日期格式不统一
    df["订单日期"] = df["订单日期"].astype(object)
    df.loc[idx_date_str, "订单日期"] = df.loc[idx_date_str, "订单日期"].map(
        lambda d: f"{d.year}/{d.month}/{d.day}"
    )

    # 重复录入 + 打乱顺序 + 末尾空行
    df = pd.concat([df, df.loc[idx_dup]], ignore_index=True)
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for i, month in enumerate(MONTHS):
        path = DATA_DIR / f"销售明细_{month}.xlsx"
        build_month(month, seed=100 + i).to_excel(path, index=False)
        print(f"已生成 {path.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()