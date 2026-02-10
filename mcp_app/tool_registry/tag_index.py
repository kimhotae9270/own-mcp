# tag_index.py
from .registry import get_all_tools
import re
_tag_index: dict[str, list] = None

TAG_PATTERN = re.compile(r"\[TAG:(.*?)\]", re.IGNORECASE)


def extract_tags(tool) -> list[str]:
    desc = tool.description or ""
    return [tag.lower().strip() for tag in TAG_PATTERN.findall(desc)]


async def build_tag_index():
    global _tag_index

    if _tag_index is not None:
        return _tag_index

    tools = await get_all_tools()

    index = {}

    for tool in tools:
        tags = extract_tags(tool)

        if not tags:
            # 선택: 로그 남기기
            # logger.warning(f"{tool.name} has no TAG")
            continue

        for tag in tags:
            index.setdefault(tag, []).append(tool)

    _tag_index = index
    return index
