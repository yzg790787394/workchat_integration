import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS, CONF_EXTERNAL_URL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # 添加外部URL到配置中
    config_data = dict(entry.data)
    if CONF_EXTERNAL_URL not in config_data:
        # 兼容旧版本：如果配置中没有external_url，使用默认值
        from homeassistant.helpers.network import get_url
        config_data[CONF_EXTERNAL_URL] = get_url(hass, prefer_external=True)
    
    # 延迟导入WorkChatClient以避免循环导入
    from .workchat_client import WorkChatClient
    
    client = WorkChatClient(hass, config_data)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client
    
    # 设置回调URL
    await client.setup_callback()
    
    # 设置实体平台 - 使用推荐的方法
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 设置通知服务和媒体上传服务
    await client.setup_notify_service()
    await client.setup_media_services()
    
    # 保存更新后的配置
    if entry.data != config_data:
        hass.config_entries.async_update_entry(entry, data=config_data)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    await client.remove_callback()
    
    # 卸载所有平台
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
