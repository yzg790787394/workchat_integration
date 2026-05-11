from __future__ import annotations
import logging
from typing import Any
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .__init__ import WorkChatConfigEntry
from .const import DOMAIN, EVENT_MESSAGE_RECEIVED, EVENT_MEDIA_UPLOADED

_LOGGER = logging.getLogger(__name__)

# 将所有描述统一管理，确保 translation_key 存在，不再使用硬编码的 name
SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    "text": SensorEntityDescription(
        key="text",
        translation_key="text_msg",
        icon="mdi:chat",
    ),
    "image": SensorEntityDescription(
        key="image",
        translation_key="image_msg",
        icon="mdi:image",
    ),
    "location": SensorEntityDescription(
        key="location",
        translation_key="location_msg",
        icon="mdi:map-marker",
    ),
    "menu_click": SensorEntityDescription(
        key="menu_click",
        translation_key="menu_click",
        icon="mdi:menu",
    ),
    "media_upload": SensorEntityDescription(
        key="media_upload",
        translation_key="media_upload",
        icon="mdi:file-upload",
    ),
    "callback_info": SensorEntityDescription(
        key="callback_info",
        translation_key="callback_info",
        icon="mdi:webhook",
    ),
}

async def async_setup_entry(
    hass: HomeAssistant, 
    entry: WorkChatConfigEntry, 
    async_add_entities: AddEntitiesCallback
) -> None:
    """设置企微通传感器。"""
    client = entry.runtime_data
    
    entities = [
        WorkChatMessageSensor(client, entry, SENSOR_TYPES["text"]),
        WorkChatMessageSensor(client, entry, SENSOR_TYPES["image"]),
        WorkChatMessageSensor(client, entry, SENSOR_TYPES["location"]),
        WorkChatMessageSensor(client, entry, SENSOR_TYPES["menu_click"]),
        WorkChatMediaUploadSensor(client, entry, SENSOR_TYPES["media_upload"]),
        WorkChatCallbackInfoSensor(client, entry, SENSOR_TYPES["callback_info"]),
    ]
    async_add_entities(entities)

class WorkChatBaseEntity(SensorEntity):
    """基类：处理设备信息和通用属性。"""
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client, entry):
        self.client = client
        self.entry = entry
        # 统一设备信息，所有实体将聚合在同一个设备下
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"企微通 ({entry.data.get('agent_id')})",
            manufacturer="Tencent",
            model="WorkChat Integration",
        )

class WorkChatMessageSensor(WorkChatBaseEntity):
    """处理文本、图片、位置、菜单点击消息。"""
    def __init__(self, client, entry, description):
        super().__init__(client, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._msg_data: dict[str, Any] = {}

    async def async_added_to_hass(self):
        """注册消息监听。"""
        self.async_on_remove(self.hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, self._handle_msg))

    @callback
    def _handle_msg(self, event):
        """解析并处理事件。"""
        if event.data.get("type") == self.entity_description.key:
            self._msg_data = event.data
            # 处理时间戳显示
            if ts := self._msg_data.get("timestamp"):
                try:
                    self._msg_data["local_time"] = dt_util.as_local(
                        dt_util.utc_from_timestamp(int(ts))
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    self._msg_data["local_time"] = str(ts)
            self.async_write_ha_state()

    @property
    def native_value(self):
        """返回核心状态值。"""
        if not self._msg_data:
            return None
        if self.entity_description.key == "location":
            return self._msg_data.get("label")
        if self.entity_description.key == "menu_click":
            return self._msg_data.get("event_key")
        if self.entity_description.key == "image":
            return self._msg_data.get("media_id")
        return self._msg_data.get("content")

    @property
    def entity_picture(self) -> str | None:
        """如果收到图片消息，在 UI 直接显示。"""
        if self.entity_description.key == "image":
            return self._msg_data.get("pic_url")
        return None

    @property
    def extra_state_attributes(self):
        """设置传感器属性。"""
        if not self._msg_data:
            return {}
        
        attrs = {
            "User": self._msg_data.get("user"),
            "CreateTime": self._msg_data.get("local_time"),
            "AgentID": self._msg_data.get("agent_id")
        }
        
        if self.entity_description.key == "location":
            attrs.update({
                "latitude": self._msg_data.get("lat"),
                "longitude": self._msg_data.get("lon"),
                "address": self._msg_data.get("label"),
            })
        elif self.entity_description.key == "menu_click":
            attrs["EventKey"] = self._msg_data.get("event_key")
            
        return attrs

class WorkChatMediaUploadSensor(WorkChatBaseEntity):
    """显示最后一次上传的 media_id。"""
    def __init__(self, client, entry, description):
        super().__init__(client, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._upload_data: dict[str, Any] = {}

    async def async_added_to_hass(self):
        self.async_on_remove(self.hass.bus.async_listen(EVENT_MEDIA_UPLOADED, self._handle_upload))

    @callback
    def _handle_upload(self, event):
        self._upload_data = event.data
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._upload_data.get("media_id", "idle")

    @property
    def extra_state_attributes(self):
        return self._upload_data

class WorkChatCallbackInfoSensor(WorkChatBaseEntity):
    """提供集成信息查询，辅助后台配置。"""
    def __init__(self, client, entry, description):
        super().__init__(client, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self):
        return "Active"

    @property
    def extra_state_attributes(self):
        return {
            "callback_url": self.client.callback_url,
            "token": self.client.config.get("token"),
            "aes_key": self.client.config.get("aes_key"),
        }
