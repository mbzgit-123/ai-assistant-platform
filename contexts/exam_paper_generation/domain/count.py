def count_for_duration(duration_seconds: int) -> int:
    """按视频时长区间映射单视频默认题量（确定性取区间下限）。

    <5 分钟→3；5–15 分钟→5；15–30 分钟→8；>30 分钟→10（封顶 15 的区间下限）。
    """
    if duration_seconds < 300:
        return 3
    if duration_seconds < 900:
        return 5
    if duration_seconds < 1800:
        return 8
    return 10
