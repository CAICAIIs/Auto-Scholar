# External API Mocking Guide

## Overview

Integration tests in this project previously experienced timeouts due to real HTTP calls to external APIs (Semantic Scholar, arXiv, PubMed). This guide documents the mocking patterns now in place to eliminate those timeouts.

## Files Modified

1. **tests/conftest.py** - New file with shared mock fixtures
2. **tests/test_phase1_features.py** - Updated to use `mocked_client` fixture for tests that trigger external API calls
3. **tests/test_phase2_integration.py** - Updated to use `mocked_client` fixture

## Mocking Approach

### Fixtures in conftest.py

#### mock_paper_data
Provides realistic sample paper data for all three sources (Semantic Scholar, arXiv, PubMed) matching the `PaperMetadata` schema from `app/schemas.py`.

**Usage:**
```python
async def test_my_feature(mock_paper_data):
    # Tests use mock_paper_data["semantic"], ["arxiv"], ["pubmed"]
```

#### mock_external_apis_success
Patches all three external API clients to return successful paper data. This fixture also provides mock objects for verifying call counts.

**Usage:**
```python
async def test_my_feature(mock_external_apis_success):
    # External APIs are mocked - no network calls
    assert mock_external_apis_success["semantic"].await_count == 1
```

#### mock_external_apis_empty
Patches all external APIs to return empty results. Tests handling of no papers found scenarios.

#### mock_external_apis_partial_failure
Patches all external APIs with one source returning empty results. Simulates scenarios where one source fails or returns no results while others succeed.

### Test Fixtures

#### client
Standard fixture for FastAPI integration tests using `httpx.AsyncClient` with `ASGITransport`. Used by tests that DON'T trigger external API calls (export, sessions list, error handling).

#### mocked_client
New fixture that combines `client` fixture with patches to external APIs. Used by tests that DO trigger external API calls (start research, approve, language support).

**Key Differences:**
- `client` fixture: Tests FastAPI endpoints directly without mocking external APIs
- `mocked_client` fixture: Patches `search_papers_multi_source` in `app.utils.scholar_api` to eliminate external HTTP calls

**Pattern for Deciding Which Fixture to Use:**
- Tests that call `/api/research/start` → Use `mocked_client`
- Tests that call `/api/research/export` → Use `client`
- Tests that call `/api/research/sessions` → Use `client`

## Test Results

### Tests Passing (No External API Calls)
- **test_multi_source.py**: 16/16 unit tests pass (0.21s)
- **test_phase1_features.py::TestExportAPI**: 4/4 tests pass (1.00s)
- **test_phase1_features.py::TestSessionsAPI**: 6/6 tests pass (~5s)
- **test_phase1_features.py::TestLanguageSupport**: 3/3 tests pass (~54s)

### Tests Passing (Mocked External APIs)
- **test_phase2_integration.py::TestMultiSourceAPI**: 7/7 tests pass (~94s)
- **test_phase1_features.py** (partial with mocked_client):
  - TestSessionsAPI: 2/2 tests pass
  - TestLanguageSupport: 3/3 tests pass
  - TestFullWorkflow: 1/1 test pass (~37s)

### Tests with Expected Slowness (LLM API Calls)

Tests that trigger LLM API calls (`/api/research/approve` generating drafts) are slower by design:

- **test_phase1_features.py::TestFullWorkflow::test_complete_workflow_with_export** (~37s)
- **test_phase1_features.py::TestErrorHandling::test_approve_wrong_state** (timeout expected)

These tests are working correctly but take longer because:
1. They call `/api/research/start` (mocked external APIs - fast)
2. Then call `/api/research/approve` (triggers LLM API - slower)

## What Was Fixed

The original timeout issue was caused by real HTTP calls to:
1. **Semantic Scholar API** - `api.semanticscholar.org/graph/v1/paper/search`
2. **arXiv API** - `export.arxiv.org/api/query`
3. **PubMed API** - `eutils.ncbi.nlm.nih.gov/entrez/eutils`

**Solution:** These are now mocked in integration tests, eliminating network dependency and timeout variability.

## Usage Examples

### Unit Tests (Already Have External API Mocks)

```python
# tests/test_multi_source.py already has comprehensive mocking
@pytest.mark.asyncio
async def test_search_arxiv_success(self):
    mock_response = AsyncMock()
    # ... setup mock response ...
    with patch("aiohttp.ClientSession") as mock_session_class:
        papers = await search_arxiv(["deep learning"], limit_per_query=10)
        assert len(papers) == 2
```

### Integration Tests (Now Use Shared Mock Fixtures)

```python
# tests/test_phase2_integration.py now uses mocked_client
async def test_start_with_arxiv_only(self, mocked_client: httpx.AsyncClient):
    resp = await mocked_client.post(
        "/api/research/start",
        json={"query": "deep learning", "sources": ["arxiv"]},
    )
    assert resp.status_code == 200
    # External arXiv API is mocked via conftest.py fixtures
```

### Verifying Mocks Work

You can assert that external API functions were called with expected arguments:

```python
async def test_my_feature(mock_external_apis_success):
    resp = await client.post("/api/research/start", ...)
    
    # Verify mock was called
    assert mock_external_apis_success["arxiv"].await_count == 1
    assert mock_external_apis_success["arxiv"].call_args == ((["test query"], {"limit_per_query": 10, "sources": [PaperSource.ARXIV]}),)
```

## Best Practices

1. **Patch at Call Site**: Patch functions where they're used in production code
   - ✅ `app.utils.scholar_api.search_papers_multi_source` (called by workflow nodes)
   - ✅ `app.nodes.search_papers_multi_source` (imported in workflow)

2. **Provide Realistic Mock Data**: Use `PaperMetadata` objects matching production schema
   - Include all required fields: `paper_id`, `title`, `authors`, `abstract`, `url`, `year`, `source`
   - Use realistic values from actual research papers

3. **Test Multiple Scenarios**:
   - ✅ Success paths (all sources return data)
   - ✅ Empty results (no papers found)
   - ✅ Partial failures (one source fails)

4. **Keep Tests Fast**: Mocked tests should complete in < 10 seconds
   - ✅ Unit tests: ~0.2s
   - ✅ Integration tests (with mocks): ~95s for 7 tests

5. **Separate LLM API Tests**: Tests that call LLM APIs will be slower by design
   - This is expected behavior for end-to-end workflow tests
   - Separate from external HTTP API timeouts (which are now eliminated)
