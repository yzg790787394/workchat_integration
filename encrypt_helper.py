import base64
from Crypto.Cipher import AES
import struct
import logging

_LOGGER = logging.getLogger(__name__)

class EncryptHelper:
    def __init__(self, key, token) -> None:
        self.key = self._process_key(key)
        self.token = token

    def _process_key(self, key):
        """处理企业微信EncodingAESKey - 增强健壮性"""
        # 去除空格并验证格式
        key = key.strip()
        if not key.endswith('=') and len(key) in (43, 44):
            key += '='
        try:
            return base64.b64decode(key)
        except Exception as e:
            _LOGGER.error("Base64解码失败: %s | 密钥: %s", str(e), key)
            raise

    def Encrypt(self, data):
        """加密消息 - 企业微信官方方案"""
        try:
            # 生成16字节随机字符串
            import random
            import string
            random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
            # 构造消息格式: [随机16B][消息长度4B][消息体][企业ID]
            msg_bytes = data.encode('utf-8')
            msg_len = struct.pack('>I', len(msg_bytes))
            receive_id = self.token.encode('utf-8')
            plaintext = random_str.encode('utf-8') + msg_len + msg_bytes + receive_id
            
            # 进行PKCS#7填充
            block_size = AES.block_size
            pad_len = block_size - (len(plaintext) % block_size)
            padding = bytes([pad_len]) * pad_len
            plaintext += padding
            
            # AES-CBC加密
            iv = self.key[:16]
            cipher = AES.new(self.key, AES.MODE_CBC, iv=iv)
            encrypted = cipher.encrypt(plaintext)
            
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            _LOGGER.error("加密失败: %s", str(e))
            raise

    def Decrypt(self, data):
        """解密消息 - 企业微信官方方案 (修复填充问题)"""
        try:
            # 增加空值检查
            if not data:
                raise ValueError("空加密数据")
                
            # Base64解码
            encrypted_data = base64.b64decode(data)
            
            # AES-CBC解密
            iv = self.key[:16]
            cipher = AES.new(self.key, AES.MODE_CBC, iv=iv)
            decrypted = cipher.decrypt(encrypted_data)
            
            # 手动移除填充（兼容企业微信官方实现）
            pad_len = decrypted[-1]
            # 检查填充长度是否有效
            if pad_len < 1 or pad_len > AES.block_size:
                # 尝试使用最后一位作为填充长度
                # 企业微信官方库使用这种更宽松的方式
                _LOGGER.debug("使用最后字节作为填充长度: %s", pad_len)
                decrypted = decrypted[:-pad_len]
            else:
                # 标准PKCS#7填充移除
                decrypted = decrypted[:-pad_len]
            
            # 解析结构: [随机16B][消息长度4B][消息体][企业ID]
            msg_len = struct.unpack('>I', decrypted[16:20])[0]
            content = decrypted[20:20+msg_len].decode('utf-8')
            
            return content
        except Exception as e:
            _LOGGER.error("解密失败 | 输入数据: %s... | 错误: %s", 
                          data[:50] if data else '空', str(e))
            raise
