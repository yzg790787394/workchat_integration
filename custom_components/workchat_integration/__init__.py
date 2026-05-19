import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.network import get_url
from homeassistant.const import Platform

from .const import DOMAIN, PLATFORMS, CONF_EXTERNAL_URL
from .workchat_client import WorkChatClient

_LOGGER = logging.getLogger(__name__)

# 定义类型别名
type WorkChatConfigEntry = ConfigEntry[WorkChatClient]

async def async_setup_entry(hass: HomeAssistant, entry: WorkChatConfigEntry) -> bool:
    """设置集成入口."""
    
    # 获取外部URL逻辑
    external_url = entry.data.get(CONF_EXTERNAL_URL) or get_url(hass, prefer_external=True)
    
    # 初始化客户端
    client = WorkChatClient(hass, entry, external_url)
    entry.runtime_data = client
    
    # 设置回调视图逻辑
    await client.setup_callback()
    
    # --- 注册自定义动作 (Services) ---

    async def handle_notify(call: ServiceCall):
        """处理 workchat_integration.notify 动作.
        此服务将保留原代码中的所有功能，并支持 services.yaml 中定义的所有字段。
        """
        # 直接透传 call.data。WorkChatClient.send_message 已优化为支持所有字段。
        await client.send_message(**call.data)

    async def handle_upload_media(call: ServiceCall):
        """处理 workchat_integration.upload_media 动作."""
        media_id = await client.upload_media_file(
            media_type=call.data["type"],
            file_path=call.data["file_path"],
            file_name=call.data.get("file_name")
        )
        return {"media_id": media_id}

    # 注册原始的 notify 动作
    hass.services.async_register(
        DOMAIN, 
        "notify", 
        handle_notify
    )

    # 注册媒体上传动作 (支持服务响应)
    hass.services.async_register(
        DOMAIN, 
        "upload_media", 
        handle_upload_media, 
        supports_response=SupportsResponse.ONLY
    )
    
    # --- 启动平台 (传感器等) ---
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: WorkChatConfigEntry) -> bool:
    """卸载集成入口."""
    # 卸载所有平台
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # 清理已注册的服务
        hass.services.async_remove(DOMAIN, "notify")
        hass.services.async_remove(DOMAIN, "upload_media")
        
        # 调用客户端清理逻辑
        await entry.runtime_data.remove_callback()
        
    return unload_ok
