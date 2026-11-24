from contexts.exam_paper_generation.domain.clean import clean_markdown


def test_clean_markdown_converts_bullet_symbols():
    text = "○ 机器学习\n● 深度学习\n▪ 神经网络"
    assert clean_markdown(text) == "- 机器学习\n- 深度学习\n- 神经网络"


def test_clean_markdown_removes_trailing_arrow():
    result = clean_markdown("1.  金融风控行业（信贷风控）---->")
    assert "---->" not in result
    assert "金融风控行业（信贷风控）" in result


def test_clean_markdown_removes_arrow_symbol():
    assert clean_markdown("看左边 → 看右边") == "看左边 看右边"


def test_clean_markdown_removes_misplaced_blockquote():
    assert clean_markdown("    >    是这种格式") == "是这种格式"


def test_clean_markdown_normalizes_list_number_spacing():
    assert clean_markdown("1.  金融风控") == "1. 金融风控"


def test_clean_markdown_collapses_multiple_blank_lines():
    result = clean_markdown("段落一\n\n\n\n段落二")
    assert result == "段落一\n\n段落二"


def test_clean_markdown_preserves_code_block():
    text = "说明\n```python\nif a > b:\n    print(a)\n```"
    result = clean_markdown(text)
    assert "```python" in result
    assert "if a > b:" in result
    assert "print(a)" in result


def test_clean_markdown_keeps_real_heading_and_bold():
    text = "# 标题\n**加粗**内容"
    result = clean_markdown(text)
    assert result == "# 标题\n**加粗**内容"
