"""企微通集成的配置流程 - 支持可选代理校验."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_CORP_ID,
    CONF_SECRET,
    CONF_AGENT_ID,
    CONF_TOKEN,
    CONF_AES_KEY,
    CONF_RECEIVE_USER,
    CONF_EXTERNAL_URL,
    CONF_PROXY,
    API_BASE,
)

_LOGGER = logging.getLogger(__name__)

class WorkChatIntegrationFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """处理企微通集成的配置流程."""

    VERSION = 1

    async def _test_credentials(self, user_input: dict[str, Any]) -> str | None:
        """测试连接（包含可选代理测试）."""
        session = async_get_clientsession(self.hass)
        
        # 处理可选代理：如果是空字符串或全是空格，则设为 None
        proxy = user_input.get(CONF_PROXY, "").strip() or None
        
        url = f"{API_BASE}/gettoken"
        params = {
            "corpid": user_input[CONF_CORP_ID],
            "corpsecret": user_input[CONF_SECRET]
        }
        
        try:
            # 在测试时就应用用户填写的代理，确保代理本身是通的
            async with session.get(url, params=params, proxy=proxy, timeout=10) as resp:
                data = await resp.json()
                if data.get("errcode") != 0:
                    _LOGGER.error("企微认证错误: %s", data.get("errmsg"))
                    return "invalid_auth"
        except Exception as err:
            _LOGGER.error("连接企微失败 (代理: %s): %s", proxy, err)
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """用户初始配置."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # 1. 代理 URL 格式预校验（仅在用户填写了内容时校验）
            proxy = user_input.get(CONF_PROXY, "").strip()
            if proxy and not proxy.startswith(("http://", "https://")):
                errors[CONF_PROXY] = "invalid_proxy_format"
            
            if not errors:
                # 2. 唯一性校验
                await self.async_set_unique_id(f"{user_input[CONF_CORP_ID]}_{user_input[CONF_AGENT_ID]}")
                self._abort_if_unique_id_configured()

                # 3. 认证测试
                error = await self._test_credentials(user_input)
                if error:
                    errors["base"] = error
                else:
                    # 4. 数据清理并创建
                    user_input[CONF_EXTERNAL_URL] = user_input[CONF_EXTERNAL_URL].rstrip("/") + "/"
                    user_input[CONF_PROXY] = proxy or "" # 存入空字符串而不是 None
                    
                    return self.async_create_entry(
                        title=f"企微应用 {user_input[CONF_AGENT_ID]}",
                        data=user_input
                    )

        default_url = self.hass.config.external_url or self.hass.config.internal_url or ""

        data_schema = vol.Schema({
            vol.Required(CONF_CORP_ID): str,
            vol.Required(CONF_SECRET): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_AGENT_ID): str,
            vol.Required(CONF_TOKEN): str,
            vol.Required(CONF_AES_KEY): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_RECEIVE_USER, default="@all"): str,
            vol.Required(CONF_EXTERNAL_URL, default=default_url): str,
            vol.Optional(CONF_PROXY, default=""): str, # 设置默认值为空字符串
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> WorkChatOptionsFlowHandler:
        return WorkChatOptionsFlowHandler()

class WorkChatOptionsFlowHandler(config_entries.OptionsFlow):
    """处理集成选项修改."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """管理选项菜单."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            proxy = user_input.get(CONF_PROXY, "").strip()
            if proxy and not proxy.startswith(("http://", "https://")):
                errors[CONF_PROXY] = "invalid_proxy_format"
            
            if not errors:
                new_data = {**self.config_entry.data, **user_input}
                # 更新并保存，触发集成重载
                self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_RECEIVE_USER,
                    default=self.config_entry.data.get(CONF_RECEIVE_USER, "@all"),
                ): str,
                vol.Optional(
                    CONF_PROXY,
                    default=self.config_entry.data.get(CONF_PROXY, ""),
                ): str,
            }),
            errors=errors,
        )
