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
            # 验证external_url格式
            external_url = user_input.get("external_url", "")
            if not self._is_valid_url(external_url):
                errors["external_url"] = "invalid_url"
            else:
                # 确保URL以斜杠结尾
                if not external_url.endswith('/'):
                    user_input["external_url"] = external_url + '/'
                return self.async_create_entry(
                    title="企微通集成",
                    data=user_input
                )
        
        # 使用异步方式获取外部URL
        external_url = self.hass.config.external_url or self.hass.config.internal_url
        # 确保在表单中显示时以斜杠结尾
        if external_url and not external_url.endswith('/'):
            external_url += '/'
        
        # 构建数据模式
        data_schema = vol.Schema({
            vol.Required("corp_id", default=user_input.get("corp_id", "") if user_input else ""): str,
            vol.Required("secret", default=user_input.get("secret", "") if user_input else ""): str,
            vol.Required("agent_id", default=user_input.get("agent_id", "") if user_input else ""): str,
            vol.Required("token", default=user_input.get("token", "") if user_input else ""): str,
            vol.Required("aes_key", default=user_input.get("aes_key", "") if user_input else ""): str,
            vol.Required("receive_user", default=user_input.get("receive_user", "@all") if user_input else "@all"): str,
            vol.Required("external_url", default=user_input.get("external_url", external_url) if user_input else external_url): str,
        })
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
    
    def _is_valid_url(self, url):
        """验证URL格式是否有效"""
        if not url:
            return False
        # 基本URL格式验证
        return re.match(r'^(http|https)://', url) is not None
