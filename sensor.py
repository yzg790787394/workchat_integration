import os
import logging
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.util import dt as dt_util
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# 实体描述定义 - 添加回调URL和媒体上传实体
ENTITY_DESCRIPTIONS = {
    "text": SensorEntityDescription(
        key="text",
        name="企微通文本消息",
        icon="mdi:chat",
    ),
    "image": SensorEntityDescription(
        key="image",
        name="企微通图片消息",
        icon="mdi:image",
    ),
    "location": SensorEntityDescription(
        key="location",
        name="企微通位置消息",
        icon="mdi:map-marker",
    ),
    "callback_info": SensorEntityDescription(
        key="callback_info",
        name="企微通回调URL",
        icon="mdi:webhook",
    ),
    "media_upload": SensorEntityDescription(
        key="media_upload",
        name="企微通上传媒体文件信息",
        icon="mdi:file-upload",
    ),
}

class WeComBaseEntity(SensorEntity):
    """企微通消息实体基类"""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, client, entry, msg_type):
        self._client = client
        self._entry = entry
        
        # 使用预定义的实体描述
        self.entity_description = ENTITY_DESCRIPTIONS[msg_type]
        
        # 设置唯一ID
        self._attr_unique_id = f"{entry.entry_id}-{msg_type}"
        
        self.msg_data = {}
        self.last_updated = dt_util.utcnow()
        
        # 监听消息事件
        self._entry.async_on_unload(
            self._client.hass.bus.async_listen(
                "workchat_message", self._handle_message
            )
        )
    
    def _handle_message(self, event):
        """处理消息事件"""
        if event.data["type"] == self.entity_description.key:
            self.msg_data = event.data
            self.last_updated = dt_util.utcnow()
            self.schedule_update_ha_state()
    
    @property
    def extra_state_attributes(self):
        """返回消息详细信息"""
        # 将时间戳转换为可读的日期时间格式
        timestamp_val = self.msg_data.get("timestamp")
        formatted_time = None
        if timestamp_val:
            try:
                # 将Unix时间戳转换为本地时间
                dt_obj = dt_util.utc_from_timestamp(timestamp_val)
                formatted_time = dt_util.as_local(dt_obj).strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                _LOGGER.error("时间格式转换失败: %s", str(e))
                formatted_time = str(timestamp_val)
        else:
            formatted_time = "未知"
            
        return {
            "user": self.msg_data.get("user"),
            "timestamp": formatted_time,  # 使用格式化后的时间
            "agent_id": self.msg_data.get("agent_id"),
            **self._get_type_specific_attrs()
        }
    
    @property
    def native_value(self):
        """返回主要值"""
        return self._get_primary_value()
    
    def _get_type_specific_attrs(self):
        """由子类实现特定消息类型的属性"""
        return {}
    
    def _get_primary_value(self):
        """由子类实现主要显示值"""
        return ""

class WorkChatTextSensor(WeComBaseEntity):
    """企微通文本消息实体"""
    
    def __init__(self, client, entry):
        super().__init__(client, entry, "text")
    
    def _get_primary_value(self):
        return self.msg_data.get("content", "")
    
    def _get_type_specific_attrs(self):
        return {
            "content": self.msg_data.get("content", "")
        }

class WorkChatImageSensor(WeComBaseEntity):
    """企微通图片消息实体"""
    
    def __init__(self, client, entry):
        super().__init__(client, entry, "image")
    
    def _get_primary_value(self):
        return self.msg_data.get("media_id", "")
    
    def _get_type_specific_attrs(self):
        return {
            "pic_url": self.msg_data.get("pic_url", ""),
            "media_id": self.msg_data.get("media_id", "")
        }

class WorkChatLocationSensor(WeComBaseEntity):
    """企微通位置消息实体"""
    
    def __init__(self, client, entry):
        super().__init__(client, entry, "location")
    
    def _get_primary_value(self):
        return self.msg_data.get("label", "")
    
    def _get_type_specific_attrs(self):
        # 直接使用原始字符串值确保精度
        lat = self.msg_data.get("lat")
        lon = self.msg_data.get("lon")
        
        # 添加后缀确保显示时不被截断
        return {
            "latitude": f"{lat}°" if lat is not None else None,
            "longitude": f"{lon}°" if lon is not None else None,
            "scale": self.msg_data.get("scale"),
            "label": self.msg_data.get("label")
        }

class WorkChatCallbackInfoSensor(SensorEntity):
    """企微通回调URL信息实体"""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self.entity_description = ENTITY_DESCRIPTIONS["callback_info"]
        self._attr_unique_id = f"{entry.entry_id}-callback_info"
        self._state = "已配置"
        self.last_updated = dt_util.utcnow()
    
    @property
    def native_value(self):
        return self._state
    
    @property
    def extra_state_attributes(self):
        """返回回调URL配置信息"""
        return {
            "回调URL": self._client.callback_url,
            "Token": self._client.config["token"],
            "EncodingAESKey": self._client.config["aes_key"]
        }

class WorkChatMediaUploadSensor(SensorEntity):
    """企微通上传媒体文件信息实体"""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self.entity_description = ENTITY_DESCRIPTIONS["media_upload"]
        self._attr_unique_id = f"{entry.entry_id}-media_upload"
        self._state = "等待上传"
        self.upload_data = {}
        self.last_updated = dt_util.utcnow()
        
        # 监听媒体上传事件
        self._entry.async_on_unload(
            self._client.hass.bus.async_listen(
                "workchat_media_uploaded", self._handle_media_upload
            )
        )
    
    def _handle_media_upload(self, event):
        """处理媒体上传事件"""
        self.upload_data = event.data
        self._state = "已上传"
        self.last_updated = dt_util.utcnow()
        self.schedule_update_ha_state()
    
    @property
    def native_value(self):
        return self._state
    
    @property
    def extra_state_attributes(self):
        """返回媒体上传信息"""
        return {
            "文件名": self.upload_data.get("file_name", ""),
            "文件类型": self.upload_data.get("type", ""),
            "上传时间": self.upload_data.get("time", ""),
            "文件路径": self.upload_data.get("file_path", ""),
            "media_id": self.upload_data.get("media_id", "")
        }

async def async_setup_entry(hass, entry, async_add_entities):
    """设置所有企微通消息实体"""
    client = hass.data[DOMAIN][entry.entry_id]
    entities = [
        WorkChatTextSensor(client, entry),
        WorkChatImageSensor(client, entry),
        WorkChatLocationSensor(client, entry),
        WorkChatCallbackInfoSensor(client, entry),
        WorkChatMediaUploadSensor(client, entry)
    ]
    async_add_entities(entities)
