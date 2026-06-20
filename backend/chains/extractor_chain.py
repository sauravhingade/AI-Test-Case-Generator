from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from backend.schemas.models import UserStoryList
import os


# ==========================================================
# PROMPT TEMPLATE
#
# This prompt tells the LLM how to extract user stories
# from a requirements document.
#
# System Message:
#   Defines the AI's role and extraction rules.
#
# Human Message:
#   Injects the actual requirements text.
# ==========================================================

EXTRACTOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior QA engineer and business analyst.
Your job is to read a software requirements document and extract clear, 
structured user stories from it.

Rules:
- Each user story must follow: "As a [user], I want [goal], so that [reason]"
- Extract EVERY distinct feature or requirement as a separate user story
- Acceptance criteria must be specific and testable
- Feature areas must be single words or short phrases like: Login, Payment, Profile
- User story IDs must be sequential: US-001, US-002 etc.
- If the document is vague, make reasonable assumptions and note them
- Minimum 1 user story, maximum 15 per document""",
        ),
        (
            "human",
            """Extract all user stories from the following requirements document:

--- REQUIREMENTS DOCUMENT START ---
{requirements_text}
--- REQUIREMENTS DOCUMENT END ---

Extract structured user stories with acceptance criteria.""",
        ),
    ]
)


# ==========================================================
# CHAIN BUILDER
#
# Creates:
# Prompt
#   ↓
# GPT-4o
#   ↓
# Structured Output (UserStoryList)
#
# Returns a LangChain Runnable chain.
# ==========================================================


def build_extractor_chain() -> RunnableSerializable:
    """
    Builds and returns the user story extractor chain.
    Returns a chain: prompt | llm.with_structured_output(UserStoryList)
    """

    # Create OpenAI chat model
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.1,  # Lower temperature = more consistent output
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Force LLM output to match UserStoryList schema
    structured_llm = llm.with_structured_output(UserStoryList)

    # Pipe prompt output into structured LLM
    chain = EXTRACTOR_PROMPT | structured_llm

    return chain


# ==========================================================
# PUBLIC FUNCTION
#
# Called by API routes/services.
#
# Input:
#   Raw requirements text
#
# Output:
#   UserStoryList object
# ==========================================================


def extract_user_stories(requirements_text: str) -> UserStoryList:
    """
    Takes raw requirements text and returns structured UserStoryList.

    Args:
        requirements_text: Raw text from PDF/DOCX/textarea

    Returns:
        UserStoryList with user_stories, total_count, summary
    """

    # Build extraction pipeline
    chain = build_extractor_chain()

    # Execute chain
    result: UserStoryList = chain.invoke({"requirements_text": requirements_text})

    return result
