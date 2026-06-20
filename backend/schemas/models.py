from pydantic import BaseModel, Field
from enum import Enum


# ==========================================================
# ENUMS
# Used to restrict values to a predefined set.
# Example:
# Priority.CRITICAL -> "critical"
# Priority.HIGH -> "high"
# ==========================================================


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Type of test case AI can generate
class TestType(str, Enum):
    FUNCTIONAL = "functional"
    NEGATIVE = "negative"
    EDGE_CASE = "edge_case"
    REGRESSION = "regression"
    PERFORMANCE = "performance"


# Format in which test steps should be generated
class BDDFormat(str, Enum):
    GHERKIN = "gherkin"
    PLAIN_ENGLISH = "plain_english"


# ==========================================================
# USER STORY MODELS
# These schemas store extracted user stories from
# requirement documents.
# ==========================================================


class UserStory(BaseModel):
    # Unique story id
    id: str = Field(description="Unique ID like US-001, US-002")

    # Short title
    title: str = Field(description="Short title of the user story")

    # Full user story
    description: str = Field(description="As a [user], I want [goal], so that [reason]")

    # Acceptance criteria extracted from requirements
    acceptance_criteria: list[str] = Field(description="List of acceptance criteria")

    # Module/feature name
    feature_area: str = Field(
        description="Feature area like Login, Payment, Profile etc."
    )


# Stores all extracted user stories
class UserStoryList(BaseModel):
    user_stories: list[UserStory]

    total_count: int = Field(description="Total number of user stories extracted")

    summary: str = Field(description="One line summary of the requirements document")


# ==========================================================
# TEST CASE MODELS
# These schemas define generated test cases.
# ==========================================================


# Single Given/When/Then step
class TestStep(BaseModel):
    step_number: int

    keyword: str = Field(description="Given / When / Then / And / But")

    action: str = Field(description="The actual step description")


# Individual test case
class TestCase(BaseModel):
    id: str = Field(description="Unique ID like TC-001, TC-002")

    title: str = Field(description="Clear, concise test case title")

    user_story_id: str = Field(description="Which user story this belongs to")

    # Enum values only
    test_type: TestType

    # Enum values only
    priority: Priority

    preconditions: list[str] = Field(description="Setup needed before test runs")

    steps: list[TestStep] = Field(description="BDD steps - Given/When/Then")

    expected_result: str = Field(description="What should happen if test passes")

    is_edge_case: bool = Field(description="Is this an edge/boundary case?")

    tags: list[str] = Field(description="Tags like smoke, regression, login etc.")


# Group of related test cases
class TestSuite(BaseModel):
    suite_name: str

    user_story_id: str

    test_cases: list[TestCase]

    total_count: int

    critical_count: int = Field(description="Number of critical priority test cases")

    edge_case_count: int = Field(description="Number of edge cases")

    coverage_areas: list[str] = Field(
        description="What areas are covered by this suite"
    )


# ==========================================================
# API REQUEST / RESPONSE MODELS
# Request -> Sent by frontend to backend
# Response -> Returned by backend to frontend
# ==========================================================


# Input schema for test case generation
class GenerateRequest(BaseModel):
    requirements_text: str = Field(description="Raw requirements text")

    test_types: list[TestType] = Field(
        default=[
            TestType.FUNCTIONAL,
            TestType.NEGATIVE,
            TestType.EDGE_CASE,
        ],
        description="Which types of test cases to generate",
    )

    bdd_format: BDDFormat = Field(
        default=BDDFormat.GHERKIN, description="BDD format for steps"
    )

    max_test_cases_per_story: int = Field(
        default=5, ge=1, le=20, description="Max test cases per user story"
    )


# Final response returned by AI test generator
class GenerateResponse(BaseModel):
    user_stories: list[UserStory]

    test_suites: list[TestSuite]

    total_test_cases: int

    total_user_stories: int

    requirements_summary: str
