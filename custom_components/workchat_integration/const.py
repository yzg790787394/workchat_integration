"""企微通集成的常量定义."""
from typing import Final
from homeassistant.const import Platform

# 集成域
DOMAIN: Final = "workchat_integration"

# 支持的平台
# 注意：在最新版本 HA 中，notify 被视为一个平台
PLATFORMS: Final = [
    Platform.NOTIFY,
    Platform.SENSOR,
]

# 配置键名
CONF_CORP_ID: Final = "corp_id"
CONF_SECRET: Final = "secret"
CONF_AGENT_ID: Final = "agent_id"
CONF_TOKEN: Final = "token"
CONF_AES_KEY: Final = "aes_key"
CONF_RECEIVE_USER: Final = "receive_user"
CONF_EXTERNAL_URL: Final = "external_url"
CONF_PROXY: Final = "proxy"

# 企业微信 API 基础 URL
API_BASE: Final = "https://qyapi.weixin.qq.com/cgi-bin"

# 默认值
DEFAULT_RECEIVE_USER: Final = "@all"

# 事件名称
EVENT_MESSAGE_RECEIVED: Final = f"{DOMAIN}_message"
EVENT_MEDIA_UPLOADED: Final = f"{DOMAIN}_media_uploaded"
