from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List, Tuple, Union

DateLike = Union[date, datetime]
Interval = Tuple[DateLike, DateLike]


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    """
    Merge an iterable of (start, end) intervals into a minimal set of disjoint intervals.

    Intervals are assumed to be half-open or open/closed consistently relative to
    your domain. Two intervals overlap if the next start is <= the current end;
    in that case they are merged by extending the end to the max of both ends.

    Args:
        intervals: Iterable of (start, end) tuples using either `date` or `datetime`.

    Returns:
        list[Interval]: Sorted, merged intervals covering all input ranges.

    Example:
        >>> merge_intervals([(1, 3), (2, 5), (7, 8)])
        [(1, 5), (7, 8)]
    """
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
    """
    Compute free intervals within a requested window, excluding busy intervals.

    The function clamps busy intervals to the [request_start, request_end) window,
    merges any overlaps, and returns the gaps between them. If the request window
    is invalid (missing or end <= start), an empty list is returned.

    Args:
        request_start: Inclusive start of the requested window (date or datetime).
        request_end: Exclusive end of the requested window (date or datetime).
        busy_intervals: Iterable of (start, end) tuples representing busy ranges.

    Returns:
        list[Interval]: Sorted list of free (start, end) intervals within the window.

    Example:
        >>> free_slices(1, 10, [(2, 3), (5, 7)])
        [(1, 2), (3, 5), (7, 10)]
    """
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
