import httpx

from filing_analyst.model_digests import UNKNOWN_DIGEST, read_model_digests


TAGS = {
    "models": [
        {"name": "qwen3.5:9B", "model": "qwen3.5:9B", "digest": "6488c96fa5fa" + "0" * 52},
        {"name": "gemma4:e2b", "model": "gemma4:e2b", "digest": "7fbdbf8f5e45" + "1" * 52},
    ]
}


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, base_url="http://ollama:11434")


def test_each_model_gets_the_short_digest_ollama_list_shows() -> None:
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, json=TAGS)

    with _client(httpx.MockTransport(respond)) as client:
        digests = read_model_digests(client, ["qwen3.5:9B", "gemma4:e2b"])
    assert digests == {"qwen3.5:9B": "6488c96fa5fa", "gemma4:e2b": "7fbdbf8f5e45"}
    assert requested == ["/api/tags"]


def test_a_model_ollama_does_not_have_reads_unknown() -> None:
    with _client(httpx.MockTransport(lambda _r: httpx.Response(200, json=TAGS))) as client:
        digests = read_model_digests(client, ["llama9:1b"])
    assert digests == {"llama9:1b": UNKNOWN_DIGEST}


def test_ollama_down_reads_unknown_for_every_model() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with _client(httpx.MockTransport(refuse)) as client:
        digests = read_model_digests(client, ["qwen3.5:9B", "gemma4:e2b"])
    assert digests == {"qwen3.5:9B": UNKNOWN_DIGEST, "gemma4:e2b": UNKNOWN_DIGEST}


def test_an_error_status_reads_unknown() -> None:
    with _client(httpx.MockTransport(lambda _r: httpx.Response(500))) as client:
        digests = read_model_digests(client, ["qwen3.5:9B"])
    assert digests == {"qwen3.5:9B": UNKNOWN_DIGEST}
