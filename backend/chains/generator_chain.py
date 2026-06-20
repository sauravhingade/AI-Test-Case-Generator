from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from backend.schemas.models import (
    UserStory,
    TestSuite,
    TestType,
    GenerateRequest,
)
import os


# ── Prompt ─────────────────────────────────────────────────

GENERATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior QA automation engineer with 10 years of experience.
Your job is to generate comprehensive BDD test cases for a given user story.

Rules for test cases:
- Test case IDs must be sequential starting from the given offset: TC-001, TC-002 etc.
- Every test case needs clear Given/When/Then steps
- Always include: happy path, negative cases, and edge cases
- Preconditions must be realistic (e.g. "User is registered", "User is logged in")
- Expected results must be specific — not vague like "it works"
- Tags must include the feature area and test type
- is_edge_case = true only for boundary/limit/unexpected input tests
- Priority rules:
    critical → authentication, payments, data loss scenarios
    high     → core feature functionality
    medium   → secondary features, UI validations
    low      → cosmetic, nice-to-have scenarios

Test types to generate: {test_types}
BDD Format: {bdd_format}
Max test cases: {max_test_cases}

{rag_context}""",
        ),
        (
            "human",
            """Generate comprehensive test cases for this user story:

User Story ID   : {user_story_id}
Title           : {user_story_title}
Description     : {user_story_description}
Feature Area    : {feature_area}

Acceptance Criteria:
{acceptance_criteria}

Generate a complete TestSuite for this user story.""",
        ),
    ]
)


# ── Chain Factory ───────────────────────────────────────────


def build_generator_chain() -> RunnableSerializable:
    """
    Builds and returns the test case generator chain.
    Returns a chain: prompt | llm.with_structured_output(TestSuite)
    """
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.2,  # slight creativity for edge cases
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    structured_llm = llm.with_structured_output(TestSuite)
    chain = GENERATOR_PROMPT | structured_llm
    return chain


# ── Helper ─────────────────────────────────────────────────


def _format_acceptance_criteria(criteria: list[str]) -> str:
    return "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(criteria))


def _format_test_types(test_types: list[TestType]) -> str:
    return ", ".join(t.value for t in test_types)


def _format_rag_context(similar_test_cases: list[str]) -> str:
    """Format retrieved RAG examples as few-shot context."""
    if not similar_test_cases:
        return ""
    examples = "\n\n".join(similar_test_cases)
    return f"""
Similar test cases from your team's history (use these as style reference):
--- EXAMPLES START ---
{examples}
--- EXAMPLES END ---
"""


# ── Public function ─────────────────────────────────────────


def generate_test_suite(
    user_story: UserStory,
    request: GenerateRequest,
    similar_test_cases: list[str] | None = None,
    tc_id_offset: int = 0,
) -> TestSuite:
    """
    Takes a UserStory and returns a complete TestSuite.

    Args:
        user_story          : Extracted UserStory object
        request             : GenerateRequest with config options
        similar_test_cases  : Retrieved RAG examples (optional)
        tc_id_offset        : Offset for sequential TC IDs across stories

    Returns:
        TestSuite with test_cases, counts, coverage_areas
    """
    chain = build_generator_chain()

    rag_context = _format_rag_context(similar_test_cases or [])

    result: TestSuite = chain.invoke(
        {
            "user_story_id": user_story.id,
            "user_story_title": user_story.title,
            "user_story_description": user_story.description,
            "feature_area": user_story.feature_area,
            "acceptance_criteria": _format_acceptance_criteria(
                user_story.acceptance_criteria
            ),
            "test_types": _format_test_types(request.test_types),
            "bdd_format": request.bdd_format.value,
            "max_test_cases": request.max_test_cases_per_story,
            "rag_context": rag_context,
        }
    )

    # Fix TC IDs to be globally unique across all user stories
    for i, tc in enumerate(result.test_cases):
        tc.id = f"TC-{tc_id_offset + i + 1:03d}"
        tc.user_story_id = user_story.id

    return result


# ── Batch generate for all user stories ────────────────────


def generate_all_test_suites(
    user_stories: list[UserStory],
    request: GenerateRequest,
    similar_test_cases_map: dict[str, list[str]] | None = None,
) -> list[TestSuite]:
    """
    Generates TestSuites for ALL user stories.

    Args:
        user_stories            : All extracted user stories
        request                 : GenerateRequest config
        similar_test_cases_map  : Dict of {user_story_id: [similar_tc_strings]}

    Returns:
        List of TestSuite — one per user story
    """
    suites = []
    tc_offset = 0

    for story in user_stories:
        similar = (similar_test_cases_map or {}).get(story.id, [])

        suite = generate_test_suite(
            user_story=story,
            request=request,
            similar_test_cases=similar,
            tc_id_offset=tc_offset,
        )
        suites.append(suite)
        tc_offset += len(suite.test_cases)

    return suites
