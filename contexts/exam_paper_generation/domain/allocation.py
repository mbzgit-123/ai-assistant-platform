def allocate_types(total: int, has_code: bool) -> dict[str, int]:
    """按「三必出题型各≥1 + 代码题约 30%（封顶 4）」确定性分配题型数量。

    返回 {"choice", "short_answer", "scenario", "code"} 四项，和为 total。
    """
    code = 0
    if has_code and total >= 4:
        code = min(4, total * 30 // 100) or 1
        code = min(code, total - 3)  # 给三必出题型留位
    rest = total - code
    extra = rest - 3
    choice = 1 + extra * 4 // 9
    short_answer = 1 + extra * 3 // 9
    scenario = rest - choice - short_answer
    return {
        "choice": choice,
        "short_answer": short_answer,
        "scenario": scenario,
        "code": code,
    }
