import json
import httpx
import pytest
from tenderready.config import Settings
from tenderready.nebius import IntegrationError, NemotronClient, SourceInput


SOURCE = SourceInput(source_id="s1", text="The bidder must provide an authorization letter.")


def valid_payload(source_id="s1", quote=SOURCE.text):
    return {"requirements": [{"statement": SOURCE.text, "category": "required_information",
        "obligation": "mandatory", "obligation_quote": SOURCE.text, "numeric_conditions": [], "date_conditions": [], "confidence": "high", "review_reasons": [], "citations": [{"source_id": source_id, "quote": quote}]}], "warnings": []}


def completion(payload, finish="stop"):
    return {"id": "chat-test", "object": "chat.completion", "created": 1, "model": "nvidia/test-nemotron",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": json.dumps(payload)}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}


def client_for(handler):
    settings = Settings(_env_file=None, nebius_api_key="test-key", nebius_model="nvidia/test-nemotron")
    return NemotronClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_extracts_with_verified_citation():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json=completion(valid_payload()))
    client = client_for(handler)
    try:
        result = await client.extract_requirements([SOURCE])
        assert result.batch.requirements[0].citations[0].source_id == "s1"
        assert result.usage.input_tokens == 20
    finally:
        await client.close()


async def test_repairs_once_and_counts_both_calls():
    calls = []
    def handler(request):
        calls.append(request)
        payload = valid_payload(source_id="invented") if len(calls) == 1 else valid_payload()
        return httpx.Response(200, json=completion(payload))
    client = client_for(handler)
    try:
        result = await client.extract_requirements([SOURCE])
        assert result.usage.attempts == 2
        assert result.usage.input_tokens == 40
    finally:
        await client.close()


async def test_rejects_invented_quote_after_bounded_repair():
    client = client_for(lambda _: httpx.Response(200, json=completion(valid_payload(quote="invented fact"))))
    try:
        with pytest.raises(IntegrationError, match="exact-citation"):
            await client.extract_requirements([SOURCE])
    finally:
        await client.close()


async def test_truncation_never_accepted():
    client = client_for(lambda _: httpx.Response(200, json=completion(valid_payload(), finish="length")))
    try:
        with pytest.raises(IntegrationError, match="Incomplete"):
            await client.extract_requirements([SOURCE])
    finally:
        await client.close()


async def test_errors_do_not_leak_provider_body():
    client = client_for(lambda _: httpx.Response(401, json={"error": {"message": "secret-provider-detail"}}))
    try:
        with pytest.raises(IntegrationError) as error:
            await client.extract_requirements([SOURCE])
        assert "secret-provider-detail" not in str(error.value)
    finally:
        await client.close()


def test_missing_key_fails_without_network():
    with pytest.raises(IntegrationError, match="not configured"):
        NemotronClient(Settings(_env_file=None, nebius_api_key=""))


async def test_model_discovery_filters_nemotron():
    client = client_for(lambda _: httpx.Response(200, json={"object": "list", "data": [
        {"id": "nvidia/Nemotron-example", "object": "model", "created": 1, "owned_by": "nvidia"},
        {"id": "other", "object": "model", "created": 1, "owned_by": "other"}]}))
    try:
        assert await client.list_models() == ["nvidia/Nemotron-example"]
    finally:
        await client.close()


@pytest.mark.parametrize("mutation", ["statement", "numeric", "date", "extra", "missing_confidence"])
async def test_rejects_unsupported_structured_facts(mutation):
    payload = valid_payload()
    req = payload["requirements"][0]
    if mutation == "statement": req["statement"] = "Invented requirement"
    if mutation == "numeric":
        req["numeric_conditions"] = [{"operator": ">=", "value_text": "999", "unit_text": None, "quote": SOURCE.text}]
    if mutation == "date":
        req["date_conditions"] = [{"relation": "before", "boundary_text": "2099-01-01", "quote": SOURCE.text}]
    if mutation == "extra": req["page_number"] = 99
    if mutation == "missing_confidence": del req["confidence"]
    client = client_for(lambda _: httpx.Response(200, json=completion(payload)))
    try:
        with pytest.raises(IntegrationError) as caught:
            await client.extract_requirements([SOURCE])
        assert caught.value.code == "invalid_extraction"
    finally:
        await client.close()


async def test_invalid_json_bounded_repair():
    calls = []
    def handler(request):
        calls.append(request)
        result = completion(valid_payload()); result["choices"][0]["message"]["content"] = "not-json"
        return httpx.Response(200, json=result)
    client = client_for(handler)
    try:
        with pytest.raises(IntegrationError):
            await client.extract_requirements([SOURCE])
        assert len(calls) == 2
    finally:
        await client.close()


async def test_timeout_is_sanitized_and_classified():
    def handler(request):
        raise httpx.ReadTimeout("SECRET", request=request)
    client = client_for(handler); client.client.max_retries = 0
    try:
        with pytest.raises(IntegrationError) as caught:
            await client.extract_requirements([SOURCE])
        assert caught.value.code == "provider_timeout"
        assert "SECRET" not in str(caught.value)
    finally:
        await client.close()


async def test_unproven_obligation_becomes_unclear():
    payload = valid_payload(); payload["requirements"][0]["obligation_quote"] = None
    client = client_for(lambda _: httpx.Response(200, json=completion(payload)))
    try:
        result = await client.extract_requirements([SOURCE])
        assert result.batch.requirements[0].obligation == "unclear"
        assert result.batch.requirements[0].review_reasons
    finally:
        await client.close()
