"""企微通通知平台实现 (适配最新通知实体规范)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_TITLE,
    NotifyEntity,
    NotifyEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import WorkChatConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: WorkChatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置企微通通知实体入口."""
    # 从 runtime_data 获取 client
    client = entry.runtime_data
    
    # 添加通知实体
    async_add_entities([WorkChatNotifyEntity(client, entry)])

class WorkChatNotifyEntity(NotifyEntity):
    """企微通通知实体类."""

    _attr_has_entity_name = True
    _attr_name = None  # 实体名称将继承自设备名称
    
    # 声明支持的特性（通知实体必须声明）
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, client, entry) -> None:
        """初始化."""
        self.client = client
        self.entry = entry
        
        # 唯一 ID
        self._attr_unique_id = f"{entry.entry_id}_notify"
        
        # 设备信息聚合
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"企微通 ({entry.data.get('agent_id')})",
            manufacturer="Tencent",
            model="WorkChat Integration",
        )

    async def async_send_message(self, message: str, title: str | None = None, **kwargs: Any) -> None:
        """发送通知消息."""
        # 合并字段，确保支持 services.yaml 中定义的 data 参数
        data = kwargs.get(ATTR_DATA) or {}
        
        params = {
            "message": message,
            "title": title,
            **data  # 透传 msg_type, media_id, url, touser 等
        }
        
        _LOGGER.debug("正在通过通知实体发送企微消息: %s", params)
        
        # 调用 client 中的发送逻辑
        await self.client.send_message(**params)
