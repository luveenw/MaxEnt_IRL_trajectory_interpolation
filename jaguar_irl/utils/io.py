# -*- coding: utf-8 -*-
"""
Utility functions for jaguar_irl.

Ported from util.py (Hirakawa et al. 2018) with Python 3 fixes
(map() returns iterator in Python 3).
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def read_text(filename: str) -> list[str]:
    """Read a text file and return stripped lines."""
    with open(filename, "r") as f:
        lines = [line.strip() for line in f.readlines()]
    return lines


def chunk_list(input_list: list[T], n: int) -> list[list[T]]:
    """Split a list into chunks of size n."""
    return [input_list[x:x + n] for x in range(0, len(input_list), n)]
