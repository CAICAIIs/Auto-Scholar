import json
from pathlib import Path

import jsonschema
import pytest

from backend.schemas import PaperMetadata, PaperSource
from backend.utils.text_chunker import TextChunk
from backend.utils.vector_pipeline import _build_chunk_payloads

SCHEMA_PATH = Path(__file__).parent.parent / "contracts" / "qdrant_payload.schema.json"


@pytest.fixture
def payload_schema():
    return json.loads(SCHEMA_PATH.read_text())


def test_inline_pipeline_payload_matches_contract(payload_schema):
    paper = PaperMetadata(
        paper_id="test-paper-001",
        title="Test Paper Title",
        authors=["Author A", "Author B"],
        abstract="Test abstract content",
        url="https://example.com/paper",
        year=2024,
        source=PaperSource.SEMANTIC_SCHOLAR,
    )
    chunks = [
        TextChunk(
            text="This is the first chunk of text content.",
            chunk_index=0,
            token_count=8,
            start_char=0,
            end_char=40,
            page_start=1,
            page_end=1,
        ),
        TextChunk(
            text="Second chunk without page info.",
            chunk_index=1,
            token_count=6,
            start_char=40,
            end_char=70,
        ),
    ]

    payloads = _build_chunk_payloads(paper, chunks)

    assert len(payloads) == 2
    for payload in payloads:
        jsonschema.validate(payload, payload_schema)


def test_inline_pipeline_payload_has_page_fields(payload_schema):
    paper = PaperMetadata(
        paper_id="page-test",
        title="Page Test",
        authors=[],
        abstract="",
        url="https://example.com",
        year=None,
    )
    chunk = TextChunk(
        text="Chunk with page info.",
        chunk_index=0,
        token_count=4,
        start_char=0,
        end_char=21,
        page_start=3,
        page_end=5,
    )

    payloads = _build_chunk_payloads(paper, [chunk])
    assert payloads[0]["page_start"] == 3
    assert payloads[0]["page_end"] == 5
    jsonschema.validate(payloads[0], payload_schema)


def test_claim_verifier_reads_only_contract_fields(payload_schema):
    fields_read_by_verifier = {"chunk_text", "page_start", "page_end"}
    schema_fields = set(payload_schema["properties"].keys())
    missing = fields_read_by_verifier - schema_fields
    assert not missing, f"claim_verifier reads fields not in contract: {missing}"


def test_contract_schema_is_valid_json_schema(payload_schema):
    jsonschema.Draft202012Validator.check_schema(payload_schema)
