"""Sparkplug B session state: alias tables and sequence tracking.

State is held per edge node, with a nested table per device. Aliases are
resolved from the BIRTH that introduced them, so a DATA message carrying only
aliases can be turned back into named metrics. The `seq` counter is per edge
node (it spans the node's own messages and all its devices' messages), so gap
detection lives at the edge-node level, not the device level.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricDef:
    name: str
    datatype: int


@dataclass
class DeviceState:
    alive: bool = False
    aliases: dict[int, MetricDef] = field(default_factory=dict)


@dataclass
class EdgeNodeState:
    alive: bool = False
    bd_seq: int | None = None
    last_seq: int | None = None
    aliases: dict[int, MetricDef] = field(default_factory=dict)
    devices: dict[str, DeviceState] = field(default_factory=dict)


class SparkplugState:
    def __init__(self) -> None:
        self._nodes: dict[tuple[str, str], EdgeNodeState] = {}

    def _node(self, group: str, edge_node: str) -> EdgeNodeState:
        return self._nodes.setdefault((group, edge_node), EdgeNodeState())

    def node_birth(
        self, group: str, edge_node: str, defs: dict[int, MetricDef], bd_seq: int | None
    ) -> None:
        node = self._node(group, edge_node)
        node.alive = True
        node.bd_seq = bd_seq
        node.last_seq = 0  # NBIRTH carries seq 0 and resets the counter.
        node.aliases = dict(defs)
        node.devices.clear()  # A node rebirth invalidates prior device state.

    def device_birth(
        self, group: str, edge_node: str, device: str, defs: dict[int, MetricDef]
    ) -> None:
        node = self._node(group, edge_node)
        node.devices[device] = DeviceState(alive=True, aliases=dict(defs))

    def device_death(self, group: str, edge_node: str, device: str) -> None:
        node = self._node(group, edge_node)
        if device in node.devices:
            node.devices[device].alive = False

    def node_death(self, group: str, edge_node: str) -> None:
        node = self._node(group, edge_node)
        node.alive = False
        for dev in node.devices.values():
            dev.alive = False

    def check_seq(self, group: str, edge_node: str, seq: int) -> bool:
        """Return True if `seq` is out of order (a gap). Wrap-aware (0-255)."""
        node = self._node(group, edge_node)
        gap = False
        if node.last_seq is not None:
            expected = (node.last_seq + 1) % 256
            if seq != expected:
                gap = True
        node.last_seq = seq
        return gap

    def resolve(
        self, group: str, edge_node: str, device: str | None, alias: int
    ) -> MetricDef | None:
        node = self._node(group, edge_node)
        if device is None:
            return node.aliases.get(alias)
        dev = node.devices.get(device)
        return dev.aliases.get(alias) if dev else None
