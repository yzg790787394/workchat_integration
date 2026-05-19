# 使用指南 (Documentation)

## ⚙️ 配置

### 步骤1：获取企业微信参数

在开始配置前，您需要从企业微信管理后台获取以下信息：

1. **企业ID(Corp ID)**：企业微信的唯一标识
2. **应用Secret**：企业微信应用的密钥
3. **应用Agent ID**：企业微信应用的ID
4. **获取令牌和密钥**：
   - 登录企业微信管理后台
   - 进入"应用管理" > 选择您的应用 > "接收消息"
   - 点击"设置API接收"
   - 点击随机获取，将获取以下信息：
      - **Token**：用于回调验证的令牌
      - **EncodingAESKey**：用于消息加密的密钥

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

### 步骤3：设置企业微信回调

配置完成后，您需要将回调URL设置到企业微信后台：

1. 在集成配置完成后，查看**回调状态实体属性Webhook url**（格式如：`https://your-ha-domain/api/workchat_callback/your_token`）
2. 登录企业微信管理后台
3. 进入"应用管理" > 选择您的应用 > "接收消息"
4. 点击"设置API接收"
5. 填入以下信息：
   - **URL**：Home Assistant中显示的回调URL
   - **Token**：与配置中相同的Token
   - **EncodingAESKey**：与配置中相同的EncodingAESKey
6. 保存设置并启用

**配置企业微信可信IP**：

将您的公网IP添加到企业微信应用的可信IP列表中。


## 🚀 服务使用

### 1.通知程序实体

通过`notify.send_message`服务发送消息到企业微信。

#### 示例
```yaml
action: notify.send_message
data:
  message: 你好
target:
  entity_id: notify.workchat_app_1000002_notifier  // 企微通 通知实体

```
注：通知消息服务，只支持文本消息

### 2. 消息通知服务

通过`workchat_integration.notify`服务发送消息到企业微信。

#### 基本示例
```yaml
service: workchat_integration.notify
data:
  msg_type: text
  message: "传感器状态异常！"
```

#### 完整参数

| 参数 | 必填 | 类型 | 默认值 | 描述 |
|------|------|------|--------|------|
| `msg_type` | 是 | string | "text" | 消息类型：text, image, video, file, textcard, news,template_card |
| `message` | 是 | string | - | 消息基础内容（文本/描述） |
| `title` | 否 | string | - | 消息标题（用于卡片、视频和图文消息） |
| `media_id` | 部分类型必填 | string | - | 媒体文件ID（需先上传） |
| `url` | 部分类型必填 | string | - | 链接地址（卡片跳转/图文URL） |
| `btntxt` | 否 | string | "详情" | 卡片消息按钮文字 |
| `articles` | 图文消息必填 | list | - | 图文消息的多篇文章（YAML格式） |
| `touser` | 否 | string | 配置值 | 指定接收用户（@all或用户ID） |

#### 消息类型示例

**文本消息**
```yaml
action: workchat_integration.notify
data:
  msg_type: text
  message: "客厅温度过高！当前温度: {{ states('sensor.living_room_temperature') }}℃"
```

**图片消息**
```yaml
action: workchat_integration.notify
data:
  msg_type: image
  media_id: "1Yv-zXfHjSjU-7LH-GwtYqDGS"
  message: "客厅监控截图"
```

**卡片消息**
```yaml
action: workchat_integration.notify
data:
  msg_type: textcard
  title: "安防通知"
  message: "前门检测到有人活动"
  url: "https://your-ha-domain/lovelace/security"
  btntxt: "查看详情"
```

**图文消息**
```yaml
action: workchat_integration.notify
data:
  msg_type: news
  articles:
    - title: "天气预警"
      description: "今日将有暴雨，请关好门窗"
      url: "https://weather.com"
      picurl: "https://example.com/weather.jpg"
    - title: "设备状态"
      description: "所有设备运行正常"
      url: "https://your-ha-domain/lovelace/devices"
```

**模板消息**

****基础传感器报表****
```yaml
action: workchat_integration.notify
data:
  msg_type: template_card
  template_card_data:
    card_type: horizontal_content_list
    source:
      item_name: "HA 智能管家"
      icon_url: "https://home-assistant.io/images/favicon-192x192.png"
    main_title:
      title: "客厅环境报告"
      desc: "当前室内环境数据已更新"
    horizontal_content_list:
      - keyname: "室内温度"
        value: "26.5℃"
      - keyname: "室内湿度"
        value: "45%"
        type: 0
      - keyname: "空气质量"
        value: "优"
        color: 2  # 绿色
    jump_list:
      - type: 1
        title: "查看详情"
        url: "https://your-ha.com/lovelace/living-room"
    card_action:
      type: 1
      url: "https://your-ha.com/lovelace/living-room"
```

****安防警报****
```yaml
action: workchat_integration.notify
data:
  msg_type: template_card
  template_card_data:
    card_type: text_notice
    source:
      item_name: "安防中心"
    main_title:
      title: "🚨 发现非法闯入"
    sub_title_text: "前门区域检测到移动异常"
    horizontal_content_list:
      - keyname: "发生位置"
        value: "别墅前门"
      - keyname: "警报级别"
        value: "特急"
        color: 1  # 红色强调
    card_action:
      type: 1
      url: "https://your-ha.com/lovelace/security"
```

****自动化示例****
```yaml
action: workchat_integration.notify
data:
  msg_type: template_card
  template_card_data:
    card_type: horizontal_content_list
    source:
      item_name: "能源监控"
    main_title:
      title: "今日用电统计"
    horizontal_content_list:
      - keyname: "累计用电"
        value: "{{ states('sensor.daily_energy') }} kWh"
      - keyname: "当前功率"
        value: "{{ states('sensor.current_power') }} W"
        color: >
          {% if states('sensor.current_power')|float > 2000 %} 1 {% else %} 0 {% endif %}
    card_action:
      type: 1
      url: "https://your-ha.com/lovelace/energy"
```

### 3. 媒体上传服务

使用`workchat_integration.upload_media`服务上传文件到企业微信并获取media_id。

#### 基本用法
```yaml
service: workchat_integration.upload_media
data:
  file_path: "/config/www/snapshot.jpg"
```

#### 完整参数

| 参数 | 必填 | 类型 | 默认值 | 描述 |
|------|------|------|--------|------|
| `type` | 否 | string | "file" | 媒体类型：file, image, video, voice |
| `file_path` | 是 | string | - | 本地文件完整路径 |
| `file_name` | 否 | string | 自动获取 | 自定义文件名 |

#### 上传示例
```yaml
action: workchat_integration.upload_media
data:
  type: image
  file_path: "/config/www/living_room_snapshot.jpg"
  file_name: "living_room.jpg"
```

#### 响应示例
服务调用成功后会返回media_id：
```json
{
  "media_id": "2hY-zXfHjSjU-8LH-GwtYqDHT"
}
```

## 🔍 传感器

集成添加后会自动创建以下传感器实体：

### 1. 企微通文本消息传感器
- **状态**：最新收到的文本内容
- **属性**：
  - 用户`From user`：发送消息的用户ID
  - 时间`Receive time`：消息时间戳
  - 内容`Raw info`：完整消息内容

### 2. 企微通图片消息传感器
- **状态**：图片消息
- **属性**：
  - 用户`From user`：发送消息的用户ID
  - 时间`Receive time`：消息时间戳
  - 图片UR`Pic url`L：图片访问地址
  - 媒体ID`Media ID`：媒体文件ID
  - 内容`Raw info`：完整消息内容

### 3. 企微通位置消息传感器
- **状态**：位置标签
- **属性**：
  - 用户：发送消息的用户ID
  - 时间：消息时间戳
  - 纬度：位置纬度
  - 经度：位置经度
  - 缩放级别：地图缩放比例
  - 位置标签：位置描述


### 4. 企微通回调URL信息传感器
- **状态**：配置状态
- **属性**：
  - 回调URL：用于企业微信的回调地址
  - Token：验证令牌
  - EncodingAESKey：加密密钥

### 5. 企微通上传媒体文件信息传感器
- **状态**：上传状态
- **属性**：
  - 文件名：上传的文件名
  - 文件类型：媒体类型
  - 上传时间：上传完成时间
  - 文件路径：本地文件路径
  - media_id：上传后获得的媒体ID

## ⚡ 高级功能

### 自动化示例

**当温度过高时发送通知**
```yaml
alias: 高温报警通知
trigger:
  - platform: numeric_state
    entity_id: sensor.living_room_temperature
    above: 30
action:
  - service: workchat_integration.notify
    data:
      msg_type: textcard
      title: "高温警告"
      message: >
        客厅温度过高！当前温度: {{ states('sensor.living_room_temperature') }}℃
        建议打开空调
      url: "https://your-ha-domain/lovelace/climate"
      btntxt: "调整空调"
```

**接收位置消息时更新设备追踪器**
```yaml
alias: 更新位置追踪
trigger:
  - platform: event
    event_type: workchat_message
    event_data:
      type: location
action:
  - service: device_tracker.see
    data:
      dev_id: mobile_app_workchat
      location_name: "{{ trigger.event.data.label }}"
      gps:
        - "{{ trigger.event.data.lat }}"
        - "{{ trigger.event.data.lon }}"
```

## 🛠 故障排除 (Troubleshooting)

集成运行异常时，请优先使用内置的 可视化诊断工具。

### 1. 快速诊断入口

直接在浏览器访问您的 Webhook 回调地址（即您在企微后台配置的那个 URL）：
https://您的域名/api/workchat_callback/您的Token

- 显示“集成已运行”：说明 HA 外部访问权限和 Webhook 路由解析完全正常。
- Access Token 显示“未获取 (Error)”：请检查集成配置中的 CorpID 和 Secret 是否正确，并确认 HA 是否能够正常访问外网。
- 页面无法打开：说明内网穿透（如 FRP/域名）或防火墙配置有误，企微服务器无法触达您的本地 HA。

### 2. 常见问题 (FAQ)

| **现象** | **可能原因** | **解决方法** |
|---------|--------------|--------------|
| **Token 获取失败** | 网络不通 / Secret 错误 | 在诊断页观察状态；检查 Secret 是否包含空格；验证代理服务器是否正常。 |
| **消息发送成功但收不到** | UserID 错误 / 应用可见范围不足 | 确认 `touser` 是成员账号（非手机号）；确认自建应用的“可见范围”包含该成员。 |
| **图片无法在传感器显示** | 媒体 ID 过期 / 权限问题 | Media ID 有效期仅 3 天，请勿在自动化中长期硬编码 ID。 |
| **签名验证失败** | 配置不一致 / 编码错误 | 检查企微后台的 Token 和 EncodingAESKey 是否与 HA 集成配置完全一致。 |
| **代理连接报错** | 地址格式错误 / 协议不支持 | 确保代理地址以 `http://` 或 `https://` 开头；本集成目前仅支持标准 HTTP/HTTPS 代理。 |


### 3. 日志分析

如果上述方法无法定位问题，请在 Home Assistant 的 configuration.yaml 中开启调试级别日志：
```
logger:
  default: info
  logs:
    custom_components.workchat_integration: debug
```
重启 HA 后，在系统日志中搜索 workchat_integration 关键字，即可看到详细的 API 请求与解密过程。

### 🔧 技术支持 (Technical Support)

#### 典型网络架构参考

对于家庭宽带（动态 IP）环境，推荐使用带有固定公网 IP 的 VPS 建立以下链路，以满足企微 API 的“可信 IP”要求：

```
[ 家庭局域网 ]                 [ 公网 VPS (固定IP) ]               [ 腾讯服务器 ]
      │                                 │                                 │
 Home Assistant                         FRP Server                        │
 (企微通集成)   ◀──────[ FRP 隧道 ]──────▶  (监听 443 端口)   ◀──────[ Webhook ]────── 企微回调
      │                                 │                                 │
   API 请求        ─────[ HTTP 代理 ]─────▶  Squid Proxy   ─────[ 可信 IP ]─────▶  企微 API
```

#### 关键组件说明：

1. FRP 穿透：负责将企微推送的回调信号（Webhook）安全地送回内网 HA。
2. HTTP 代理：负责将 HA 发出的 API 请求通过 VPS 转发，使企微识别到的是 VPS 的固定 IP（需填入企微后台的“可信 IP 列表”）。

#### 架构优势与性能优化

1. 全异步非阻塞 (Async IO)
本集成基于 aiohttp 彻底重构。所有网络交互（发信、上传、Token 获取）均在异步事件循环中运行。即使在弱网或代理延迟较高的情况下，也不会产生“同步阻塞警告”，确保灯光、开关等本地自动化不受网络波动影响。

2. 原子化令牌并发锁 (Token Lock)
内置异步锁机制。当多个自动化任务同时触发发信且 Access Token 正好过期时，集成会确保只有一个请求去腾讯服务器刷新令牌，其余任务将挂起等待并复用新令牌，有效防止触发企微 API 的高频调用限制。

3. 智能资源生命周期管理
- 自动容错：遇到 40014（Token 过期）错误码时，系统将触发瞬时静默重试。
- 内存优化：适配最新的 runtime_data 模式，在集成卸载时会自动清理所有 Webhook 路由、取消待处理的异步任务，确保零内存泄漏。
- 诊断可视化：将复杂的回调校验逻辑转化为直观的 Web 诊断页面，大幅降低了用户的配置与维护成本。
