"""Bulk-loaded B+ tree for ordered composite-key range scans."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Generic, TypeVar

Key = TypeVar("Key")
Value = TypeVar("Value")


@dataclass
class _Node(Generic[Key, Value]):
    keys: list[Key]
    children: list[_Node[Key, Value]] = field(default_factory=list)
    values: list[Value] = field(default_factory=list)
    next_leaf: _Node[Key, Value] | None = None

    @property
    def is_leaf(self) -> bool:
        return not self.children


class BPlusTree(Generic[Key, Value]):
    """A read-optimized B+ tree built from sorted data.

    Interior nodes direct a seek; linked leaves make a range scan linear only in matching entries.
    The index is rebuilt when its source table is refreshed, matching the immutable nightly window.
    """

    def __init__(self, items: Iterable[tuple[Key, Value]], leaf_size: int = 128, fanout: int = 64):
        if leaf_size < 2 or fanout < 2:
            raise ValueError("leaf_size and fanout must be at least 2")
        ordered = sorted(items, key=lambda item: item[0])
        self.size = len(ordered)
        self.leaf_size = leaf_size
        self.fanout = fanout
        self.root: _Node[Key, Value] | None = self._build(ordered)

    def _build(self, items: list[tuple[Key, Value]]) -> _Node[Key, Value] | None:
        if not items:
            return None
        leaves: list[_Node[Key, Value]] = []
        for start in range(0, len(items), self.leaf_size):
            page = items[start : start + self.leaf_size]
            leaves.append(_Node(keys=[key for key, _ in page], values=[value for _, value in page]))
        for left, right in pairwise(leaves):
            left.next_leaf = right
        level = leaves
        while len(level) > 1:
            parent_level: list[_Node[Key, Value]] = []
            for start in range(0, len(level), self.fanout):
                children = level[start : start + self.fanout]
                # Separators are the first key of every child after the first.
                parent_level.append(_Node(keys=[child.keys[0] for child in children[1:]], children=children))
            level = parent_level
        return level[0]

    def _leaf_for(self, key: Key) -> _Node[Key, Value] | None:
        node = self.root
        while node is not None and not node.is_leaf:
            node = node.children[bisect_right(node.keys, key)]
        return node

    def _leftmost_leaf(self) -> _Node[Key, Value] | None:
        node = self.root
        while node is not None and not node.is_leaf:
            node = node.children[0]
        return node

    def range(self, start: Key | None = None, end: Key | None = None) -> list[Value]:
        """Return values with inclusive start/end bounds."""
        if self.root is None:
            return []
        leaf = self._leaf_for(start) if start is not None else self._leftmost_leaf()
        if leaf is None:
            return []
        result: list[Value] = []
        first = bisect_left(leaf.keys, start) if start is not None else 0
        while leaf is not None:
            for key, value in zip(leaf.keys[first:], leaf.values[first:]):
                if end is not None and key > end:
                    return result
                result.append(value)
            leaf, first = leaf.next_leaf, 0
        return result
