"""企微通 (WorkChat) API 客户端实现."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any

from aiohttp import web, FormData
from yarl import URL

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, 
    API_BASE, 
    EVENT_MESSAGE_RECEIVED, 
    EVENT_MEDIA_UPLOADED
)

_LOGGER = logging.getLogger(__name__)

class WorkChatClient:
    """企业微信异步客户端."""

    def __init__(self, hass: HomeAssistant, entry, external_url: str) -> None:
        """初始化客户端."""
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.external_url = external_url.rstrip("/")
        
        self.session = async_get_clientsession(hass)
        
        self._access_token: str | None = None
        self._token_expire: float = 0
        self._token_lock = asyncio.Lock()

        from .encrypt_helper import EncryptHelper
        self.encryptor = EncryptHelper(
            self.config["aes_key"],
            self.config["token"]
        )

        self.proxy = self.config.get("proxy", "").strip() or None
        self.base_url = URL(API_BASE)
        
        self.callback_url = f"{self.external_url}/api/workchat_callback/{self.config['token']}"

    async def get_access_token(self, force_refresh: bool = False) -> str | None:
        """获取有效的 Access Token (带并发锁)."""
        async with self._token_lock:
            if not force_refresh and self._access_token and time.time() < self._token_expire - 300:
                return self._access_token

            url = self.base_url / "gettoken"
            params = {
                "corpid": self.config["corp_id"],
                "corpsecret": self.config["secret"]
            }

            try:
                async with self.session.get(url, params=params, proxy=self.proxy, timeout=10) as resp:
                    data = await resp.json()
                    if data.get("errcode") == 0:
                        self._access_token = data["access_token"]
                        self._token_expire = time.time() + data["expires_in"]
                        return self._access_token
                    _LOGGER.error("企微 API 获取 Token 失败: %s", data.get("errmsg"))
            except Exception as err:
                _LOGGER.error("获取 Token 网络异常: %s (代理: %s)", err, self.proxy)
            return None

    async def send_message(self, **kwargs: Any) -> bool:
        """发送消息 (支持 2026 推荐的消息格式)."""
        token = await self.get_access_token()
        if not token:
            return False

        msg_type = kwargs.get("msg_type", "text")
        payload: dict[str, Any] = {
            "touser": kwargs.get("touser", self.config.get("receive_user", "@all")),
            "agentid": self.config["agent_id"],
            "msgtype": msg_type,
            "safe": kwargs.get("safe", 0),
            "enable_id_trans": 0,
            "enable_duplicate_check": 0
        }

        # 构建 Payload 逻辑
        if msg_type in ["text", "markdown"]:
            payload[msg_type] = {"content": kwargs.get("message")}
        elif msg_type == "textcard":
            payload["textcard"] = {
                "title": kwargs.get("title"),
                "description": kwargs.get("message"),
                "url": kwargs.get("url", ""),
                "btntxt": kwargs.get("btntxt", "详情")
            }
        elif msg_type == "template_card":  # 新增：模版卡片支持
            payload["template_card"] = kwargs.get("template_card_data")
        elif msg_type == "news":
            articles = kwargs.get("articles") or [{
                "title": kwargs.get("title"),
                "description": kwargs.get("message"),
                "url": kwargs.get("url"),
                "picurl": kwargs.get("picurl")
            }]
            payload["news"] = {"articles": articles}
        elif msg_type in ["image", "file", "voice"]:
            payload[msg_type] = {"media_id": kwargs.get("media_id")}
        elif msg_type == "video":
            payload["video"] = {
                "media_id": kwargs.get("media_id"),
                "title": kwargs.get("title"),
                "description": kwargs.get("message")
            }

        url = (self.base_url / "message/send").with_query(access_token=token)
        try:
            async with self.session.post(url, json=payload, proxy=self.proxy, timeout=10) as resp:
                res_data = await resp.json()
                if res_data.get("errcode") == 40014:
                    await self.get_access_token(force_refresh=True)
                    return await self.send_message(**kwargs)
                return res_data.get("errcode") == 0
        except Exception as err:
            _LOGGER.error("发送消息异常: %s", err)
        return False

    async def upload_media_file(self, media_type: str, file_path: str, file_name: str | None = None) -> str | None:
        """上传媒体文件并触发 HA 事件."""
        token = await self.get_access_token()
        if not token: return None

        def _get_file_content():
            if not os.path.exists(file_path): return None
            with open(file_path, "rb") as f: return f.read()

        file_content = await self.hass.async_add_executor_job(_get_file_content)
        if not file_content: return None

        url = (self.base_url / "media/upload").with_query(access_token=token, type=media_type)
        data = FormData()
        data.add_field('media', file_content, filename=file_name or os.path.basename(file_path))

        try:
            async with self.session.post(url, data=data, proxy=self.proxy, timeout=30) as resp:
                res_data = await resp.json()
                if res_data.get("errcode") == 0:
                    media_id = str(res_data.get("media_id"))
                    self.hass.bus.async_fire(EVENT_MEDIA_UPLOADED, {
                        "media_id": media_id, "file_path": file_path, "type": media_type
                    })
                    return media_id
        except Exception as err:
            _LOGGER.error("上传异常: %s", err)
        return None

    async def setup_callback(self):
        """注册 Webhook 视图."""
        self.hass.http.register_view(WorkChatCallbackView(self))

    async def remove_callback(self):
        """清理逻辑."""
        _LOGGER.debug("清理企微回调视图")

    def generate_passive_response(self, content: str) -> str:
        """生成加密的被动回复 XML."""
        timestamp = str(int(time.time()))
        nonce = str(int(time.time()) % 1000000)
        encrypt = self.encryptor.encrypt(content)
        
        tmp_list = sorted([self.config["token"], timestamp, nonce, encrypt])
        signature = hashlib.sha1("".join(tmp_list).encode()).hexdigest()
        
        return f"""<xml>
            <Encrypt><![CDATA[{encrypt}]]></Encrypt>
            <MsgSignature><![CDATA[{signature}]]></MsgSignature>
            <TimeStamp>{timestamp}</TimeStamp>
            <Nonce><![CDATA[{nonce}]]></Nonce>
        </xml>"""

class WorkChatCallbackView(HomeAssistantView):
    """处理企微回调的 Aiohttp 视图."""
    url = "/api/workchat_callback/{token}"
    name = "api:workchat_callback"
    requires_auth = False

    def __init__(self, client: WorkChatClient) -> None:
        self.client = client

    def _verify(self, sig, ts, nonce, data):
        """签名校验逻辑."""
        try:
            tmp = sorted([self.client.config["token"], ts, nonce, data])
            return hashlib.sha1("".join(tmp).encode()).hexdigest() == sig
        except: return False

    async def get(self, request, token):
        """企微 URL 验证步骤."""
        if token != self.client.config["token"]: return web.Response(status=403)
        q = request.query
        if self._verify(q.get("msg_signature"), q.get("timestamp"), q.get("nonce"), q.get("echostr", "")):
            try:
                decrypted = await self.client.hass.async_add_executor_job(
                    self.client.encryptor.decrypt, q.get("echostr")
                )
                return web.Response(text=decrypted)
            except: pass
        return web.Response(status=400)

    async def post(self, request, token):
        """接收加密消息并解析."""
        if token != self.client.config["token"]: return web.Response(status=403)
        try:
            body = await request.text()
            root = ET.fromstring(body)
            encrypt_msg = root.find('Encrypt').text
            
            q = request.query
            if not self._verify(q.get("msg_signature"), q.get("timestamp"), q.get("nonce"), encrypt_msg):
                return web.Response(status=401)

            decrypted_xml = await self.client.hass.async_add_executor_job(
                self.client.encryptor.decrypt, encrypt_msg
            )
            
            await self._process_xml(decrypted_xml)
            return web.Response(text="success")
        except Exception as err:
            _LOGGER.error("回调处理失败: %s", err)
            return web.Response(status=500)

    async def _process_xml(self, xml_str):
        """解析 XML 并将数据分发至传感器."""
        root = ET.fromstring(xml_str)
        msg_type = root.find("MsgType").text
        
        event_data = {
            "user": root.find("FromUserName").text,
            "type": msg_type, # 默认类型
            "agent_id": root.find("AgentID").text if root.find("AgentID") is not None else "",
            "timestamp": root.find("CreateTime").text,
        }

        # 详细逻辑解析
        if msg_type == "text":
            event_data["content"] = root.find("Content").text
        elif msg_type == "image":
            event_data["media_id"] = root.find("MediaId").text
            event_data["pic_url"] = root.find("PicUrl").text # 供传感器 entity_picture 使用
        elif msg_type == "location":
            event_data.update({
                "lat": root.find("Location_X").text,
                "lon": root.find("Location_Y").text,
                "label": root.find("Label").text if root.find("Label") is not None else ""
            })
        elif msg_type == "event":
            # --- 关键修复：将菜单点击事件映射为传感器识别的 menu_click ---
            event_name = root.find("Event").text
            if event_name == "click":
                event_data["type"] = "menu_click"
            else:
                event_data["type"] = "event"
                
            event_data["event"] = event_name
            if (ek := root.find("EventKey")) is not None:
                event_data["event_key"] = ek.text

        # 触发事件总线，传感器会自动捕获
        self.client.hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, event_data)
