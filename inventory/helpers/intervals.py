from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List, Sequence, Tuple, Union

DateLike = Union[date, datetime]
Interval = Tuple[DateLike, DateLike]


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    intervals_list: List[Interval] = list(intervals)
    if len(intervals_list) == 0:
        return []

    intervals_list.sort(key=lambda pair: pair[0])

    merged: List[Interval] = []
    current_start: DateLike
    current_end: DateLike
    current_start, current_end = intervals_list[0]

    for idx in range(1, len(intervals_list)):
        next_start, next_end = intervals_list[idx]
        if next_start <= current_end:
            if next_end > current_end:
                current_end = next_end
        else:
            merged.append((current_start, current_end))
            current_start = next_start
            current_end = next_end

    merged.append((current_start, current_end))
    return merged


def free_slices(
    request_start: DateLike, request_end: DateLike, busy_intervals: Iterable[Interval]
) -> List[Interval]:
    if request_start is None or request_end is None:
        return []
    if request_end <= request_start:
        return []

    clamped_busy: List[Interval] = []
    for start_value, end_value in busy_intervals:
        if end_value <= request_start or start_value >= request_end:
            continue
        s = start_value if start_value > request_start else request_start
        e = end_value if end_value < request_end else request_end
        if s < e:
            clamped_busy.append((s, e))

    merged_busy: List[Interval] = merge_intervals(clamped_busy)

    free_list: List[Interval] = []
    cursor: DateLike = request_start

    for busy_start, busy_end in merged_busy:
        if cursor < busy_start:
            free_list.append((cursor, busy_start))
        if busy_end > cursor:
            cursor = busy_end

    if cursor < request_end:
        free_list.append((cursor, request_end))

    return free_list
