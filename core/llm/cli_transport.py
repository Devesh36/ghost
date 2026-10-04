"""Bounded CLI transport in an empty disposable directory, with process cleanup."""
import asyncio
import os
import signal
import tempfile

from core.llm.transport import ProviderError, ProviderLimits


async def run_cli(argv: list[str], payload: bytes, environment: dict[str, str],
                  limits: ProviderLimits, *, prefix: str, failure: str) -> bytes:
    if len(payload) > limits.request_bytes:
        raise ProviderError('Model request exceeds the configured byte limit.')
    process = None
    with tempfile.TemporaryDirectory(prefix=prefix) as workspace:
        try:
            async with asyncio.timeout(limits.request_timeout):
                process = await asyncio.create_subprocess_exec(
                    *argv, cwd=workspace, env=environment, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    start_new_session=True)

                async def read(stream):
                    body = bytearray()
                    while chunk := await stream.read(4096):
                        if len(body) + len(chunk) > limits.response_bytes:
                            raise ProviderError('Provider response exceeds the configured byte limit.')
                        body.extend(chunk)
                    return bytes(body)

                async def send():
                    process.stdin.write(payload)
                    await process.stdin.drain()
                    process.stdin.close()

                tasks = [asyncio.create_task(read(process.stdout)),
                         asyncio.create_task(read(process.stderr)), asyncio.create_task(send())]
                try:
                    stdout, _, _ = await asyncio.gather(*tasks)
                    code = await process.wait()
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            if code:
                raise ProviderError(failure)
        except TimeoutError:
            raise ProviderError('Model request exceeded its deadline.') from None
        except (OSError, ConnectionError):
            raise ProviderError(failure) from None
        finally:
            if process:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 2)
                except TimeoutError:
                    pass
    return stdout
