import asyncio
from dotenv import load_dotenv

from .tavily_provider import (
    TavilySearchProvider,
)


async def main():

    load_dotenv()

    provider = TavilySearchProvider()

    results = await provider.search(
        '"Python Developer" Lagos jobs',
        limit=5,
    )

    for result in results:

        print("\nTITLE:")
        print(result.title)

        print("\nURL:")
        print(result.url)

        print("\nSNIPPET:")
        print(result.snippet)

        print("\n" + "-" * 60)


if __name__ == "__main__":
    asyncio.run(main())