"""企业微信加解密助手."""
from __future__ import annotations

import base64
import logging
import os
import struct
from typing import Final

# Home Assistant 环境下建议使用 pycryptodome (manifest.json 中需包含)
from Crypto.Cipher import AES

_LOGGER = logging.getLogger(__name__)

BLOCK_SIZE: Final = 32  # 企微固定 32 字节对齐
IV_SIZE: Final = 16

class EncryptHelper:
    """处理企业微信消息加解密的助手类."""

    def __init__(self, aes_key_base64: str, receive_id: str) -> None:
        """初始化加密助手."""
        self.receive_id = receive_id
        try:
            # 企微 EncodingAESKey 固定为 43 位，加 "=" 补齐为 44 位进行 Base64 解码
            key_decode_str = aes_key_base64.strip() + "="
            self.key = base64.b64decode(key_decode_str)
            if len(self.key) != 32:
                raise ValueError(f"AES Key 长度错误: 预期 32 字节，实际 {len(self.key)}")
        except Exception as err:
            _LOGGER.error("EncodingAESKey 解码失败: %s", err)
            raise ValueError("Invalid EncodingAESKey") from err

    def encrypt(self, text: str) -> str:
        """加密消息内容."""
        try:
            text_bytes = text.encode("utf-8")
            # 1. 构造包体: random(16B) + msg_len(4B) + msg + receive_id
            random_bytes = os.urandom(16)
            msg_len = struct.pack(">I", len(text_bytes))
            receive_id_bytes = self.receive_id.encode("utf-8")
            
            raw_data = random_bytes + msg_len + text_bytes + receive_id_bytes
            
            # 2. PKCS#7 填充 (32 字节块对齐)
            pad_len = BLOCK_SIZE - (len(raw_data) % BLOCK_SIZE)
            raw_data += bytes([pad_len]) * pad_len
            
            # 3. AES-CBC 加密 (企微规定 IV 为 Key 的前 16 位)
            cipher = AES.new(self.key, AES.MODE_CBC, iv=self.key[:IV_SIZE])
            encrypted_bytes = cipher.encrypt(raw_data)
            
            return base64.b64encode(encrypted_bytes).decode("utf-8")
        except Exception as err:
            _LOGGER.error("企微加密异常: %s", err)
            raise

    def decrypt(self, encrypted_base64: str) -> str:
        """解密消息内容."""
        if not encrypted_base64:
            raise ValueError("加密数据为空")

        try:
            # 1. Base64 解码
            encrypted_bytes = base64.b64decode(encrypted_base64)
            
            # 2. AES-CBC 解密
            cipher = AES.new(self.key, AES.MODE_CBC, iv=self.key[:IV_SIZE])
            decrypted_raw = cipher.decrypt(encrypted_bytes)
            
            # 3. 移除 PKCS#7 填充
            pad_len = decrypted_raw[-1]
            if pad_len < 1 or pad_len > BLOCK_SIZE:
                pad_len = 0
            content_raw = decrypted_raw[:-pad_len] if pad_len > 0 else decrypted_raw
            
            # 4. 提取结构信息 (前 16 字节是随机字符串)
            # content_raw[16:20] 是 4 字节的消息长度
            msg_len = struct.unpack(">I", content_raw[16:20])[0]
            
            # 5. 提取消息正文
            msg_content = content_raw[20 : 20 + msg_len].decode("utf-8")
            
            # 6. 校验 CorpID
            received_id = content_raw[20 + msg_len :].decode("utf-8").strip()
            if received_id != self.receive_id:
                _LOGGER.warning(
                    "企微加解密校验失败: 收到 ID %s, 配置 ID %s", 
                    received_id, self.receive_id
                )
            
            return msg_content
        except Exception as err:
            _LOGGER.error("企微解密失败 (检查 EncodingAESKey): %s", err)
            raise
