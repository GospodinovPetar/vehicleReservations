def _merge_intervals(intervals):
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            if e > last_e:
                merged[-1] = (last_s, e)
        else:
            merged.append((s, e))
    return merged


def _free_slices(request_start, request_end, busy_intervals):
    if request_end <= request_start:
        return []
    busy = []
    for s, e in busy_intervals:
        s2 = max(request_start, s)
        e2 = min(request_end, e)
        if s2 < e2:
            busy.append((s2, e2))
    busy = _merge_intervals(busy)
    slices = []
    cursor = request_start
    for s, e in busy:
        if cursor < s:
            slices.append((cursor, s))
        if e > cursor:
            cursor = e
    if cursor < request_end:
        slices.append((cursor, request_end))
    return slices