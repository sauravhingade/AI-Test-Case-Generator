import os
import json

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.schemas.models import TestCase, TestSuite


# ==========================================================
# CONSTANTS
# ==========================================================

# Location where ChromaDB files are stored on disk
# data/chroma_db/
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "../../data/chroma_db")

# Name of the Chroma collection
# Similar to a table name in SQL
COLLECTION_NAME = "test_cases"

# OpenAI embedding model used to convert text into vectors
EMBEDDING_MODEL = "text-embedding-3-small"


# ==========================================================
# SINGLETON VECTOR STORE
#
# We create the Chroma vector database only once and
# reuse it throughout the application.
#
# Without this:
# Request 1 -> create Chroma
# Request 2 -> create Chroma
# Request 3 -> create Chroma
#
# With singleton:
# Create once -> reuse forever
# ==========================================================

_vectorstore: Chroma | None = None


def get_vectorstore() -> Chroma:
    """
    Returns the Chroma vector store.

    First call:
        Creates embeddings + Chroma instance

    Future calls:
        Reuses existing instance
    """
    global _vectorstore

    if _vectorstore is None:
        # Embedding model used for semantic search
        embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL, api_key=os.getenv("OPENAI_API_KEY")
        )

        # Create/load Chroma collection
        _vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        )

    return _vectorstore


# ==========================================================
# INDEXING
# Converts TestCase objects into Documents
# so they can be stored in ChromaDB.
# ==========================================================


def _test_case_to_document(tc: TestCase, suite_name: str) -> Document:
    """
    Converts a TestCase into a LangChain Document.

    Chroma stores Documents, not Pydantic objects.

    page_content:
        Text used for similarity search

    metadata:
        Extra fields used for filtering
    """

    # Convert structured BDD steps into readable text
    #
    # Example:
    # Given user exists
    # When password is invalid
    # Then show error
    #
    steps_text = "\n".join(f"{step.keyword} {step.action}" for step in tc.steps)

    # This text gets embedded and searched
    #
    # Chroma does semantic similarity on this content
    #
    page_content = f"""
Test Case: {tc.title}
Feature: {suite_name}
Type: {tc.test_type.value}
Priority: {tc.priority.value}

Steps:
{steps_text}

Expected Result: {tc.expected_result}
Tags: {", ".join(tc.tags)}
    """.strip()

    # Metadata is NOT used for similarity search.
    #
    # It is used for filtering.
    #
    # Example:
    # filter={"suite_name": "Login"}
    #
    metadata = {
        "tc_id": tc.id,
        "title": tc.title,
        "test_type": tc.test_type.value,
        "priority": tc.priority.value,
        # Chroma metadata works best with simple types
        "is_edge_case": str(tc.is_edge_case),
        "user_story_id": tc.user_story_id,
        "suite_name": suite_name,
        # Store tags as JSON string
        "tags": json.dumps(tc.tags),
    }

    return Document(page_content=page_content, metadata=metadata)


def index_test_suite(suite: TestSuite) -> int:
    """
    Stores all test cases from one suite into ChromaDB.

    Example:

    Login Suite
        TC-001
        TC-002
        TC-003

    All three become Documents and are indexed.
    """
    vs = get_vectorstore()

    docs = [_test_case_to_document(tc, suite.suite_name) for tc in suite.test_cases]

    if docs:
        vs.add_documents(docs)

    return len(docs)


def index_all_suites(suites: list[TestSuite]) -> int:
    """
    Stores all test suites.

    Example:

    Login Suite
    Payment Suite
    Profile Suite

    Returns total number of indexed test cases.
    """
    total = 0

    for suite in suites:
        total += index_test_suite(suite)

    return total


# ==========================================================
# RETRIEVAL (RAG)
#
# Search previously indexed test cases.
# ==========================================================


def retrieve_similar_test_cases(
    query: str, k: int = 3, filter_by_feature: str | None = None
) -> list[str]:
    """
    Retrieves similar test cases from ChromaDB.

    Example query:
        "invalid login password"

    Chroma:
        query -> embedding

    Finds:
        most similar stored embeddings

    Returns:
        page_content strings
    """
    vs = get_vectorstore()

    # Internal Chroma collection
    collection = vs._collection

    # If database is empty,
    # there is nothing to retrieve.
    if collection.count() == 0:
        return []

    # Optional metadata filter
    #
    # Example:
    # {"suite_name": "Login"}
    #
    # Equivalent SQL idea:
    # WHERE suite_name = 'Login'
    #
    where = {"suite_name": filter_by_feature} if filter_by_feature else None

    try:
        docs = vs.similarity_search(
            query=query,
            k=k,
            filter=where,
        )

        # Return only the searchable text
        # This will later be injected into prompts.
        return [doc.page_content for doc in docs]

    except Exception:
        # RAG is optional.
        # Generation should still work if retrieval fails.
        return []


def retrieve_similar_for_story(
    story_title: str, feature_area: str, k: int = 3
) -> list[str]:
    """
    Convenience wrapper — retrieves similar TCs for a user story.

    Example:

    Story:
        Reset Password

    Feature:
        Authentication

    Query becomes:

        Authentication Reset Password test cases
    """

    query = f"{feature_area} {story_title} test cases"

    return retrieve_similar_test_cases(
        query=query,
        k=k,
        # Search entire collection
        filter_by_feature=None,
    )


# ==========================================================
# MAINTENANCE HELPERS
# ==========================================================


def clear_vectorstore() -> bool:
    """
    Deletes ALL indexed test cases.

    Useful during development/testing.
    """
    try:
        vs = get_vectorstore()

        # Delete all documents whose tc_id is not empty
        #
        # $ne = Not Equal
        #
        # Similar SQL:
        # WHERE tc_id != ''
        #
        vs._collection.delete(where={"tc_id": {"$ne": ""}})

        return True

    except Exception:
        return False


def get_indexed_count() -> int:
    """
    Returns total number of indexed documents.
    """
    try:
        vs = get_vectorstore()
        return vs._collection.count()

    except Exception:
        return 0
