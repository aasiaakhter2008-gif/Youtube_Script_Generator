"""Example: generate a YouTube script and stream it."""

import asyncio

from youtube_script_generator import YouTubeScriptClient


async def main() -> None:
    client = YouTubeScriptClient(api_key="sk_yours_xxxxx", base_url="http://localhost:8000")

    job = await client.generate(topic="Why the sky is blue", duration_minutes=8)
    job_id = job["job_id"]

    async for event in client.stream_events(job_id):
        print(event)

    await client.get_script(job_id)
    content = await client.export(job_id, format="md")
    print(content.decode("utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
