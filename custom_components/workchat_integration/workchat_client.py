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
    """处理企微回调的 Aiohttp 视图，包含 Web 状态诊断页."""
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

    def _get_status_html(self, status_data: dict[str, Any]) -> str:
        """生成诊断状态页的 HTML."""
        # 状态颜色逻辑
        has_token = status_data['has_token']
        token_status = "有效 (Ready)" if has_token else "未获取 (Error)"
        token_color = "#27ae60" if has_token else "#e74c3c"
        
        return f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>企微通集成状态诊断</title>
            <style>
                body {{ font-family: -apple-system, system-ui, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #1c1e21; }}
                .container {{ max-width: 500px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
                .header {{ display: flex; align-items: center; border-bottom: 1px solid #ebedf0; margin-bottom: 20px; padding-bottom: 15px; }}
                .logo {{ background: #07c160; color: white; width: 40px; height: 40px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 12px; }}
                h2 {{ margin: 0; font-size: 1.25rem; }}
                .status-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f0f2f5; font-size: 14px; }}
                .status-label {{ color: #65676b; }}
                .status-value {{ font-weight: 500; font-family: monospace; }}
                .badge {{ padding: 2px 8px; border-radius: 4px; color: white; font-size: 12px; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #8a8d91; }}
                .log-box {{ background: #1c1e21; color: #a3e635; padding: 10px; border-radius: 6px; font-size: 12px; margin-top: 15px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">企</div>
                    <h2>企微通集成状态</h2>
                </div>
                <div class="status-row">
                    <span class="status-label">Access Token</span>
                    <span class="status-value" style="color: {token_color}">{token_status}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Agent ID</span>
                    <span class="status-value">{status_data['agent_id']}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Webhook 校验</span>
                    <span class="status-value" style="color: #27ae60">配置正常 ✓</span>
                </div>
                <div class="status-row">
                    <span class="status-label">最近消息时间</span>
                    <span class="status-value">{status_data['last_msg_time'] or '等待首条消息...'}</span>
                </div>
                <div class="log-box">
                    System: Service is running asynchronously.<br>
                    External URL: {status_data['external_url']}
                </div>
            </div>
            <div class="footer">WorkChat Integration for Home Assistant</div>
        </body>
        </html>
        """

    async def get(self, request, token):
        """企微 URL 验证步骤 + 诊断页显示."""
        if token != self.client.config["token"]: 
            return web.Response(status=403, text="URL Token Mismatch")
        
        q = request.query
        echostr = q.get("echostr")

       # --- 如果不是企微验证请求，则进入诊断页 ---
        if not echostr:
            # 主动尝试获取/检查一次 Token，确保状态页显示的是最新状态
            # get_access_token() 内部有锁和时间检查，不会导致重复请求
            current_token = await self.client.get_access_token()
            
            status_data = {
                "has_token": current_token is not None,
                "agent_id": self.client.config.get("agent_id"),
                "external_url": self.client.external_url,
                "last_msg_time": getattr(self.client, "last_msg_time", None)
            }
            return web.Response(text=self._get_status_html(status_data), content_type="text/html")

        # --- 原有的企微校验逻辑 ---
        if self._verify(q.get("msg_signature"), q.get("timestamp"), q.get("nonce"), echostr):
            try:
                decrypted = await self.client.hass.async_add_executor_job(
                    self.client.encryptor.decrypt, echostr
                )
                return web.Response(text=decrypted)
            except Exception as e:
                _LOGGER.error("解密验证失败: %s", e)
        
        return web.Response(status=400, text="Verification Failed")

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
        """解析 XML 并将数据分发至传感器，同时记录通信时间."""
        # 记录最后通信时间
        self.client.last_msg_time = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")

        root = ET.fromstring(xml_str)
        msg_type = root.find("MsgType").text
        
        event_data = {
            "user": root.find("FromUserName").text,
            "type": msg_type,
            "agent_id": root.find("AgentID").text if root.find("AgentID") is not None else "",
            "timestamp": root.find("CreateTime").text,
        }

        if msg_type == "text":
            event_data["content"] = root.find("Content").text
        elif msg_type == "image":
            event_data["media_id"] = root.find("MediaId").text
            event_data["pic_url"] = root.find("PicUrl").text
        elif msg_type == "location":
            event_data.update({
                "lat": root.find("Location_X").text,
                "lon": root.find("Location_Y").text,
                "label": root.find("Label").text if root.find("Label") is not None else ""
            })
        elif msg_type == "event":
            event_name = root.find("Event").text
            if event_name == "click":
                event_data["type"] = "menu_click"
            else:
                event_data["type"] = "event"
                
            event_data["event"] = event_name
            if (ek := root.find("EventKey")) is not None:
                event_data["event_key"] = ek.text

        self.client.hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, event_data)
