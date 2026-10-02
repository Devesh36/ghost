"""Transport boundary tests: no API key, paid calls, or external network."""
import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from core.llm.openai_compatible import OpenAICompatibleProvider, ProviderError, ProviderLimits


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay = chunks, delay
        self.closed = False
        self.reads = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.closed = True


def completion(content='{"revisions": []}', **kwargs):
    return json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop", **kwargs}]}).encode()


def setup(monkeypatch, stream, status=200, headers=None, **limits):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status, headers=headers, stream=stream)
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(handle), **kw))
    provider = OpenAICompatibleProvider("private-api-key", "https://provider.invalid/v1", "test-model",
                                        limits=ProviderLimits(**limits))
    return provider, requests


def test_valid_completion_and_fenced_tool_json(monkeypatch):
    stream = Chunks([completion('```json\n{"revisions": []}\n```')])
    provider, requests = setup(monkeypatch, stream)
    assert asyncio.run(provider.tool_call("system", "prompt", {})) == {"revisions": []}
    assert stream.closed
    assert requests[0].headers['accept-encoding'] == 'identity'
    assert json.loads(requests[0].content)['model'] == 'test-model'


def test_request_limit_counts_encoded_bytes_before_network(monkeypatch):
    provider, requests = setup(monkeypatch, Chunks([]), request_bytes=1024)
    with pytest.raises(ProviderError, match="request exceeds"):
        asyncio.run(provider.generate("", "👻" * 300))
    assert requests == []


@pytest.mark.parametrize("headers,chunks,reads", [
    ({'content-length': '10000000'}, [b'x'], 0),
    ({}, [b'x' * 700, b'x' * 700, b'never consumed'], 2),
    ({'content-encoding': 'gzip'}, [b'compressed input'], 0),
    ({'content-length': 'invalid'}, [b'x'], 0),
])
def test_response_limits_close_stream(monkeypatch, headers, chunks, reads):
    stream = Chunks(chunks)
    provider, _ = setup(monkeypatch, stream, headers=headers, response_bytes=1024)
    with pytest.raises(ProviderError):
        asyncio.run(provider.generate("", ""))
    assert stream.closed and stream.reads == reads


@pytest.mark.parametrize("body", [
    b'private-response-not-json', b'[]', b'{"choices": []}',
    completion("private text", finish_reason="length"), completion(None), completion(""),
    completion("{}", finish_reason="content_filter"), b'{"choices": NaN}',
    b'[' * 2000 + b']' * 2000,
])
def test_invalid_completions_do_not_echo_payload(monkeypatch, body):
    provider, _ = setup(monkeypatch, Chunks([body]))
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.generate("secret prompt", ""))
    assert "private" not in str(error.value) and "secret" not in str(error.value)


@pytest.mark.parametrize("content", ['[]', 'null', '{"value": Infinity}', 'secret-invalid-json'])
def test_tool_response_must_be_valid_object(monkeypatch, content):
    provider, _ = setup(monkeypatch, Chunks([completion(content)]))
    with pytest.raises(ProviderError):
        asyncio.run(provider.tool_call("", "", {}))


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_http_errors_never_read_or_expose_body(monkeypatch, status):
    stream = Chunks([b'private-api-key private-response'])
    provider, requests = setup(monkeypatch, stream, status=status, headers={'location': 'https://other.invalid'})
    with pytest.raises(ProviderError, match=f"HTTP {status}") as error:
        asyncio.run(provider.generate("secret prompt", ""))
    assert "private" not in str(error.value)
    assert stream.closed and stream.reads == 0 and len(requests) == 1


def test_slow_drip_hits_total_deadline_and_closes(monkeypatch):
    stream = Chunks([b' '] * 100, delay=0.01)
    provider, _ = setup(monkeypatch, stream, request_timeout=0.06)
    with pytest.raises(ProviderError, match="deadline"):
        asyncio.run(provider.generate("", ""))
    assert stream.closed and 0 < stream.reads < 100


def test_cancellation_propagates_and_closes_response(monkeypatch):
    stream = Chunks([b' '] * 100, delay=0.01)
    provider, _ = setup(monkeypatch, stream)
    async def scenario():
        task = asyncio.create_task(provider.generate("", ""))
        while not stream.reads:
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert stream.closed


@pytest.mark.parametrize("value", [0, -1, float('nan'), float('inf')])
def test_invalid_deadlines_rejected(value):
    with pytest.raises(ValidationError):
        ProviderLimits(request_timeout=value)


def test_transport_errors_hide_endpoint_and_credentials(monkeypatch):
    def fail(request):
        raise httpx.ConnectError('private-api-key https://private-host.invalid', request=request)
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: client(transport=httpx.MockTransport(fail), **kw))
    provider = OpenAICompatibleProvider('key', 'https://private-host.invalid', 'model')
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.generate('', ''))
    assert str(error.value) == 'Model request failed during HTTP transport.'


def test_real_http_slow_response_deadline(monkeypatch):
    """Exercise HTTPX over an actual local socket, not only a mock stream."""
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    async def scenario():
        disconnected = asyncio.Event()
        async def serve(reader, writer):
            try:
                header = await reader.readuntil(b'\r\n\r\n')
                length = next(int(line.split(b':', 1)[1]) for line in header.split(b'\r\n')
                              if line.lower().startswith(b'content-length:'))
                await reader.readexactly(length)
                writer.write(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n')
                await writer.drain()
                for _ in range(100):
                    writer.write(b'1\r\n \r\n')
                    await writer.drain()
                    await asyncio.sleep(0.02)
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
                disconnected.set()
        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        async with server:
            provider = OpenAICompatibleProvider('test', f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}',
                                                'test', limits=ProviderLimits(request_timeout=0.3))
            started = asyncio.get_running_loop().time()
            with pytest.raises(ProviderError, match='deadline'):
                await provider.generate('', '')
            assert asyncio.get_running_loop().time() - started < 1.5
            await asyncio.wait_for(disconnected.wait(), 2)
    asyncio.run(scenario())


def test_incomplete_provider_patch_never_reaches_working_tree(tmp_path, monkeypatch):
    import io
    import shlex
    import sys
    from rich.console import Console
    from core.agent_harness.orchestrator import debug
    from infrastructure.collectors.commands import recorded_run
    from surfaces.cli.commands.demo import create_demo
    from infrastructure.database.repository import Database
    from core.domain.types import Session
    from infrastructure.safety.sandbox.worktree import source_signature
    from infrastructure.repository.git import git

    repo = create_demo(tmp_path / 'project')
    target = repo / 'pricing.py'
    target.write_text('# preserve this unrelated header\n\n' + target.read_text())
    db = Database(repo)
    session = Session(repository_path=str(repo), starting_commit=git(repo, 'rev-parse', 'HEAD').strip(), branch='main')
    db.start(session)
    recorded_run(db, session.id, repo, shlex.join([sys.executable, '-B', '-m', 'unittest', '-q']), stream=False)
    before = source_signature(repo)
    # Even valid-looking JSON is rejected if the provider says it was truncated.
    stream = Chunks([completion('{"edits": []}', finish_reason='length')])
    provider, requests = setup(monkeypatch, stream)
    result = asyncio.run(debug(repo, db, session.id, provider, Console(file=io.StringIO()), apply=True))
    assert result.status == 'completed' and result.confidence == 'HIGH'
    assert len(requests) == 2  # Hypothesis refinement and the nontrivial patch proposal.
    assert not result.patch and not result.verification and not result.applied
    assert any('Patch proposal failed' in note for note in result.notes)
    assert source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
    assert 'private-api-key' not in db.latest_investigation(session.id).model_dump_json()
