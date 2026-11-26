import argparse
import json
from pathlib import Path

from contexts.teaching_assistant.domain.chunks import chunk_markdown_file


def main() -> None:
    parser = argparse.ArgumentParser(description="读 data/docs/*.md 切片并写 JSONL")
    parser.add_argument(
        "--input",
        default="contexts/teaching_assistant/data/docs",
        help="md 文档目录",
    )
    parser.add_argument(
        "--output",
        default="contexts/teaching_assistant/data/chunks.jsonl",
        help="输出 JSONL 路径",
    )
    args = parser.parse_args()

    in_dir = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8") as f:
        for path in sorted(in_dir.glob("*.md")):
            document_name = path.stem
            content = path.read_text(encoding="utf-8")
            for record in chunk_markdown_file(document_name, content):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    print(f"wrote {count} chunks to {out_path}")


if __name__ == "__main__":
    main()
