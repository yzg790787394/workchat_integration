from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
)

_LOGGER = logging.getLogger(__name__)

class WorkChatIntegrationFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """处理企微通集成的配置流程."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """用户发起配置步骤."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # 格式化 URL
            user_input[CONF_EXTERNAL_URL] = user_input[CONF_EXTERNAL_URL].rstrip("/") + "/"
            
            return self.async_create_entry(
                title=f"企微应用 {user_input[CONF_AGENT_ID]}",
                data=user_input
            )

        # 默认外部 URL 逻辑
        default_url = self.hass.config.external_url or self.hass.config.internal_url or ""

        # 使用 Selector 提供更好的 UI 体验
        data_schema = vol.Schema({
            vol.Required(CONF_CORP_ID, default=""): str,
            vol.Required(CONF_SECRET, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_AGENT_ID, default=""): str,
            vol.Required(CONF_TOKEN, default=""): str,
            vol.Required(CONF_AES_KEY, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_RECEIVE_USER, default="@all"): str,
            vol.Required(CONF_EXTERNAL_URL, default=default_url): str,
            vol.Optional(CONF_PROXY, default=""): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WorkChatOptionsFlowHandler:
        """
        获取选项流处理器。
        注意：最新 HA 不再需要在初始化时传递 config_entry。
        """
        return WorkChatOptionsFlowHandler()


class WorkChatOptionsFlowHandler(config_entries.OptionsFlow):
    """处理集成选项修改."""

    # 关键修复：删除自定义的 __init__ 方法。
    # HA 2024+ 会通过 self.config_entry 自动提供数据。

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """管理选项菜单."""
        if user_input is not None:
            # 更新配置条目数据并保存
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            # 选项流必须返回一个空的 entry 或在 async_update_entry 后完成
            return self.async_create_entry(title="", data={})

        # 获取当前配置值
        current_receive_user = self.config_entry.data.get(CONF_RECEIVE_USER, "@all")
        current_proxy = self.config_entry.data.get(CONF_PROXY, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_RECEIVE_USER,
                    default=current_receive_user,
                ): str,
                vol.Optional(
                    CONF_PROXY,
                    default=current_proxy,
                ): str,
            }),
        )
