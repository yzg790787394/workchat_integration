# 使用指南 (Documentation)

### 步骤1：获取企业微信参数

在开始配置前，您需要从企业微信管理后台获取以下信息：

1. **企业ID(Corp ID)**：企业微信的唯一标识
2. **应用Secret**：企业微信应用的密钥
3. **应用Agent ID**：企业微信应用的ID
4. **Token**：用于回调验证的令牌
5. **EncodingAESKey**：用于消息加密的密钥

**配置企业微信可信IP**：
将您的公网IP添加到企业微信应用的可信IP列表中。

### 步骤2：在Home Assistant中添加集成

1. 进入Home Assistant的 **设置** > **设备与服务** > **集成**
2. 点击右下角的 **+ 添加集成**
3. 搜索并选择 **"企微通"**
4. 填写以下配置参数：
   - **企业ID**：您的企业ID
   - **应用Secret**：应用的密钥
   - **应用Agent ID**：应用的ID
   - **Token**：回调验证令牌
   - **EncodingAESKey**：加密密钥
   - **接收用户**：默认接收消息的用户（如`@all`或指定用户ID）
   - **外部URL**：Home Assistant的外部访问地址（自动填充）  如：`http://*.*.*.*:****`
   - **代理地址**（可选）：HTTP代理地址，格式如`http://您的VPS_IP:3128`
5. 点击 **提交** 完成配置

![配置界面](img/配置界面1.jpeg)

### 步骤3：设置企业微信回调

配置完成后，您需要将回调URL设置到企业微信后台：

1. 在集成配置完成后，检查日志中显示的回调URL（格式如：`https://your-ha-domain/api/workchat_callback/your_token`）
2. 登录企业微信管理后台
3. 进入"应用管理" > 选择您的应用 > "接收消息"
4. 点击"设置API接收"
5. 填入以下信息：
   - **URL**：Home Assistant中显示的回调URL
   - **Token**：与配置中相同的Token
   - **EncodingAESKey**：与配置中相同的EncodingAESKey
6. 保存设置并启用

![回调URL配置](img/回调url.jpg)
