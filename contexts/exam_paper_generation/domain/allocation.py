def allocate_types(total: int, has_code: bool) -> dict[str, int]:
    """按「三必出题型各≥1 + 代码填空约 30%（封顶 4）」确定性分配题型数量。

    返回 {"multi_choice", "short_answer", "scenario", "code_fill"} 四项，和为 total。
    """
    code_fill = 0
    if has_code and total >= 4:
        code_fill = min(4, total * 30 // 100) or 1
        code_fill = min(code_fill, total - 3)  # 给三必出题型留位
    rest = total - code_fill
    extra = rest - 3
    multi_choice = 1 + extra * 4 // 9
    short_answer = 1 + extra * 3 // 9
    scenario = rest - multi_choice - short_answer
    return {
        "multi_choice": multi_choice,
        "short_answer": short_answer,
        "scenario": scenario,
        "code_fill": code_fill,
    }
