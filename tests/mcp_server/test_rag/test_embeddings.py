"""Tests for mcp_server/rag/embeddings.py — embedding generation and singleton."""

from unittest.mock import MagicMock, patch

import mcp_server.rag.embeddings as emb_module
from mcp_server.rag.embeddings import generate_embeddings, generate_query_embedding


class TestGenerateEmbeddings:
    def test_returns_384_dimensions(self):
        texts = ["drought in Brazil", "CO2 emissions"]
        result = generate_embeddings(texts)
        assert len(result) == 2
        assert all(len(vec) == 384 for vec in result)

    def test_empty_list_returns_empty(self):
        result = generate_embeddings([])
        assert result == []

    def test_single_text(self):
        result = generate_embeddings(["climate change"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_embeddings_are_floats(self):
        result = generate_embeddings(["test"])
        assert all(isinstance(v, float) for v in result[0])


class TestGenerateQueryEmbedding:
    def test_returns_single_384_vector(self):
        result = generate_query_embedding("drought northeast Brazil")
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)


class TestSingletonCaching:
    def test_model_loaded_only_once(self):
        import sys

        import numpy as np

        # Reset singleton
        emb_module._embedder = None

        mock_st_module = MagicMock()
        mock_model = MagicMock()
        mock_model.encode.return_value = [np.array([0.1] * 384)]
        MockST = MagicMock(return_value=mock_model)
        mock_st_module.SentenceTransformer = MockST

        # Patch sentence_transformers in sys.modules so the lazy import resolves to our mock
        with patch.dict(sys.modules, {"sentence_transformers": mock_st_module}):
            emb_module._embedder = None
            emb_module.get_embedder()
            emb_module.get_embedder()
            emb_module.get_embedder()

            MockST.assert_called_once_with("all-MiniLM-L6-v2")
