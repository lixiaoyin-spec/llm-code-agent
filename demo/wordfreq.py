"""统计一段英文文本中每个单词出现的次数（忽略大小写与标点）。"""

import re


def count_words(text: str) -> dict[str, int]:
    words = re.findall(r"[A-Za-z]+", text)
    counts: dict[str, int] = {}
    for word in words:
        key = word.lower()
        counts[key] = counts.get(key, 0)
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    import sys

    sample = sys.stdin.read() if not sys.stdin.isatty() else "Hello, hello world!"
    print(count_words(sample))
