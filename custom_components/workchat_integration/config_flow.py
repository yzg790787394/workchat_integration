from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
import re
import urllib.parse

class WorkChatIntegrationFlowHandler(config_entries.ConfigFlow, domain="workchat_integration"):
    """配置流程处理"""
    
    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            # 验证external_url格式
            external_url = user_input.get("external_url", "")
            if not self._is_valid_url(external_url):
                errors["external_url"] = "invalid_url"
            
            # 验证代理URL格式（如果提供）
            proxy_url = user_input.get("proxy", "")
            if proxy_url and not self._is_valid_url(proxy_url):
                errors["proxy"] = "invalid_proxy_url"
            
            if not errors:
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
            # 新增代理URL字段（可选）
            vol.Optional("proxy", default=user_input.get("proxy", "http://您的VPS_IP:3128") if user_input else "http://您的VPS_IP:3128"): str,
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
        """验证URL格式是否有效"""
        if not url:
            return True  # 空URL是允许的（对于代理字段）
        
        # 基本URL格式验证
        url_pattern = re.compile(
            r'^(https?)://'  # http:// 或 https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # 或IP地址
            r'(?::\d+)?'  # 可选的端口
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        return re.match(url_pattern, url) is not None
