from datetime import date
from typing import List, Tuple

def _merge_intervals(intervals: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            merged[-1] = (last_s, max(last_e, e))
        else:
            merged.append((s, e))
    return merged

def _free_slices(request_start: date, request_end: date,
                 busy: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    if request_end <= request_start:
        return []
    busy = [(max(request_start, s), min(request_end, e)) for s, e in busy]
    busy = [(s, e) for s, e in busy if s < e]
    busy = _merge_intervals(busy)
    slices = []
    cursor = request_start
    for s, e in busy:
        if cursor < s:
            slices.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < request_end:
        slices.append((cursor, request_end))
    return slices