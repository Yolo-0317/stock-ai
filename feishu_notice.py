import json
import time

import requests

# 导入日志配置
from logger_config import get_logger

# 获取 logger（与 monitor 脚本共享同一个 logger）
logger = get_logger("monitor")

# 自己的测试机器人
FEISHU_BOT_URL = (
    "https://open.feishu.cn/open-apis/bot/v2/hook/6ae3c4bc-a50e-49dc-b75d-fa9a217b2299"
)

LARK_MSG_TIMEOUT = 3  # 请求超时时间
NOTIFY_MSG_ENV_PREFIX = "【简单的提醒】"  # 消息前缀


def send_to_lark(
    message: str, is_error: bool = False, max_retries: int = 3, retry_delay: int = 2
) -> bool:
    """
    发送消息到 Lark 机器人，失败时自动重试

    Args:
        message: 要发送的消息内容
        is_error: 是否为报错信息，只有报错信息才会重试
        max_retries: 最大重试次数
        retry_delay: 重试间隔时间（秒）

    Returns:
        bool: 发送成功返回 True，失败返回 False
    """
    logger.debug(f"给 Lark 机器人发送推送")

    # 格式化消息
    formatted_message = f"{NOTIFY_MSG_ENV_PREFIX}\n{message}"

    # 重试机制 - 只有报错信息才重试
    retry_count = max_retries if not is_error else 0

    for attempt in range(retry_count + 1):
        try:
            response = requests.post(
                url=FEISHU_BOT_URL,
                data=json.dumps(
                    {
                        "msg_type": "text",
                        "content": {
                            "text": formatted_message,
                        },
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                },
                proxies={
                    "http": "",
                    "https": "",
                },
                timeout=LARK_MSG_TIMEOUT,
            )

            response_obj = response.json()

            # 检查响应状态
            if response.status_code == 200 and response_obj.get("StatusCode") == 0:
                return True
            else:
                error_message = f"飞书通知发送失败，状态码: {response.text}"
                logger.warning(error_message)
        except Exception as e:
            logger.error(f"飞书通知发送异常: {e}")

        # 如果不是最后一次尝试，等待后重试
        if attempt < retry_count:
            logger.info(f"等待 {retry_delay} 秒后重试，(第{attempt + 1}次尝试)")
            time.sleep(retry_delay)
        else:
            break

    # 所有重试都失败了
    if not is_error:
        # 普通消息重试失败后，发送一条错误消息（只发一次，不重试）
        send_to_lark(f"{message}重试失败", is_error=True)
    else:
        # 发送失败消息失败，不重试
        logger.error(f"【失败消息】飞书通知发送失败，错误消息不重试")
    return False
