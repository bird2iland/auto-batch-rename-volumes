# Auto-Batch-Rename-Volumes (批量自动卷重命名工具)

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Auto-Batch-Rename-Volumes** 是一款专为摄影师、DIT（数字影像工程师）和 IT 管理人员设计的 macOS 效率工具。它能够自动识别、监控并批量重命名外部存储介质（如 U 盘、SD 卡、CFexpress 卡等），支持复杂的命名规则提取，确保您的工作流高效且标准化。

## ✨ 核心特性

- 🚀 **批量处理**：一键重命名所有挂载的外部卷。
- 🔍 **智能扫描**：自动遍历卷内文件，基于视频或元数据文件示例提取卷名。
- 🕒 **实时监控**：开启监控模式，新插入的存储卡将自动触发重命名流程。
- 🛡️ **安全机制**：
    - **持久化白名单**：手动排除不需要操作的设备，配置自动保存。
    - **系统保护**：自动过滤系统关键分区，防止误操作。
    - **二次确认**：所有操作均有预览，确认无误后方可执行。
- 📊 **操作日志**：所有重命名历史均有据可查。
- 🎨 **现代 UI**：基于 `rich` 库构建的精美终端交互界面。

## 🛠️ 技术栈

- **语言**: Python 3.8+
- **环境管理**: [uv](https://github.com/astral-sh/uv) (极速 Python 依赖管理)
- **UI 库**: [rich](https://github.com/Textualize/rich)
- **核心工具**: macOS `diskutil` 原生集成

## 📦 快速开始

### 1. 安装 uv
如果您尚未安装 `uv`，请先安装：
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 克隆项目
```bash
git clone https://github.com/YOUR_USERNAME/auto-batch-rename-volumes.git
cd auto-batch-rename-volumes
```

### 3. 运行程序
使用 `uv` 运行，它会自动处理所有依赖：
```bash
uv run main.py
```

## 📖 使用指南

### 1. 扫描并重命名 (Scan & Rename)
手动触发对当前连接的所有 U 盘或 SD 卡的扫描。您可以选择：
- **自动递增**：例如输入 `CARD#`，起始 `1`，生成 `CARD#1`, `CARD#2`...
- **文件名提取**：程序会列出每个卷的文件示例，您可以指定扩展名（如 `mp4`）并选择提取文件名（Stem）的前缀或后缀。

### 2. 实时监控 (Monitoring)
开启后，程序将进入后台轮询。每当您插入一张新卡，程序都会立即识别并弹出重命名交互界面，非常适合 DIT 大批量倒卡场景。

### 3. 白名单管理 (Whitelist)
通过设备唯一 ID（Device Identifier）锁定特定磁盘。加入白名单后的磁盘在任何模式下都会被自动忽略。

## 📝 许可证

本项目采用 [MIT 许可证](LICENSE) 开源。

---
*由摄影师为摄影师打造。*
