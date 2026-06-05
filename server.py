#!/usr/bin/env python3
"""
Midea Air Conditioner MCP Server

Controls Midea (and associated brands) smart air conditioners
via local network protocol using the msmart-ng library.

Usage:
    python3 server.py          # Start stdio MCP server (for OpenClaw)
    python3 server.py --scan   # Scan network and list devices
"""

import asyncio
import json
import os
import sys
import socket
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from msmart.device import AirConditioner
from msmart.discover import Discover
from msmart.const import DeviceType

logging.basicConfig(level=logging.WARNING)
_LOGGER = logging.getLogger("midea-mcp")

# ─── macOS UDP broadcast fix ──────────────────────────────────────────────
# msmart-ng binds to 0.0.0.0 which fails on macOS (errno 49).
# We patch Discover.discover to use subnet broadcast + pre-bound socket.

_local_ip: Optional[str] = None
_subnet_broadcast: Optional[str] = None


def _get_local_ip() -> str:
    global _local_ip
    if _local_ip:
        return _local_ip
    local_ip = os.environ.get("MIDEA_LOCAL_IP")
    if local_ip:
        _local_ip = local_ip
        return _local_ip

    try:
        import fcntl
        import struct
        for name in sorted(socket.if_nameindex(), key=lambda x: x[0]):
            iface = name[1]
            if iface.startswith(("lo", "utun", "llw", "awdl", "bridge", "gif", "stf")):
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                ip = socket.inet_ntoa(
                    fcntl.ioctl(s.fileno(), 0xC0206921, struct.pack("256s", iface.encode()[:15]))[20:24]
                )
                s.close()
                if ip and not ip.startswith("127."):
                    _local_ip = ip
                    return _local_ip
            except Exception:
                continue
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("1.1.1.1", 1))
        _local_ip = s.getsockname()[0]
        s.close()
        return _local_ip or "127.0.0.1"
    except Exception:
        return "127.0.0.1"


def _get_subnet_broadcast() -> str:
    global _subnet_broadcast
    if _subnet_broadcast:
        return _subnet_broadcast
    local_ip = _get_local_ip()
    parts = local_ip.rsplit(".", 1)
    _subnet_broadcast = f"{parts[0]}.255" if len(parts) == 2 else "255.255.255.255"
    return _subnet_broadcast


# Patch Discover.discover to bind to LAN IP instead of 0.0.0.0
import msmart.discover as _disc

_orig_discover_classmethod = Discover.discover


async def _patched_discover(
    cls,
    *,
    target=None,
    timeout=5,
    discovery_packets=3,
    interface=None,
    region="",
    account=None,
    password=None,
    auto_connect=False,
    get_async_client=None,
):
    """Patched discover: uses subnet broadcast + pre-bound socket to avoid macOS errno 49."""

    if target is None:
        target = _get_subnet_broadcast()

    if cls._lock is None:
        cls._lock = asyncio.Lock()

    cls._cloud = None
    cls._get_async_client = get_async_client
    cls._region = region
    cls._account = account
    cls._password = password
    cls._auto_connect = auto_connect

    loop = asyncio.get_event_loop()
    local_ip = _get_local_ip()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    try:
        sock.bind((local_ip, 0))
    except OSError:
        _LOGGER.warning("Could not bind to %s, falling back to 0.0.0.0", local_ip)
        sock.bind(("0.0.0.0", 0))

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: _disc._DiscoverProtocol(
            target=target,
            discovery_packets=discovery_packets,
            interface=interface,
        ),
        sock=sock,
    )
    protocol = _disc.cast(_disc._DiscoverProtocol, protocol)

    try:
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    # Gather discovered devices
    devices = await asyncio.gather(*protocol.tasks) if protocol.tasks else []
    devices = list(filter(None, devices))

    return devices


Discover.discover = classmethod(_patched_discover)

# ─── MCP Server ───────────────────────────────────────────────────────────

mcp = FastMCP(
    name="Midea AC Controller",
    instructions="控制美的（及同生态品牌）智能空调。支持扫描发现设备、查看状态、开关机、调温、调模式、调风速。",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
)

# Global: cached device reference
_device: Optional[AirConditioner] = None


async def _get_device(ip: Optional[str] = None) -> AirConditioner:
    """Get or discover the Midea AC device."""
    global _device

    if _device is not None:
        return _device

    if ip:
        dev = await Discover.discover_single(ip, discovery_packets=2)
        if dev is None:
            raise Exception(f"无法在 {ip} 发现美的设备，请确认 IP 地址和网络连接。")
        _device = dev if isinstance(dev, AirConditioner) else None
        if _device is None:
            raise Exception(f"在 {ip} 发现的设备不是空调。")
        return _device

    # Auto-discover
    _LOGGER.info("Scanning for Midea devices...")
    devices = await Discover.discover(discovery_packets=2)
    acs = [d for d in devices if isinstance(d, AirConditioner)]

    if not acs:
        raise Exception("未在局域网发现美的空调。请确认空调已通电并连接网络，或指定 IP 地址重试。")

    _device = acs[0]
    _LOGGER.info(f"Found AC at {_device.ip}")
    return _device


# ─── Mode name mapping ────────────────────────────────────────────────────

MODE_NAMES = {
    AirConditioner.OperationalMode.AUTO: "自动",
    AirConditioner.OperationalMode.COOL: "制冷",
    AirConditioner.OperationalMode.DRY: "除湿",
    AirConditioner.OperationalMode.HEAT: "制热",
    AirConditioner.OperationalMode.FAN_ONLY: "送风",
}

FAN_NAMES = {
    AirConditioner.FanSpeed.AUTO: "自动",
    AirConditioner.FanSpeed.SILENT: "静音",
    AirConditioner.FanSpeed.LOW: "低风",
    AirConditioner.FanSpeed.MEDIUM: "中风",
    AirConditioner.FanSpeed.HIGH: "高风",
    AirConditioner.FanSpeed.MAX: "强力",
}


# ─── Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def discover_devices() -> str:
    """扫描局域网，发现美的空调设备。返回发现的设备列表。"""
    try:
        devices = await Discover.discover(discovery_packets=3)
        acs = [d for d in devices if isinstance(d, AirConditioner)]

        if not acs:
            global _device
            _device = None
            return "未在局域网发现美的空调设备。\n请确认：\n1. 空调已通电\n2. 空调已连接 WiFi\n3. 手机和空调在同一个网络"

        result = f"发现 {len(acs)} 台美的空调：\n\n"
        for i, ac in enumerate(acs, 1):
            try:
                await ac.refresh()
            except Exception:
                pass
            mode_name = MODE_NAMES.get(ac.operational_mode, str(ac.operational_mode.name))
            fan_name = FAN_NAMES.get(ac.fan_speed, str(ac.fan_speed))
            indoor = f"{ac.indoor_temperature}°C" if ac.indoor_temperature else "N/A"
            result += (
                f"【{i}】IP: {ac.ip}\n"
                f"  状态: {'🟢 开机' if ac.power_state else '⚫ 关机'}\n"
                f"  模式: {mode_name}\n"
                f"  目标温度: {ac.target_temperature}°C\n"
                f"  室内温度: {indoor}\n"
                f"  风速: {fan_name}\n\n"
            )

        _device = acs[0]
        return result

    except Exception as e:
        return f"扫描失败：{e}"


@mcp.tool()
async def get_status(ip: Optional[str] = None) -> str:
    """获取美的空调的当前状态（开关、温度、模式、风速等）。

    Args:
        ip: 空调 IP 地址（可选，不传则自动发现）
    """
    try:
        ac = await _get_device(ip)
        try:
            await ac.refresh()
        except Exception:
            pass

        mode_name = MODE_NAMES.get(ac.operational_mode, str(ac.operational_mode.name))
        fan_name = FAN_NAMES.get(ac.fan_speed, str(ac.fan_speed))
        indoor = f"{ac.indoor_temperature}°C" if ac.indoor_temperature else "N/A"
        outdoor = f"{ac.outdoor_temperature}°C" if ac.outdoor_temperature else "N/A"

        return (
            f"📊 美的空调状态\n"
            f"{'─' * 25}\n"
            f"IP 地址: {ac.ip}\n"
            f"运行状态: {'🟢 运行中' if ac.power_state else '⚫ 已关机'}\n"
            f"运行模式: {mode_name}\n"
            f"目标温度: {ac.target_temperature}°C\n"
            f"室内温度: {indoor}\n"
            f"室外温度: {outdoor}\n"
            f"风速: {fan_name}\n"
            f"支持模式: {', '.join(MODE_NAMES.get(m, str(m.name)) for m in ac.supported_operation_modes)}\n"
            f"温度范围: {ac.min_target_temperature}°C ~ {ac.max_target_temperature}°C"
        )
    except Exception as e:
        return f"获取状态失败：{e}"


@mcp.tool()
async def set_power(state: bool, ip: Optional[str] = None) -> str:
    """开关美的空调。

    Args:
        state: True=开机, False=关机
        ip: 空调 IP 地址（可选）
    """
    try:
        ac = await _get_device(ip)
        ac.power_state = state
        await ac.apply()
        return f"✅ 空调已{'开机' if state else '关机'}"
    except Exception as e:
        return f"操作失败：{e}"


@mcp.tool()
async def set_temperature(temperature: float, ip: Optional[str] = None) -> str:
    """设置美的空调目标温度。

    Args:
        temperature: 目标温度 (°C)，通常在 16-31°C 之间
        ip: 空调 IP 地址（可选）
    """
    try:
        ac = await _get_device(ip)
        if temperature < ac.min_target_temperature or temperature > ac.max_target_temperature:
            return f"温度超出范围（{ac.min_target_temperature}°C ~ {ac.max_target_temperature}°C）"

        ac.target_temperature = temperature
        if not ac.power_state:
            ac.power_state = True
        await ac.apply()
        return f"✅ 目标温度已设为 {temperature}°C"
    except Exception as e:
        return f"操作失败：{e}"


@mcp.tool()
async def set_mode(mode: str, ip: Optional[str] = None) -> str:
    """设置美的空调运行模式。

    Args:
        mode: 运行模式，可选：制冷 / 制热 / 除湿 / 送风 / 自动
        ip: 空调 IP 地址（可选）
    """
    mode_map = {
        "自动": AirConditioner.OperationalMode.AUTO,
        "制冷": AirConditioner.OperationalMode.COOL,
        "制热": AirConditioner.OperationalMode.HEAT,
        "除湿": AirConditioner.OperationalMode.DRY,
        "送风": AirConditioner.OperationalMode.FAN_ONLY,
    }

    if mode not in mode_map:
        return f"不支持的运行模式：{mode}，可选：{' / '.join(mode_map.keys())}"

    try:
        ac = await _get_device(ip)
        ac.operational_mode = mode_map[mode]
        if not ac.power_state:
            ac.power_state = True
        await ac.apply()
        return f"✅ 运行模式已设为「{mode}」"
    except Exception as e:
        return f"操作失败：{e}"


@mcp.tool()
async def set_fan_speed(speed: str, ip: Optional[str] = None) -> str:
    """设置美的空调风速。

    Args:
        speed: 风速档位，可选：自动 / 静音 / 低风 / 中风 / 高风 / 强力
        ip: 空调 IP 地址（可选）
    """
    fan_map = {
        "自动": AirConditioner.FanSpeed.AUTO,
        "静音": AirConditioner.FanSpeed.SILENT,
        "低风": AirConditioner.FanSpeed.LOW,
        "中风": AirConditioner.FanSpeed.MEDIUM,
        "高风": AirConditioner.FanSpeed.HIGH,
        "强力": AirConditioner.FanSpeed.MAX,
    }

    if speed not in fan_map:
        return f"不支持的风速：{speed}，可选：{' / '.join(fan_map.keys())}"

    try:
        ac = await _get_device(ip)
        ac.fan_speed = fan_map[speed]
        if not ac.power_state:
            ac.power_state = True
        await ac.apply()
        return f"✅ 风速已设为「{speed}」"
    except Exception as e:
        return f"操作失败：{e}"


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Midea AC MCP Server")
    parser.add_argument("--scan", action="store_true", help="扫描局域网发现美的空调设备")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP 传输协议 (默认 stdio, streamable-http 用于 Docker/远程访问)",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="HTTP 监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 监听端口 (默认 8000)")

    args = parser.parse_args()

    if args.scan:
        async def scan_only():
            result = await discover_devices()
            print(result)
        asyncio.run(scan_only())
        return

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
