"""Line-based fence scanner: tracks fence length so a nested ``` inside a
````-fenced block does not terminate it. The naive regex ```x\n(.*?)``` silently
truncates any template that contains a code fence of its own."""
import re

def blocks(text, lang=None):
    out, cur, fence, cur_lang = [], None, None, None
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(`{3,})([A-Za-z0-9_-]*)\s*$", line)
        if cur is None and m:
            fence, cur_lang, cur = m.group(1), m.group(2), []
        elif cur is not None and m and len(m.group(1)) >= len(fence) and not m.group(2):
            if lang is None or cur_lang == lang:
                out.append(("".join(cur), fence, cur_lang))
            cur = fence = cur_lang = None
        elif cur is not None:
            cur.append(line)
    return out
