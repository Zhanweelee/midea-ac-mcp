# Midea AC MCP Server ❄️

Model Context Protocol (MCP) 服务器，用于通过大语言模型控制美的（及同生态品牌）智能空调。

基于 [msmart-ng](https://github.com/tuckkern/msmart-ng) 库，走局域网本地协议，无需云账号。

## 功能

- 🔍 自动发现局域网中的美的空调
- 📊 查看空调状态（开关、温度、模式、风速）
- 🔛 开关机
- 🌡 调节目标温度
- 🌀 切换运行模式（制冷/制热/除湿/送风/自动）
- 💨 调节风速（自动/静音/低风/中风/高风/强力）

## 快速开始

### 前置条件

- Python 3.10+
- 空调已通过美的美居 App 接入 WiFi
- 运行本服务的设备与空调在同一局域网

### 安装

```bash
# 克隆仓库
git clone https://github.com/JonathanLee/midea-ac-mcp.git
cd midea-ac-mcp

# 安装依赖
pip install -r requirements.txt
```

### 扫描设备

```bash
python3 server.py --scan
```

### 配置 MCP 客户端

#### OpenClaw

```bash
openclaw mcp add midea-ac \
  --command python3 \
  --arg /path/to/midea-ac-mcp/server.py
```

#### Claude Desktop / Cline

```json
{
  "mcpServers": {
    "midea-ac": {
      "command": "python3",
      "args": ["/path/to/midea-ac-mcp/server.py"]
    }
  }
}
```

## 工具说明

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `discover_devices` | 扫描局域网发现美的空调 | 无 |
| `get_status` | 获取空调当前状态 | `ip`（可选） |
| `set_power` | 开关空调 | `state`（必填 true/false） |
| `set_temperature` | 设置目标温度 | `temperature`（必填） |
| `set_mode` | 切换运行模式 | `mode`（必填：制冷/制热/除湿/送风/自动） |
| `set_fan_speed` | 调节风速 | `speed`（必填：自动/静音/低风/中风/高风/强力） |

> 所有工具均支持可选的 `ip` 参数。不传 ip 则自动发现第一台空调。

## 使用示例

```text
用户：空调调到26度
→ 调用 set_temperature(temperature=26)

用户：开空调，制冷模式，风速自动
→ 调用 set_power(state=true)
→ 调用 set_mode(mode="制冷")
→ 调用 set_fan_speed(speed="自动")

用户：空调现在什么状态？
→ 调用 get_status()
```

## 工作原理

```
MCP Client → stdio → midea-ac-mcp/server.py → msmart-ng (UDP广播) → 美的空调
```

所有通信在局域网内完成，不经过云端。

## 技术栈

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP 服务器框架
- [msmart-ng](https://github.com/tuckkern/msmart-ng) — 美的空调局域网控制库
- Python asyncio — 异步 I/O

## 许可证

MIT
