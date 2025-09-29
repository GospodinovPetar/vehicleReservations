from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List, Tuple, Union

DateLike = Union[date, datetime]
Interval = Tuple[DateLike, DateLike]


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    items = sorted(intervals, key=lambda p: p[0])
    if not items:
        return []

    merged: List[Interval] = []
    cur_start, cur_end = items[0]

    for nxt_start, nxt_end in items[1:]:
        if nxt_start <= cur_end:
            cur_end = max(cur_end, nxt_end)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = nxt_start, nxt_end

    merged.append((cur_start, cur_end))
    return merged


def free_slices(
    request_start: DateLike, request_end: DateLike, busy_intervals: Iterable[Interval]
) -> List[Interval]:
    if request_start is None or request_end is None:
        return []
    if request_end <= request_start:
        return []

    clamped: List[Interval] = []
    for s, e in busy_intervals:
        if e <= request_start or s >= request_end:
            continue
        clamped.append((max(s, request_start), min(e, request_end)))

    merged_busy = merge_intervals(clamped)

    free: List[Interval] = []
    cursor: DateLike = request_start

    for b_start, b_end in merged_busy:
        if cursor < b_start:
            free.append((cursor, b_start))
        cursor = max(cursor, b_end)

    if cursor < request_end:
        free.append((cursor, request_end))

    return free
