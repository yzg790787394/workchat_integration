import os
import logging
import requests
import hashlib
import time
import xml.etree.ElementTree as ET
from homeassistant.util import dt as dt_util
from homeassistant.components.http import HomeAssistantView
from aiohttp import web
from .const import DOMAIN, API_BASE, CONF_EXTERNAL_URL
from .encrypt_helper import EncryptHelper

_LOGGER = logging.getLogger(__name__)

class WorkChatCallbackView(HomeAssistantView):
    """处理企微通回调的视图"""
    
    url = "/api/workchat_callback/{token}"
    name = "api:workchat_callback"
    requires_auth = False
    
    def __init__(self, client):
        self.client = client
    
    def _calculate_signature(self, token, timestamp, nonce, encrypt):
        token = str(token)
        timestamp = str(timestamp)
        nonce = str(nonce)
        encrypt = str(encrypt)
        
        params = sorted([token, timestamp, nonce, encrypt])
        sign_str = ''.join(params)
        return hashlib.sha1(sign_str.encode()).hexdigest()
    
    async def get(self, request, token):
        required = ["echostr", "msg_signature", "timestamp", "nonce"]
        if any(p not in request.query for p in required):
            _LOGGER.error("缺少必要参数: %s", request.query)
            return web.Response(text="Missing parameters", status=400)
        
        data = request.query
        echostr = data["echostr"]
        signature = data["msg_signature"]
        timestamp = data["timestamp"]
        nonce = data["nonce"]
        
        _LOGGER.debug("验证回调请求 - Token: %s, 时间戳: %s, 随机数: %s, 加密字符串: %s, 签名: %s", 
                     token, timestamp, nonce, echostr, signature)
        
        if token != self.client.config["token"]:
            _LOGGER.error("Token不匹配! URL中的Token: %s, 配置Token: %s", 
                         token, self.client.config["token"])
            return web.Response(text="Token不匹配", status=400)
        
        calc_sign = self._calculate_signature(
            self.client.config["token"], timestamp, nonce, echostr
        )
        _LOGGER.debug("计算签名: %s", calc_sign)
        
        if calc_sign != signature:
            _LOGGER.warning("签名验证失败! 收到签名: %s, 计算签名: %s", signature, calc_sign)
            return web.Response(text="签名验证失败", status=400)
        
        try:
            decrypted = self.client.encryptor.Decrypt(echostr)
            _LOGGER.debug("验证成功, 解密内容: %s", decrypted)
            return web.Response(text=decrypted)
        except Exception as e:
            _LOGGER.error("解密失败: %s", str(e))
            return web.Response(text=f"解密失败: {str(e)}", status=400)
    
    async def post(self, request, token):
        _LOGGER.debug("收到回调消息 - Token: %s, 方法: POST", token)
        
        try:
            data = await request.text()
            root = ET.fromstring(data)
            encrypt = root.find('Encrypt').text
            
            response = await self.client.handle_callback({
                "msg_signature": request.query.get("msg_signature", ""),
                "timestamp": request.query.get("timestamp", ""),
                "nonce": request.query.get("nonce", ""),
                "encrypt": encrypt
            })
            
            if isinstance(response, tuple):
                return web.Response(text=response[0], status=response[1])
            return web.Response(text=response, content_type="application/xml")
        except Exception as e:
            _LOGGER.exception("处理回调时发生异常: %s", str(e))
            return web.Response(text=f"服务器错误: {str(e)}", status=500)

class WorkChatClient:
    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self.access_token = None
        self.token_expire = 0
        self.encryptor = EncryptHelper(
            config["aes_key"],
            config["token"]
        )
        self.callback_url = None  # 初始化回调URL属性
    
    async def get_access_token(self):
        """获取或刷新Access Token"""
        if self.access_token and time.time() < self.token_expire - 60:
            return self.access_token
            
        url = f"{API_BASE}/gettoken?corpid={self.config['corp_id']}&corpsecret={self.config['secret']}"
        response = await self.hass.async_add_executor_job(requests.get, url)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("errcode") == 0:
                self.access_token = data["access_token"]
                self.token_expire = time.time() + data["expires_in"]
                return self.access_token
        
        _LOGGER.error("获取Access Token失败: %s", response.text)
        return None
    
    async def setup_callback(self):
        """注册回调URL"""
        # 使用配置中的external_url
        external_url = self.config[CONF_EXTERNAL_URL]
        if not external_url.endswith('/'):
            external_url += '/'
        
        callback_url = f"{external_url}api/workchat_callback/{self.config['token']}"
        self.callback_url = callback_url  # 存储回调URL
        
        _LOGGER.debug("生成的回调URL: %s", callback_url)
        _LOGGER.debug("配置参数 - Token: %s, AES Key: %s", 
                     self.config["token"], self.config["aes_key"])
        
        _LOGGER.info("请在企微通后台设置回调URL: %s", callback_url)
        
        self.hass.http.register_view(WorkChatCallbackView(self))
    
    async def remove_callback(self):
        """清理回调"""
        pass
    
    async def setup_notify_service(self):
        """注册通知服务"""
        async def workchat_notify(call):
            await self.send_message(
                **call.data
            )
            
        self.hass.services.async_register(
            DOMAIN, "notify", workchat_notify
        )
    
    async def setup_media_services(self):
        """注册媒体上传服务"""
        async def upload_media(call):
            media_type = call.data.get("type", "file")
            file_path = call.data.get("file_path")
            file_name = call.data.get("file_name")
            
            try:
                media_id = await self.upload_media_file(
                    media_type, 
                    file_path,
                    file_name
                )
                return {"media_id": media_id}
            except Exception as e:
                _LOGGER.error("上传媒体文件失败: %s", str(e))
                return {"error": str(e)}
        
        self.hass.services.async_register(
            DOMAIN, "upload_media", upload_media
        )
    
    async def upload_media_file(self, media_type, file_path, file_name=None):
        """上传媒体文件到企微通"""
        access_token = await self.get_access_token()
        if not access_token:
            raise Exception("无法获取Access Token")
        
        url = f"{API_BASE}/media/upload?access_token={access_token}&type={media_type}"
        
        def _perform_upload():
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            file_size = os.path.getsize(file_path)
            max_size = 10 * 1024 * 1024  # 10MB
            if file_size > max_size:
                raise ValueError(f"文件过大 ({file_size/(1024*1024):.2f}MB)，最大支持10MB")
            
            filename = file_name or os.path.basename(file_path)
            
            with open(file_path, "rb") as file:
                files = {"media": (filename, file)}
                response = requests.post(url, files=files)
                return response, filename
        
        try:
            result = await self.hass.async_add_executor_job(_perform_upload)
            response, filename = result
        except Exception as e:
            _LOGGER.error("文件上传请求失败: %s", str(e))
            raise
        
        if response.status_code != 200:
            error_msg = f"上传失败，状态码: {response.status_code}"
            _LOGGER.error(error_msg)
            raise Exception(error_msg)
        
        data = response.json()
        if data.get("errcode") != 0:
            error_msg = data.get("errmsg", "未知错误")
            _LOGGER.error("企微通错误: %s", error_msg)
            raise Exception(f"企微通错误: {error_msg}")
        
        media_id = data.get("media_id")
        if not media_id:
            _LOGGER.error("未返回有效的media_id")
            raise Exception("未返回有效的media_id")
        
        _LOGGER.debug("媒体文件上传成功，media_id: %s", media_id)
        
        # 触发媒体上传事件
        self.hass.bus.async_fire("workchat_media_uploaded", {
            "file_path": file_path,
            "file_name": filename,
            "type": media_type,
            "media_id": media_id,
            "time": dt_util.utcnow().isoformat()
        })
        
        return media_id
    
    async def send_message(self, **kwargs):
        """发送消息到企微通"""
        access_token = await self.get_access_token()
        if not access_token: 
            _LOGGER.error("无法获取有效的Access Token")
            return False
            
        msg_type = kwargs.get("msg_type", "text")
        payload = {
            "touser": kwargs.get("touser", self.config["receive_user"]),
            "agentid": self.config["agent_id"],
            "msgtype": msg_type
        }
        
        if msg_type == "text":
            payload["text"] = {"content": kwargs["message"]}
            
        elif msg_type == "image":
            payload["image"] = {"media_id": kwargs["media_id"]}
            
        elif msg_type == "video":
            payload["video"] = {
                "media_id": kwargs["media_id"],
                "title": kwargs.get("title", ""),
                "description": kwargs.get("description", "")
            }
            
        elif msg_type == "file":
            payload["file"] = {"media_id": kwargs["media_id"]}
            
        elif msg_type == "textcard":
            payload["textcard"] = {
                "title": kwargs["title"],
                "description": kwargs["message"],
                "url": kwargs["url"],
                "btnttxt": kwargs.get("btnttxt", "详情")
            }
            
        elif msg_type == "news":
            articles = kwargs.get("articles", [])
            if not articles and kwargs.get("title"):
                articles = [{
                    "title": kwargs["title"],
                    "description": kwargs.get("description", kwargs.get("message", "")),
                    "url": kwargs.get("url", ""),
                    "picurl": kwargs.get("picurl", "")
                }]
            payload["news"] = {"articles": articles}
        
        _LOGGER.debug("准备发送消息到企微通，类型: %s", msg_type)
        _LOGGER.debug("消息负载: %s", payload)
        
        def _send_request():
            try:
                url = f"{API_BASE}/message/send?access_token={access_token}"
                response = requests.post(url, json=payload, timeout=10)
                return response
            except requests.exceptions.Timeout:
                _LOGGER.error("请求超时")
                raise
            except requests.exceptions.RequestException as e:
                _LOGGER.error("请求异常: %s", str(e))
                raise
        
        try:
            response = await self.hass.async_add_executor_job(_send_request)
        except Exception as e:
            _LOGGER.error("发送消息时发生异常: %s", str(e))
            return False
        
        if response.status_code != 200:
            error_msg = f"发送消息失败，HTTP状态码: {response.status_code}"
            _LOGGER.error(error_msg)
            return False
        
        try:
            response_data = response.json()
        except ValueError:
            _LOGGER.error("无法解析响应JSON: %s", response.text)
            return False
        
        if response_data.get("errcode") == 0:
            _LOGGER.info("消息发送成功")
            return True
            
        error_msg = f"发送消息失败: {response_data.get('errmsg', '未知错误')}"
        _LOGGER.error(error_msg)
        
        if "invaliduser" in response_data:
            _LOGGER.warning("无效的用户ID: %s", response_data["invaliduser"])
        
        return False
    
    def _calculate_signature(self, token, timestamp, nonce, encrypt):
        token = str(token)
        timestamp = str(timestamp)
        nonce = str(nonce)
        encrypt = str(encrypt)
        
        params = sorted([token, timestamp, nonce, encrypt])
        sign_str = ''.join(params)
        return hashlib.sha1(sign_str.encode()).hexdigest()
    
    async def handle_callback(self, data):
        required = ["msg_signature", "timestamp", "nonce", "encrypt"]
        if not all(k in data for k in required):
            _LOGGER.error("回调数据缺失必要字段: %s", data)
            return "Invalid request", 400
        
        signature = str(data["msg_signature"])
        timestamp = str(data["timestamp"])
        nonce = str(data["nonce"])
        encrypt = str(data["encrypt"])
        
        calc_sign = self._calculate_signature(
            self.config["token"], timestamp, nonce, encrypt
        )
        
        if calc_sign != signature:
            _LOGGER.warning("签名验证失败! 收到签名: %s, 计算签名: %s", signature, calc_sign)
            return "签名验证失败", 400
        
        try:
            decrypted = self.encryptor.Decrypt(encrypt)
        except Exception as e:
            _LOGGER.error("解密失败: %s", str(e))
            return "解密失败", 400
        
        try:
            xml_tree = ET.fromstring(decrypted)
        except ET.ParseError as e:
            _LOGGER.error("XML解析失败: %s", str(e))
            return "XML解析失败", 400
        
        # 获取公共字段
        msg_type = xml_tree.find("MsgType").text
        user_id = xml_tree.find("FromUserName").text
        create_time = int(xml_tree.find("CreateTime").text)
        agent_id = int(xml_tree.find("AgentID").text)
        
        event_data = {
            "user": user_id,
            "type": msg_type,
            "timestamp": create_time,
            "agent_id": agent_id
        }
        
        # 根据消息类型解析特定字段 - 新增菜单点击事件处理
        if msg_type == "text":
            event_data["content"] = xml_tree.find("Content").text
        elif msg_type == "image":
            event_data["pic_url"] = xml_tree.find("PicUrl").text
            event_data["media_id"] = xml_tree.find("MediaId").text
        elif msg_type == "location":
            location_x = xml_tree.find("Location_X").text
            location_y = xml_tree.find("Location_Y").text
            scale = xml_tree.find("Scale").text
            label = xml_tree.find("Label").text
            
            event_data["lat"] = location_x
            event_data["lon"] = location_y
            event_data["scale"] = float(scale) if scale else None
            event_data["label"] = label
        elif msg_type == "event":  # 处理事件类型
            event_type = xml_tree.find("Event").text
            if event_type == "click":  # 菜单点击事件
                event_key = xml_tree.find("EventKey").text
                event_data.update({
                    "type": "menu_click",  # 使用特殊类型标识菜单点击
                    "event_key": event_key  # 添加event_key字段
                })
        
        # 触发事件
        self.hass.bus.async_fire("workchat_message", event_data)
        
        return self._generate_response("success")
    
    def _generate_response(self, content):
        timestamp = str(int(time.time()))
        nonce = "123456"
        encrypt = self.encryptor.Encrypt(content)
        signature = self._calculate_signature(
            self.config["token"], timestamp, nonce, encrypt
        )
        
        return f"""<xml>
            <Encrypt><![CDATA[{encrypt}]]></Encrypt>
            <MsgSignature><![CDATA[{signature}]]></MsgSignature>
            <TimeStamp>{timestamp}</TimeStamp>
            <Nonce><![CDATA[{nonce}]]></Nonce>
        </xml>"""
