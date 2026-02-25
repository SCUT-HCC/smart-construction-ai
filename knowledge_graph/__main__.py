"""K22 入口 — python -m knowledge_graph"""

import asyncio

from knowledge_graph.builder import build_knowledge_graph

if __name__ == "__main__":
    asyncio.run(build_knowledge_graph())
