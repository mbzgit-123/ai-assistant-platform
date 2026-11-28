from contexts.self_practice.domain.fusion import fuse_summaries


def test_fuse_summaries_joins_with_titles_and_blank_lines():
    items = [
        ("视频一", "要点A"),
        ("视频二", "要点B"),
    ]
    assert fuse_summaries(items) == "## 视频一\n要点A\n\n## 视频二\n要点B"


def test_fuse_summaries_skips_empty_summaries():
    items = [
        ("视频一", "要点A"),
        ("视频二", "   "),
        ("视频三", ""),
        ("视频四", "要点B"),
    ]
    assert fuse_summaries(items) == "## 视频一\n要点A\n\n## 视频四\n要点B"


def test_fuse_summaries_strips_whitespace():
    items = [("视频一", "  要点A  ")]
    assert fuse_summaries(items) == "## 视频一\n要点A"


def test_fuse_summaries_without_title_uses_summary_only():
    items = [("", "要点A"), ("  ", "要点B")]
    assert fuse_summaries(items) == "要点A\n\n要点B"


def test_fuse_summaries_all_empty_returns_empty_string():
    assert fuse_summaries([("视频一", ""), ("视频二", "  ")]) == ""
