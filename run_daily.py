"""自动化入口：每天固定时间跑一次日报，并推送到飞书群。

    py run_daily.py --now                        # 立即执行一次
    py run_daily.py --at 09:00                   # 常驻，每天 09:00 执行

推送配置（两种方式任选）：
    1. 环境变量
         set FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
         set FEISHU_SECRET=你复制的签名密钥        # 机器人没开"签名校验"就不用设
    2. 命令行参数 --webhook / --secret

未配置 webhook 时会退化成打印到控制台，不影响本地练习。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from urllib import request

from daily_report import run

WEBHOOK_ENV = "FEISHU_WEBHOOK"
SECRET_ENV = "FEISHU_SECRET"


def build_payload(text: str, secret: str | None = None) -> dict:
    """构造飞书自定义机器人的文本消息体。"""
    payload: dict = {"msg_type": "text", "content": {"text": text}}

    if secret:
        # 官方要求：以 "{timestamp}\n{secret}" 作为密钥做 HMAC-SHA256，再 base64
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        payload["timestamp"] = timestamp
        payload["sign"] = base64.b64encode(digest).decode("utf-8")

    return payload


def push_to_feishu(text: str, webhook: str, secret: str | None = None) -> None:
    body = json.dumps(build_payload(text, secret)).encode("utf-8")
    req = request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    # 返回体里 code 是新的标准字段，StatusCode 是兼容字段
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"飞书返回异常：{result}")
    print(f"已推送到飞书群（{result.get('msg', 'ok')}）")


def notify(text: str, webhook: str | None = None, secret: str | None = None) -> None:
    """推送日报。没配 webhook 就在控制台打印。"""
    if not webhook:
        print("未配置 FEISHU_WEBHOOK，仅打印到控制台：")
        print("\n" + text + "\n")
        return
    push_to_feishu(text, webhook, secret)


def run_once(webhook: str | None, secret: str | None) -> None:
    started = datetime.now()
    try:
        notify(run(), webhook, secret)
        print(f"[{started:%H:%M:%S}] 执行成功，耗时 {(datetime.now() - started).seconds}s")
    except Exception as exc:  # 定时任务不能因为一次失败就整体退出
        print(f"[{started:%H:%M:%S}] 执行失败：{exc}")


def next_run_time(hour: int, minute: int) -> datetime:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="日报定时执行器")
    parser.add_argument("--now", action="store_true", help="立即执行一次后退出")
    parser.add_argument("--at", default="09:00", help="每天执行时间，格式 HH:MM")
    parser.add_argument("--webhook", default=os.getenv(WEBHOOK_ENV), help="飞书机器人 webhook")
    parser.add_argument("--secret", default=os.getenv(SECRET_ENV), help="签名校验密钥")
    args = parser.parse_args()

    if args.now:
        run_once(args.webhook, args.secret)
        return

    if not args.webhook:
        print(f"提示：未设置 {WEBHOOK_ENV}，本次仅输出到控制台。")

    hour, minute = (int(part) for part in args.at.split(":"))
    print(f"已启动，每天 {hour:02d}:{minute:02d} 生成日报（Ctrl+C 退出）")
    while True:
        target = next_run_time(hour, minute)
        print(f"下次执行：{target:%Y-%m-%d %H:%M}")
        time.sleep(max((target - datetime.now()).total_seconds(), 0))
        run_once(args.webhook, args.secret)


if __name__ == "__main__":
    main()