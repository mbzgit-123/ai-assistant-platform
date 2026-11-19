def merge_counts(counts: list[int], cap: int = 30, floor: int = 3) -> list[int]:
    """多视频合并：总题量超 cap 按比例缩减，每视频保底 floor。

    当视频数过多（n * floor > cap）时保底退化为 cap // n，保证 sum(结果) ≤ cap。
    """
    total = sum(counts)
    if total <= cap:
        return list(counts)
    n = len(counts)
    if n * floor > cap:
        floor = cap // n
    scaled = [max(floor, c * cap // total) for c in counts]
    # 保底向上取整可能导致 sum 仍超过 cap：反复削减「最大且 > floor」的元素
    while sum(scaled) > cap:
        idx = max(range(len(scaled)), key=lambda i: scaled[i])
        if scaled[idx] <= floor:
            break
        scaled[idx] -= 1
    return scaled
