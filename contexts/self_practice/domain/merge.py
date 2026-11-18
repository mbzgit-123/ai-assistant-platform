def merge_counts(counts: list[int], cap: int = 30, floor: int = 3) -> list[int]:
    """多视频合并：总题量超 cap 按比例缩减，每视频保底 floor。"""
    total = sum(counts)
    if total <= cap:
        return list(counts)
    scaled = [max(floor, c * cap // total) for c in counts]
    # 保底向上取整可能导致 sum 仍超过 cap：反复削减「最大且 > floor」的元素
    while sum(scaled) > cap:
        idx = max(range(len(scaled)), key=lambda i: scaled[i])
        if scaled[idx] <= floor:
            break
        scaled[idx] -= 1
    return scaled
