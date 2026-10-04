# python-statis — 销售日报自动化

一个用来练习 pandas 数据处理的小项目：**批量读取多个月的销售 Excel → 清洗脏数据 → 分组汇总 → 生成日报并推送到飞书群**。

数据是脚本模拟生成的，所以不需要联网、不需要准备任何原始文件，克隆下来就能跑通完整流程。

## 它能做什么

```
data/*.xlsx  ──►  daily_report.py  ──►  output/销售日报_YYYYMMDD.xlsx（5 个 sheet）
（多个月报表明细）   （批量读取 + 清洗 + 汇总）      └──►  文本日报  ──►  飞书群机器人
                                          run_daily.py 负责定时触发和推送
```

## 目录结构

| 路径 | 说明 |
|---|---|
| `generate_data.py` | 生成 3 个月的模拟销售 Excel（含脏数据），写入 `data/` |
| `daily_report.py` | 核心逻辑：读取 → 清洗 → 汇总 → 写出 Excel + 生成文本日报 |
| `run_daily.py` | 自动化入口：定时执行 + 推送到飞书 |
| `requirements.txt` | 依赖清单 |
| `data/` | 生成的原始数据（已 gitignore，可随时重新生成） |
| `output/` | 生成的报表产物（已 gitignore） |

## 环境准备

需要 Python 3.10+（用到 `X | None` 类型写法）。安装依赖：

```powershell
py -m pip install -r requirements.txt
```

依赖只有三个：`pandas`、`openpyxl`（读写 Excel）、`numpy`（生成模拟数据）。

## 快速开始

```powershell
py generate_data.py          # 1. 造数据 → data/ 下出现 3 个 xlsx
py daily_report.py           # 2. 出报表 → output/销售日报_YYYYMMDD.xlsx
py run_daily.py --now        # 3. 走自动化入口跑一次（不配 webhook 时打印到控制台）
py run_daily.py --at 09:00   # 4. 常驻，每天 09:00 自动执行
```

`daily_report.py` 也支持指定目录：

```powershell
py daily_report.py --data-dir data --out-dir output
```

## 数据里有什么"脏"东西

`generate_data.py` 故意注入了真实工作中最常见的几类问题：

| 类型 | 表现 |
|---|---|
| 门店名不干净 | 前后空格、中间夹空格，如 `" 上海店  "` |
| 日期格式不统一 | 一部分是日期对象，一部分是 `"2026/8/3"` 字符串 |
| 类型错误 | 数量被录成文本 `"3"` |
| 缺失值 | 单价或数量为空 |
| 退货 | 数量为负数 |
| 重复录入 | 同一日期 + 门店 + 商品 + 数量 + 单价出现两次 |

以默认参数生成 3 个月，原始 618 行，清洗后保留 538 行。

## 清洗规则

`daily_report.py` 的 `clean()` 按顺序做了 6 件事：

1. 文本列 `strip()` 去空格，并用正则把中间空格也去掉（统一门店/商品写法）
2. `pd.to_datetime(..., errors="coerce")` 统一日期，兼容两种格式
3. `pd.to_numeric(..., errors="coerce")` 把数量和单价转成数值，非法文本变 `NaN`
4. 丢弃关键字段缺失的行，以及数量为 0 的行
5. 按「日期 + 门店 + 商品 + 数量 + 单价」`drop_duplicates()` 去重
6. 计算金额（负数量是退货，金额自然为负），并从日期派生 `月份` 列

每一步丢弃了多少行，都会在日报里打印出来，方便核对。

## 输出说明

`output/销售日报_YYYYMMDD.xlsx` 包含 5 个 sheet：

| Sheet | 内容 |
|---|---|
| `明细` | 清洗后的完整明细，含金额、月份、来源文件 |
| `月度汇总` | 每月的订单数、销量、销售额 |
| `门店汇总` | 各门店销售额、订单数、客单价，按销售额降序 |
| `商品排行` | 只看正向销售的商品销量与销售额排名 |
| `门店月度透视` | `pivot_table` 产出的「门店 × 月份」销售额矩阵 |

同时生成一段纯文本日报（月度趋势、门店排名、商品 Top3），这就是推送到飞书的内容。

## 推送日报到飞书

### 1. 在群里添加自定义机器人

群 → 设置 → 群机器人 → 添加机器人 → **自定义机器人**，复制形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx` 的 webhook 地址。

### 2. 配置安全设置（二选一）

- **签名校验**：勾选后复制密钥，代码会自动计算 `sign`。
- **自定义关键词**：填 `销售日报` 即可——日报正文第一行就是这个关键词。

### 3. 设置环境变量并运行

```powershell
$env:FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/你的token"
$env:FEISHU_SECRET  = "你的签名密钥"    # 没开签名校验就不要设置
py run_daily.py --now
```

想永久保存用 `setx FEISHU_WEBHOOK "..."`，新开终端后生效。也可以临时用参数传入：

```powershell
py run_daily.py --now --webhook "https://..." --secret "..."
```

**没有配置 webhook 时，日报会退化成打印到控制台**，不影响本地练习和调试。

### 两个官方限制

- 请求体不能超过 **20KB**，超了返回 `9499 Bad Request`
- 限流 **100 次/分钟、5 次/秒**，官方建议避开 10:00、17:30 这类整点/半点，否则可能撞上 `11232`

## 安全提醒

Webhook 地址等同于密码，泄露后别人可以往你群里发消息。代码从**环境变量**读取，不会写进文件；`.gitignore` 已排除 `.env`、`data/`、`output/`。

## 可以继续练习的方向

1. 让 `read_all()` 同时支持 `.csv` 和 `.xlsx`
2. 在 `summarize()` 里加环比增长率（`pct_change`）和退货率
3. 把 `notify()` 换成飞书**消息卡片**，或在文本里 `@` 指定人
4. 换成自己的数据：改字段名，在 `clean()` 里补几条针对自己业务的规则