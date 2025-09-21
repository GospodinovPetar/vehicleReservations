def merge_intervals(intervals):
    intervals = list(intervals)
    if len(intervals) == 0:
        return []

    intervals.sort(key=lambda pair: pair[0])

    merged = []
    current_start, current_end = intervals[0]

    for i in range(1, len(intervals)):
        start, end = intervals[i]

        if start <= current_end:
            if end > current_end:
                current_end = end
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end

    merged.append((current_start, current_end))
    return merged


def free_slices(request_start, request_end, busy_intervals):
    if request_end <= request_start:
        return []

    clamped_busy = []
    for start, end in busy_intervals:
        if end <= request_start or start >= request_end:
            continue

        s = start if start > request_start else request_start
        e = end if end < request_end else request_end

        if s < e:
            clamped_busy.append((s, e))

    merged_busy = merge_intervals(clamped_busy)

    free = []
    cursor = request_start

    for start, end in merged_busy:
        if cursor < start:
            free.append((cursor, start))
        if end > cursor:
            cursor = end

    if cursor < request_end:
        free.append((cursor, request_end))

    return free
