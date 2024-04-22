from __future__ import annotations

import re
from collections.abc import Iterable


class ChannelSorter:
    def __init__(self, platform: str, channels: Iterable[str] | None = None) -> None:
        self._priority: dict[str, int] = {}
        self._tree: dict[str, list[str]] = {}
        self.platform = platform
        if channels:
            for channel in channels:
                self.add_channel(channel)
            for root in self._tree:
                self.add_defaults(root)

    def get_root(self, channel: str) -> str:
        return channel.split("/")[0]

    def add_defaults(self, root: str):
        for channel in [f"{root}/{self.platform}", rf"{root}/.*", f"{root}/noarch"]:
            self.add_channel(channel, allow_fuzzy=not channel.endswith("noarch"))

    def get_variants(self, root: str):
        # add parent channel priority
        if root not in self._tree:
            self._priority[root] = 1000 * len(self._tree)
            self._tree[root] = []

        return self._tree[root]

    def add_channel(self, channel: str, allow_fuzzy=True):
        root = self.get_root(channel)
        if channel not in self._priority:
            for c in (variants := self.get_variants(root)):
                if c == channel or (allow_fuzzy and re.match(c, channel)):
                    self._priority[channel] = self._priority[c]
                    # then fuzzy match
                    if c != channel:
                        self._priority[c] += 1
                    break
            # couldn't find priority in saved variant
            if channel not in self._priority:
                self._priority[channel] = self._priority[root] + len(variants) * 10
                variants.append(channel)

    def get_priority(self, channel: str) -> int:
        self.add_channel(channel)
        return self._priority[channel]
