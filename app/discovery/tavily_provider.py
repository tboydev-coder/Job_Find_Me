import os
import asyncio

from dotenv import load_dotenv
from tavily import TavilyClient

from .search import SearchProvider, SearchResult

load_dotenv()


class TavilySearchProvider(SearchProvider):

    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")

        if not api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set"
            )

        self.client = TavilyClient(
            api_key=api_key
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:

        response = await asyncio.to_thread(
            self.client.search,
            query=query,
            max_results=limit,
            search_depth="basic",
        )

        results = []

        if not isinstance(response, dict):
            return results

        for item in response.get(
            "results",
            []
        ):

            if not isinstance(item, dict) or not item.get("url"):
                continue

            results.append(
                SearchResult(
                    title=item.get(
                        "title",
                        "",
                    ),
                    url=item.get(
                        "url",
                        "",
                    ),
                    snippet=item.get(
                        "content",
                    ),
                )
            )

        return results
