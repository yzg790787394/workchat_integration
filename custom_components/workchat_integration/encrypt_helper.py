"""企业微信加解密助手."""
from __future__ import annotations

import base64
import logging
import os
import struct
from typing import Final

from Crypto.Cipher import AES

_LOGGER = logging.getLogger(__name__)

# 定义常量
BLOCK_SIZE: Final = 32  # 企业微信固定使用 32 字节块大小进行填充
IV_SIZE: Final = 16

class EncryptHelper:
    """处理企业微信消息加解密的助手类."""

    def __init__(self, aes_key_base64: str, receive_id: str) -> None:
        """初始化加密助手.
        
        :param aes_key_base64: 企业微信后台提供的 EncodingAESKey
        :param receive_id: 企业 ID (CorpID)
        """
        self.receive_id = receive_id
        try:
            # 自动补全 base64 填充符号并解码
            key_bytes = base64.b64decode(aes_key_base64.strip() + "=" * (44 - len(aes_key_base64.strip())))
            self.key = key_bytes
        except Exception as err:
            _LOGGER.error("AES Key 解码失败，请检查 EncodingAESKey 是否正确: %s", err)
            raise ValueError("Invalid EncodingAESKey") from err

    def encrypt(self, text: str) -> str:
        """加密消息内容.
        
        遵循企微协议: Base64_Encode(AES_Encrypt[random(16B) + msg_len(4B) + msg + receive_id])
        """
        try:
            text_bytes = text.encode("utf-8")
            # 1. 构造原始数据包
            # random_bytes(16B) + msg_len(4B) + msg + receive_id
            random_bytes = os.urandom(16)  # 使用系统级随机数，更安全
            msg_len = struct.pack(">I", len(text_bytes))
            receive_id_bytes = self.receive_id.encode("utf-8")
            
            raw_data = random_bytes + msg_len + text_bytes + receive_id_bytes
            
            # 2. PKCS#7 填充 (注意：企微要求按 32 字节对齐，而非 AES 默认的 16)
            pad_len = BLOCK_SIZE - (len(raw_data) % BLOCK_SIZE)
            raw_data += bytes([pad_len]) * pad_len
            
            # 3. AES-CBC 加密
            cipher = AES.new(self.key, AES.MODE_CBC, iv=self.key[:IV_SIZE])
            encrypted_bytes = cipher.encrypt(raw_data)
            
            return base64.b64encode(encrypted_bytes).decode("utf-8")
        except Exception as err:
            _LOGGER.error("加密失败: %s", err)
            raise

    def decrypt(self, encrypted_base64: str) -> str:
        """解密消息内容."""
        if not encrypted_base64:
            raise ValueError("收到空加密数据")

        try:
            # 1. Base64 解码
            encrypted_bytes = base64.b64decode(encrypted_base64)
            
            # 2. AES-CBC 解密
            cipher = AES.new(self.key, AES.MODE_CBC, iv=self.key[:IV_SIZE])
            decrypted_raw = cipher.decrypt(encrypted_bytes)
            
            # 3. 移除填充 (PKCS#7)
            pad_len = decrypted_raw[-1]
            if pad_len < 1 or pad_len > BLOCK_SIZE:
                pad_len = 0
            content_raw = decrypted_raw[:-pad_len] if pad_len > 0 else decrypted_raw
            
            # 4. 解析协议结构
            # 结构: [16B random] + [4B len] + [msg] + [receive_id]
            msg_len = struct.unpack(">I", content_raw[16:20])[0]
            msg_content = content_raw[20 : 20 + msg_len].decode("utf-8")
            
            # 5. 校验 ReceiveID (CorpID) 是否匹配
            # 增加 .strip() 防止因不可见字符导致的匹配失败
            received_corp_id = content_raw[20 + msg_len :].decode("utf-8").strip()
            configured_corp_id = self.receive_id.strip()

            if received_corp_id != configured_corp_id:
                _LOGGER.warning(
                    "企微回调校验 ID 不匹配! 收到: %s, 配置: %s. "
                    "请检查集成配置中的 CorpID 是否填错。",
                    received_corp_id, configured_corp_id
                )
                # 即使不匹配也建议返回内容，方便调试，或者抛出异常拦截
            
            return msg_content
        except Exception as err:
            _LOGGER.error("解密包结构解析失败: %s", err)
            raise
