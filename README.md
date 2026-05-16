# <img src="custom_components/workchat_integration/brand/icon.png" width="64"> 企微通 (WorkChat Integration)

[![Release](https://img.shields.io/github/v/release/hzonz/workchat_integration)](https://github.com/hzonz/workchat_integration/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/hzonz/workchat_integration/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

## 企微通集成允许Home Assistant与企业微信（WorkChat）无缝集成，实现双向通信功能。通过此集成，您可以：  从Home Assistant向企业微信发送各种类型的消息（文本、图片、文件、卡片、模板等）  接收企业微信发送的消息（文本、图片、位置等）  在Home Assistant中展示接收的消息内容和回调信息

## 🌟 功能概览

- 📨 **消息发送**：支持纯文本、Markdown、文本卡片、图文消息（News）以及最新的交互式模版卡片。
- 📤 **媒体中转**：支持将本地文件/监控抓图上传至企微服务器。
- 🔄 **双向通信**：既能发送通知，也能通过 Webhook 接收企微消息（文字、图片、位置、菜单点击）。
- 📊 **传感器集成**：将接收的消息和状态展示为传感器实体。
- 🔐 **安全验证**：基于 AES-CBC 32位对齐加密，确保你的家居数据在公网传输中绝对安全。
- 🌐 **代理支持**：通过HTTP代理访问企业微信API，解决动态IP问题。

## 📦 安装

### 通过HACS安装（推荐）

1. 在HACS的"集成"部分，点击右上角的三点菜单
2. 选择"自定义存储库"
3. 在存储库字段输入：`https://github.com/hzonz/workchat_integration`
4. 类别选择"集成"
5. 点击"添加"保存
6. 在HACS中找到"企微通"集成并点击安装
7. 重启Home Assistant

### 手动安装

1. 下载最新的: `https://github.com/hzonz/workchat_integration`
2. 解压并将`workchat_integration`文件夹放入Home Assistant的`custom_components`目录
3. 重启Home Assistant

## 📖 文档导航
- [🚀 详细配置与使用教程 (DOCS.md)](md/DOCS.md)
- [📜 版本更新历史 (CHANGELOG.md)](md/CHANGELOG.md)

## 🤝 贡献

欢迎贡献代码、报告问题或提出功能建议！

1. 提交Issues：报告问题或功能请求
2. 提交Pull Requests：贡献代码改进
3. 项目讨论：分享使用经验或建议

## 📄 许可证

本项目基于MIT许可证开源。详情请查看LICENSE文件。

## ❤️ 支持

如果这个项目对您有帮助，请给项目点个Star ⭐！

---
**兼容版本**: Home Assistant 2024.5+
