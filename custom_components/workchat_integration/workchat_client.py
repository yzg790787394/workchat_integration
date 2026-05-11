"""企微通 API 客户端实现"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any

from aiohttp import web, FormData
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, 
    API_BASE, 
    EVENT_MESSAGE_RECEIVED, 
    EVENT_MEDIA_UPLOADED,
    CONF_PROXY
)

_LOGGER = logging.getLogger(__name__)

class WorkChatClient:
    """企业微信异步客户端."""

    def __init__(self, hass: HomeAssistant, entry, external_url: str) -> None:
        """初始化客户端."""
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.external_url = external_url
        self.session = async_get_clientsession(hass)
        
        self._access_token: str | None = None
        self._token_expire: float = 0
        self._token_lock = asyncio.Lock()

        # 初始化加密助手，使用 corp_id 进行校验
        from .encrypt_helper import EncryptHelper
        self.encryptor = EncryptHelper(
            self.config["aes_key"],
            self.config["corp_id"]
        )

        self.proxy = self.config.get(CONF_PROXY, "").strip() or None
        # 构造完整回调 URL
        self.callback_url = f"{external_url.rstrip('/')}/api/workchat_callback/{self.config['token']}"

    async def get_access_token(self) -> str | None:
        """异步获取 Access Token (带并发锁)."""
        async with self._token_lock:
            if self._access_token and time.time() < self._token_expire - 300:
                return self._access_token

            url = f"{API_BASE}/gettoken"
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
                _LOGGER.error("获取 Token 网络异常: %s", err)
            return None

    async def send_message(self, **kwargs: Any) -> bool:
        """发送各种类型的消息."""
        token = await self.get_access_token()
        if not token:
            return False

        msg_type = kwargs.get("msg_type", "text")
        payload: dict[str, Any] = {
            "touser": kwargs.get("touser", self.config.get("receive_user", "@all")),
            "agentid": self.config["agent_id"],
            "msgtype": msg_type,
            "safe": kwargs.get("safe", 0)
        }

        # 构造不同消息体
        if msg_type in ["text", "markdown"]:
            payload[msg_type] = {"content": kwargs.get("message")}
        elif msg_type == "textcard":
            payload["textcard"] = {
                "title": kwargs.get("title"),
                "description": kwargs.get("message"),
                "url": kwargs.get("url"),
                "btntxt": kwargs.get("btntxt", "详情")
            }
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

        try:
            url = f"{API_BASE}/message/send?access_token={token}"
            async with self.session.post(url, json=payload, proxy=self.proxy, timeout=10) as resp:
                res_data = await resp.json()
                return res_data.get("errcode") == 0
        except Exception as err:
            _LOGGER.error("消息发送失败: %s", err)
            return False

    async def upload_media_file(self, media_type: str, file_path: str, file_name: str | None = None) -> str | None:
        """上传媒体文件到企微."""
        token = await self.get_access_token()
        if not token:
            return None

        # 路径纠错处理
        clean_path = file_path.strip()
        if not clean_path.startswith("/"):
            if clean_path.startswith("config/"):
                clean_path = "/" + clean_path
            else:
                clean_path = "/config/" + clean_path

        def _get_data():
            if not os.path.exists(clean_path):
                return None
            with open(clean_path, "rb") as f:
                return f.read()

        file_content = await self.hass.async_add_executor_job(_get_data)
        if not file_content:
            _LOGGER.error("上传失败: 文件路径不存在 %s", clean_path)
            return None

        url = f"{API_BASE}/media/upload?access_token={token}&type={media_type}"
        data = FormData()
        data.add_field('media', file_content, filename=file_name or os.path.basename(clean_path))

        try:
            async with self.session.post(url, data=data, proxy=self.proxy, timeout=30) as resp:
                res = await resp.json()
                if res.get("errcode") == 0:
                    media_id = str(res.get("media_id"))
                    # 触发上传成功事件，供传感器捕获
                    self.hass.bus.async_fire(EVENT_MEDIA_UPLOADED, {
                        "media_id": media_id,
                        "file_path": clean_path,
                        "type": media_type,
                        "time": dt_util.now().isoformat()
                    })
                    return media_id
                _LOGGER.error("企微上传接口报错: %s", res.get("errmsg"))
        except Exception as err:
            _LOGGER.error("上传网络异常: %s", err)
        return None

    async def setup_callback(self):
        """注册回调视图."""
        self.hass.http.register_view(WorkChatCallbackView(self))

    async def remove_callback(self):
        """卸载回调入口，防止卸载时报错."""
        _LOGGER.debug("WorkChat 回调已卸载")

class WorkChatCallbackView(HomeAssistantView):
    """处理企微回调的 HTTP 视图."""
    url = "/api/workchat_callback/{token}"
    name = "api:workchat_callback"
    requires_auth = False

    def __init__(self, client: WorkChatClient) -> None:
        self.client = client

    def _verify_signature(self, sig, ts, nonce, text):
        """企业微信签名验证算法."""
        tmp = sorted([self.client.config["token"], ts, nonce, text])
        calc_sig = hashlib.sha1("".join(tmp).encode()).hexdigest()
        return calc_sig == sig

    async def get(self, request, token):
        """处理企业微信 URL 验证 (GET)."""
        if token != self.client.config["token"]:
            return web.Response(status=403)
        
        q = request.query
        echostr = q.get("echostr", "")
        try:
            # 验证签名
            is_valid = await self.client.hass.async_add_executor_job(
                self._verify_signature, q.get("msg_signature"), q.get("timestamp"), q.get("nonce"), echostr
            )
            if is_valid:
                # 解密验证内容
                decrypted = await self.client.hass.async_add_executor_job(
                    self.client.encryptor.decrypt, echostr
                )
                # 必须返回原始字符串，不能带引号
                return web.Response(text=decrypted)
        except Exception as err:
            _LOGGER.error("回调验证 GET 出错: %s", err)
        return web.Response(status=400)

    async def post(self, request, token):
        """处理企业微信消息推送 (POST)."""
        if token != self.client.config["token"]:
            return web.Response(status=403)

        try:
            body = await request.text()
            root = ET.fromstring(body)
            encrypt_msg = root.find('Encrypt').text
            
            # 校验 POST 签名
            q = request.query
            is_valid = await self.client.hass.async_add_executor_job(
                self._verify_signature, q.get("msg_signature"), q.get("timestamp"), q.get("nonce"), encrypt_msg
            )
            if not is_valid:
                return web.Response(status=401)

            # 解密消息 XML
            decrypted_xml = await self.client.hass.async_add_executor_job(
                self.client.encryptor.decrypt, encrypt_msg
            )
            
            # 解析并分发事件
            await self._process_xml(decrypted_xml)
            return web.Response(text="success")
        except Exception as err:
            _LOGGER.error("处理回调消息 POST 出错: %s", err)
            return web.Response(status=500)

    async def _process_xml(self, xml_str):
        """解析解密后的 XML 并通过事件总线分发."""
        msg_root = ET.fromstring(xml_str)
        msg_type = msg_root.find("MsgType").text
        
        event_data = {
            "user": msg_root.find("FromUserName").text,
            "type": msg_type,
            "timestamp": msg_root.find("CreateTime").text,
            "agent_id": msg_root.find("AgentID").text,
        }
        
        if msg_type == "text":
            event_data["content"] = msg_root.find("Content").text
        elif msg_type == "image":
            event_data["media_id"] = msg_root.find("MediaId").text
            # 企微节点名为 PicUrl (大小写敏感)
            pic_node = msg_root.find("PicUrl")
            event_data["pic_url"] = pic_node.text if pic_node is not None else ""
        elif msg_type == "location":
            event_data.update({
                "lat": msg_root.find("Location_X").text,
                "lon": msg_root.find("Location_Y").text,
                "label": msg_root.find("Label").text,
                "scale": msg_root.find("Scale").text if msg_root.find("Scale") is not None else "15"
            })
        elif msg_type == "event":
            event_data["event"] = msg_root.find("Event").text
            if (k := msg_root.find("EventKey")) is not None:
                event_data["event_key"] = k.text
                # 菜单点击识别
                if event_data["event"] == "click":
                    event_data["type"] = "menu_click"

        # 触发事件，传感器会监听这个 EVENT_MESSAGE_RECEIVED
        self.client.hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, event_data)
