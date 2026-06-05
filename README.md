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

### 本地运行（推荐）

```bash
# 克隆仓库
git clone https://github.com/JonathanLee/midea-ac-mcp.git
cd midea-ac-mcp

# 安装依赖
pip install -r requirements.txt

# 扫描局域网中的美的空调
python3 server.py --scan

# 启动 MCP Server（stdio 模式，用于 MCP 客户端）
python3 server.py

# 或启动 HTTP 模式（供远程访问）
python3 server.py --transport streamable-http --host 0.0.0.0 --port 8000
```

### Docker 运行

```bash
# 使用 docker-compose（推荐，自动使用 host 网络模式）
docker-compose up -d

# 或直接使用 Docker
docker build -t midea-ac-mcp .
docker run -d \
  --name midea-ac-mcp \
  --network host \
  --restart unless-stopped \
  midea-ac-mcp
```

> ⚠️ **重要**: 必须使用 `--network host`（主机网络模式），因为 Midea AC 通过 UDP 广播发现，容器默认的 bridge 网络无法广播到宿主机局域网。

### macOS 注意事项

macOS 下 UDP 广播可能需要额外权限。如果 `--scan` 报 `errno 49`，请：

1. 确保空调和 MacBook 在同一个 WiFi 网络
2. 确认空调已通电且连接 WiFi
3. 直接指定空调 IP 连接（见下文「指定 IP」）

## 使用方式

### MCP 客户端配置

#### OpenClaw

```bash
# stdio 模式
openclaw mcp add midea-ac \
  --command python3 \
  --arg /path/to/midea-ac-mcp/server.py

# HTTP 模式（远程 Docker 部署）
openclaw mcp add midea-ac \
  --url http://host-ip:8000/mcp \
  --transport streamable-http
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

#### Claude Desktop（HTTP 远程模式）

```json
{
  "mcpServers": {
    "midea-ac": {
      "url": "http://host-ip:8000/mcp"
    }
  }
}
```

### 指定空调 IP

对于已知 IP 的空调，所有工具都支持 `ip` 参数，跳过自动发现：

```text
用户：帮我查一下 192.168.1.100 这台空调的状态
→ 调用 get_status(ip="192.168.1.100")

用户：把 192.168.1.100 调到 26 度
→ 调用 set_temperature(temperature=26, ip="192.168.1.100")
```

## 工具说明

| 工具名 | 说明 | 必须参数 | 可选参数 |
|--------|------|---------|---------|
| `discover_devices` | 扫描局域网发现美的空调 | — | — |
| `get_status` | 获取空调当前状态 | — | `ip` |
| `set_power` | 开关空调 | `state` (true/false) | `ip` |
| `set_temperature` | 设置目标温度 | `temperature` (16-31°C) | `ip` |
| `set_mode` | 切换运行模式 | `mode` (制冷/制热/除湿/送风/自动) | `ip` |
| `set_fan_speed` | 调节风速 | `speed` (自动/静音/低风/中风/高风/强力) | `ip` |

## 使用示例

```text
用户：空调调到26度
→ set_temperature(temperature=26)

用户：开空调，制冷模式，风速自动
→ set_power(state=true)
→ set_mode(mode="制冷")
→ set_fan_speed(speed="自动")

用户：空调现在什么状态？
→ get_status()

用户：帮我查一下192.168.1.100的状态
→ get_status(ip="192.168.1.100")
```

## Docker 部署

### 项目结构

```
midea-ac-mcp/
├── Dockerfile            # Docker 构建文件
├── docker-compose.yml    # Docker Compose 配置
├── requirements.txt      # Python 依赖
├── server.py             # MCP Server 主程序
└── README.md             # 本文件
```

### 构建与运行

```bash
# 构建镜像
docker build -t midea-ac-mcp .

# 启动（host 网络模式）
docker run -d \
  --name midea-ac-mcp \
  --network host \
  --restart unless-stopped \
  midea-ac-mcp
```

### 暴露端口

默认以 HTTP 模式运行在 `8000` 端口，MCP 端点路径为 `/mcp`：

```
http://<host-ip>:8000/mcp
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  midea-ac-mcp:
    build: .
    container_name: midea-ac-mcp
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
    network_mode: host    # 必须！用于 UDP 广播发现空调
    restart: unless-stopped
```

## 命令行选项

| 选项 | 说明 |
|------|------|
| `--scan` | 扫描局域网发现美的空调 |
| `--transport stdio` | stdio 模式（默认，用于 MCP 客户端） |
| `--transport streamable-http` | HTTP 模式（用于 Docker/远程访问） |
| `--host HOST` | HTTP 监听地址（默认 0.0.0.0） |
| `--port PORT` | HTTP 监听端口（默认 8000） |

## 网络架构

```
┌──────────────┐     stdio/http      ┌──────────────┐    UDP广播    ┌──────────┐
│ MCP Client   │ ◄─────────────────► │ midea-ac-mcp  │ ◄──────────► │ 美的空调  │
│ (Claude/     │                      │ (server.py)   │              │ (局域网)  │
│  OpenClaw)   │                      │               │              │          │
└──────────────┘                      └──────────────┘              └──────────┘
```

所有通信在局域网内完成，不经过云端。

## 技术栈

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP 服务器框架
- [msmart-ng](https://github.com/tuckkern/msmart-ng) — 美的空调局域网控制库
- Python asyncio — 异步 I/O

## 许可证

MIT
