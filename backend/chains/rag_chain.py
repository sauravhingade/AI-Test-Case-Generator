"""
RAG Chain — retrieves similar past test cases from ChromaDB
and injects them as few-shot examples into the generator chain.

Flow:
  User Story → get_rag_context_for_story() → top-K similar TCs
                        ↓
  Generator chain gets rag_context in prompt
                        ↓
  LLM uses past examples as style/format reference
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from backend.rag.vectorstore import get_vectorstore, get_indexed_count
from backend.schemas.models import UserStory
import os


# ── Retriever builder ───────────────────────────────────────


def build_retriever(k: int = 3):
    """
    Builds a LangChain retriever from ChromaDB vectorstore.
    Returns top-k similar documents for a given query.
    """
    vs = get_vectorstore()
    retriever = vs.as_retriever(search_type="similarity", search_kwargs={"k": k})
    return retriever


# ── Format retrieved docs ───────────────────────────────────


def format_retrieved_docs(docs) -> str:
    """Formats retrieved Documents into clean string for prompt injection."""
    if not docs:
        return ""
    formatted = []
    for i, doc in enumerate(docs, 1):
        formatted.append(f"Example {i}:\n{doc.page_content}")
    return "\n\n".join(formatted)


# ── Main RAG function ───────────────────────────────────────


def get_rag_context_for_story(story: UserStory, k: int = 3) -> str:
    """
    Given a UserStory, retrieves similar past test cases
    and returns them as formatted string for prompt injection.

    Returns empty string if RAG is empty — generation still works.
    """
    if get_indexed_count() == 0:
        return ""

    retriever = build_retriever(k=k)
    query = f"{story.feature_area} {story.title} test cases"

    try:
        docs = retriever.invoke(query)
        return format_retrieved_docs(docs)
    except Exception:
        return ""


# ── Build RAG map for all stories ──────────────────────────


def build_rag_context_map(stories: list[UserStory], k: int = 3) -> dict[str, list[str]]:
    """
    Builds a dict of {user_story_id: [rag_context_string]}
    for all stories at once.

    Used in main.py pipeline before generate_all_test_suites.
    """
    rag_map = {}
    for story in stories:
        context = get_rag_context_for_story(story, k=k)
        if context:
            rag_map[story.id] = [context]
    return rag_map


# ── RAG QA Chain (bonus — for future chat feature) ─────────


def build_rag_qa_chain():
    """
    Builds a RAG QA chain over indexed test cases.
    For future Streamlit chat: "Show me all critical login test cases"
    """
    vs = get_vectorstore()
    retriever = vs.as_retriever(search_kwargs={"k": 5})

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a QA assistant. Answer questions about test cases
using only the context provided below.

Context:
{context}

If the answer is not in the context, say "No matching test cases found."
Keep answers concise and structured.""",
            ),
            ("human", "{question}"),
        ]
    )

    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    chain = (
        {
            "context": retriever | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain
