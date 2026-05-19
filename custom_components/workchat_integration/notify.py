"""企微通通知实体实现 (适配最新规范)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_DATA,
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
    client = entry.runtime_data
    
    # 实体化通知平台不再需要 async_load_platform
    async_add_entities([WorkChatNotifyEntity(client, entry)])

class WorkChatNotifyEntity(NotifyEntity):
    """企微通通知实体类."""

    _attr_has_entity_name = True
    # 建议设置 translation_key，配合 zh-Hans.json 可以翻译为“通知器”
    _attr_translation_key = "workchat_notifier"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, client, entry) -> None:
        """初始化."""
        self.client = client
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notify"
        
        agent_id = entry.data.get("agent_id")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"WorkChat App ({agent_id})",
            manufacturer="Tencent",
            model="WorkChat Integration",
            configuration_url=f"https://work.weixin.qq.com/wework_admin/frame#apps/modApiApp/{agent_id}",
        )

    async def async_send_message(self, message: str, title: str | None = None, **kwargs: Any) -> None:
        """发送通知消息."""
        # 合并字段
        data = kwargs.get(ATTR_DATA) or {}
        
        # 构造发送参数
        params = {
            "message": message,
            "title": title,
            **data
        }
        
        try:
            success = await self.client.send_message(**params)
            if not success:
                _LOGGER.error("企微消息发送失败，请检查 client 日志")
        except Exception as err:
            _LOGGER.exception("通过通知实体发送消息时发生崩溃: %s", err)
