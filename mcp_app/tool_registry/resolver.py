from .tag_index import build_tag_index

async def get_tools_by_tags(tags: list[str]):

    index = await build_tag_index()

    unique_tools = {}

    for tag in tags:
        for tool in index.get(tag, []):
            unique_tools[tool.name] = tool

    return list(unique_tools.values())
