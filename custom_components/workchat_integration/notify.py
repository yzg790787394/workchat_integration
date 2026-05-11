"""企微通传感器平台实现 - 2026 优化版."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .__init__ import WorkChatConfigEntry
from .const import DOMAIN, EVENT_MESSAGE_RECEIVED, EVENT_MEDIA_UPLOADED

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class WorkChatSensorEntityDescription(SensorEntityDescription):
    """描述企微通消息传感器的扩展类."""
    event_type: str | None = None  # 对应企微回调中的 MsgType 或 Event

# 消息监听传感器定义（核心业务）
MESSAGE_SENSOR_DESCRIPTIONS: tuple[WorkChatSensorEntityDescription, ...] = (
    WorkChatSensorEntityDescription(
        key="text",
        translation_key="text_msg",
        event_type="text",
        icon="mdi:chat-processing-outline",
    ),
    WorkChatSensorEntityDescription(
        key="image",
        translation_key="image_msg",
        event_type="image",
        icon="mdi:image-filter-hdr",
    ),
    WorkChatSensorEntityDescription(
        key="location",
        translation_key="location_msg",
        event_type="location",
        icon="mdi:map-marker-radius",
    ),
    WorkChatSensorEntityDescription(
        key="menu_click",
        translation_key="menu_click",
        event_type="menu_click",
        icon="mdi:cursor-default-click",
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: WorkChatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """根据配置条目设置传感器实体."""
    client = entry.runtime_data
    
    entities: list[SensorEntity] = []
    
    # 1. 消息监听实体
    for description in MESSAGE_SENSOR_DESCRIPTIONS:
        entities.append(WorkChatMessageSensor(client, entry, description))
    
    # 2. 诊断与状态实体
    entities.append(WorkChatCallbackInfoSensor(client, entry))
    entities.append(WorkChatMediaUploadSensor(client, entry))
    
    async_add_entities(entities)

class WorkChatBaseEntity(SensorEntity):
    """企微通实体的共同基类."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client, entry: WorkChatConfigEntry):
        self.client = client
        self.entry = entry
        agent_id = entry.data.get("agent_id", "Unknown")
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"WorkChat App ({agent_id})",
            manufacturer="Tencent",
            model="WorkChat Integration",
            configuration_url=f"https://work.weixin.qq.com/wework_admin/frame#apps/modApiApp/{agent_id}",
        )

class WorkChatMessageSensor(WorkChatBaseEntity):
    """监听并展示企微特定类型消息的传感器."""

    entity_description: WorkChatSensorEntityDescription

    def __init__(self, client, entry, description: WorkChatSensorEntityDescription):
        super().__init__(client, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._msg_data: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """注册事件监听器."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_MESSAGE_RECEIVED, self._handle_message
            )
        )

    @callback
    def _handle_message(self, event):
        """处理自定义消息事件."""
        data = event.data
        if data.get("type") == self.entity_description.event_type:
            self._msg_data = data
            
            # 处理创建时间
            if ts := data.get("timestamp"):
                try:
                    dt_obj = dt_util.utc_from_timestamp(float(ts))
                    self._msg_data["formatted_time"] = dt_util.as_local(dt_obj).isoformat()
                except (ValueError, TypeError):
                    self._msg_data["formatted_time"] = str(ts)
            
            self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """返回传感器的状态值（优化长字符串显示）."""
        if not self._msg_data:
            return None
        
        key = self.entity_description.key
        
        # 优化图片显示：主状态不显示 ID，显示类型文字
        if key == "image":
            return "图片消息" # 或者返回 self._msg_data.get("formatted_time") 只显示时间
            
        if key == "text":
            return self._msg_data.get("content")
            
        if key == "menu_click":
            return self._msg_data.get("event_key")
            
        if key == "location":
            return self._msg_data.get("label") or self._msg_data.get("lat")
        
        # 对于其他可能存在的长 ID 类型（如 file, video），进行截断显示
        val = self._msg_data.get("media_id")
        if val and len(val) > 16:
            return f"{val[:6]}...{val[-6:]}"
        return val

    @property
    def entity_picture(self) -> str | None:
        """核心功能：如果是图片传感器，直接在头像处显示图片预览."""
        if self.entity_description.key == "image":
            return self._msg_data.get("pic_url")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """将完整长 ID 存入属性."""
        if not self._msg_data:
            return {}
        
        attrs = {
            "from_user": self._msg_data.get("user"),
            "receive_time": self._msg_data.get("formatted_time"),
            "agent_id": self._msg_data.get("agent_id"),
        }

        # 针对图片类型，把长 ID 塞进属性里
        if self.entity_description.key == "image":
            attrs["media_id"] = self._msg_data.get("media_id")
            attrs["pic_url"] = self._msg_data.get("pic_url")

        if self.entity_description.key == "location":
            attrs.update({
                "latitude": self._msg_data.get("lat"),
                "longitude": self._msg_data.get("lon"),
                "address": self._msg_data.get("label"),
            })
        
        attrs["raw_info"] = self._msg_data
        return attrs

class WorkChatCallbackInfoSensor(WorkChatBaseEntity):
    """显示 Webhook 配置与 Token 状态的诊断传感器."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client, entry):
        super().__init__(client, entry)
        self.entity_description = SensorEntityDescription(
            key="callback_info",
            translation_key="callback_info",
            icon="mdi:api",
        )
        self._attr_unique_id = f"{entry.entry_id}_callback_info"

    @property
    def native_value(self) -> str:
        return "Connected" if self.client.callback_url else "Disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {
            "webhook_url": self.client.callback_url,
            "corpid": self.client.config.get("corp_id"),
        }
        
        # 安全获取 Token 过期时间
        expire_ts = getattr(self.client, "_token_expire", 0)
        if expire_ts > 0:
            attrs["token_expires_at"] = dt_util.as_local(
                dt_util.utc_from_timestamp(expire_ts)
            ).isoformat()
            
        return attrs

class WorkChatMediaUploadSensor(WorkChatBaseEntity):
    """显示最近一次媒体上传 ID 的诊断传感器."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client, entry):
        super().__init__(client, entry)
        self.entity_description = SensorEntityDescription(
            key="last_media_upload",
            translation_key="media_upload",
            icon="mdi:cloud-upload-outline",
        )
        self._attr_unique_id = f"{entry.entry_id}_media_upload"
        self._upload_data: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_MEDIA_UPLOADED, self._handle_upload
            )
        )

    @callback
    def _handle_upload(self, event):
        self._upload_data = event.data
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """主状态显示上传状态和时间."""
        if not self._upload_data.get("media_id"):
            return "等待上传"
        return "已就绪"  # 或者返回 dt_util.now().strftime("%H:%M:%S")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """在属性中保留原始、完整的 media_id."""
        attrs = {
            "file_path": self._upload_data.get("file_path"),
            "media_type": self._upload_data.get("type"),
            "upload_time": self._upload_data.get("upload_time"),
            # 完整 ID 存放在这里，方便自动化提取和用户手动复制
            "media_id": self._upload_data.get("media_id"), 
        }
        return attrs
