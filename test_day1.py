from dotenv import load_dotenv
from backend.schemas.models import GenerateRequest, TestType, BDDFormat
from backend.chains.extractor_chain import extract_user_stories
from backend.chains.generator_chain import generate_all_test_suites

load_dotenv()

"""
Day 1 Test — run this from project root:
    python test_day1.py
"""


# ── Sample requirements text ────────────────────────────────

SAMPLE_REQUIREMENTS = """
Product: E-Commerce Mobile App

1. User Registration & Login
   - Users can register using email and password
   - Password must be minimum 8 characters with at least one number
   - Users can login with registered email/password
   - Failed login attempts should be locked after 5 tries
   - Users can reset password via email OTP

2. Product Search
   - Users can search products by name or category
   - Search results show product name, price, and rating
   - Users can filter results by price range and rating
   - Out of stock products should be shown but not purchasable

3. Shopping Cart
   - Users can add products to cart
   - Users can update quantity or remove items from cart
   - Cart should persist across sessions
   - Cart should show total price with taxes
"""


def test_extraction():
    print("\n" + "=" * 60)
    print("STEP 1: Extracting User Stories...")
    print("=" * 60)

    result = extract_user_stories(SAMPLE_REQUIREMENTS)

    print(f"\n✅ Summary     : {result.summary}")
    print(f"✅ Total Stories: {result.total_count}")

    for story in result.user_stories:
        print(f"\n  [{story.id}] {story.title}")
        print(f"  Feature : {story.feature_area}")
        print(f"  Criteria: {len(story.acceptance_criteria)} items")

    return result


def test_generation(user_story_list):
    print("\n" + "=" * 60)
    print("STEP 2: Generating Test Cases...")
    print("=" * 60)

    request = GenerateRequest(
        requirements_text=SAMPLE_REQUIREMENTS,
        test_types=[TestType.FUNCTIONAL, TestType.NEGATIVE, TestType.EDGE_CASE],
        bdd_format=BDDFormat.GHERKIN,
        max_test_cases_per_story=5,
    )

    # Only test first story to save API tokens during dev
    suites = generate_all_test_suites(
        user_stories=user_story_list.user_stories[:1], request=request
    )

    for suite in suites:
        print(f"\n📋 Suite: {suite.suite_name}")
        print(f"   Total    : {suite.total_count} test cases")
        print(f"   Critical : {suite.critical_count}")
        print(f"   Edge Cases: {suite.edge_case_count}")
        print(f"   Coverage : {', '.join(suite.coverage_areas)}")

        for tc in suite.test_cases:
            print(f"\n   [{tc.id}] {tc.title}")
            print(f"   Type     : {tc.test_type.value} | Priority: {tc.priority.value}")
            print(f"   Edge case: {tc.is_edge_case}")
            print(f"   Steps    : {len(tc.steps)}")
            for step in tc.steps:
                print(f"     {step.keyword} {step.action}")
            print(f"   Expected : {tc.expected_result}")

    return suites


if __name__ == "__main__":
    user_stories = test_extraction()
    test_suites = test_generation(user_stories)
    print("\n✅ Day 1 Complete! Chains working correctly.")
