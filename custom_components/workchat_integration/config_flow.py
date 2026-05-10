from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
import re

class WorkChatIntegrationFlowHandler(config_entries.ConfigFlow, domain="workchat_integration"):
    """配置流程处理"""

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is not None:
            # 验证 external_url
            external_url = user_input.get("external_url", "")
            if not self._is_valid_url(external_url):
                errors["external_url"] = "invalid_url"

            # 验证 proxy（可选）
            proxy_url = user_input.get("proxy", "")
            if not self._is_valid_url(proxy_url):
                errors["proxy"] = "invalid_proxy_url"

            if not errors:
                # external_url 统一以 / 结尾
                if not external_url.endswith('/'):
                    user_input["external_url"] = external_url + '/'

                return self.async_create_entry(
                    title="企微通集成",
                    data=user_input
                )

        # 默认 external_url
        external_url = self.hass.config.external_url or self.hass.config.internal_url
        if external_url and not external_url.endswith('/'):
            external_url += '/'

        # 构建 schema
        data_schema = vol.Schema({
            vol.Required("corp_id", default=user_input.get("corp_id", "") if user_input else ""): str,
            vol.Required("secret", default=user_input.get("secret", "") if user_input else ""): str,
            vol.Required("agent_id", default=user_input.get("agent_id", "") if user_input else ""): str,
            vol.Required("token", default=user_input.get("token", "") if user_input else ""): str,
            vol.Required("aes_key", default=user_input.get("aes_key", "") if user_input else ""): str,
            vol.Required("receive_user", default=user_input.get("receive_user", "@all") if user_input else "@all"): str,
            vol.Required("external_url", default=user_input.get("external_url", external_url) if user_input else external_url): str,

            # 代理字段真正可选，默认空字符串
            vol.Optional("proxy", default=user_input.get("proxy", "") if user_input else ""): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "proxy_help": "可选，用于通过代理服务器连接企业微信API。例如：http://您的VPS_IP:3128"
            }
        )

    def _is_valid_url(self, url):
        """验证URL格式是否有效（允许空值）"""
        if not url or not str(url).strip():
            return True  # 空值、空白字符串都合法（用于可选 proxy）

        url = url.strip()

        url_pattern = re.compile(
            r'^(https?)://'  # http:// 或 https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # 端口
            r'(?:/?|[/?]\S+)$',
            re.IGNORECASE
        )
        return re.match(url_pattern, url) is not None
