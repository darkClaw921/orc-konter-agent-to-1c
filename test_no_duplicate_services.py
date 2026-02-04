#!/usr/bin/env python3
"""
Test script to verify that duplicate service extraction has been removed from step 3
"""
import re

def test_prompts():
    """Check that services extraction has been removed from EXTRACT_CONTRACT_DATA_PROMPT"""
    with open('backend/app/services/prompts.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Check that EXTRACT_CONTRACT_DATA_PROMPT doesn't contain services extraction
    extract_prompt_match = re.search(
        r'EXTRACT_CONTRACT_DATA_PROMPT = """(.*?)"""',
        content,
        re.DOTALL
    )

    if not extract_prompt_match:
        print("❌ EXTRACT_CONTRACT_DATA_PROMPT not found")
        return False

    extract_prompt = extract_prompt_match.group(1)

    # Check that services-related sections are removed
    services_patterns = [
        r'Services \(Услуги из спецификации',
        r'CRITICAL: SERVICES EXTRACTION',
        r'Extract ALL services',
    ]

    found_services = []
    for pattern in services_patterns:
        if re.search(pattern, extract_prompt, re.IGNORECASE):
            found_services.append(pattern)

    if found_services:
        print(f"❌ Found services extraction patterns in EXTRACT_CONTRACT_DATA_PROMPT: {found_services}")
        return False

    print("✅ EXTRACT_CONTRACT_DATA_PROMPT: No services extraction found")

    # Check MERGE_CHUNKS_DATA_PROMPT
    merge_prompt_match = re.search(
        r'MERGE_CHUNKS_DATA_PROMPT = """(.*?)"""',
        content,
        re.DOTALL
    )

    if not merge_prompt_match:
        print("❌ MERGE_CHUNKS_DATA_PROMPT not found")
        return False

    merge_prompt = merge_prompt_match.group(1)

    # Check that services merging instructions are simplified
    if re.search(r'For services:.*merge all services', merge_prompt, re.IGNORECASE | re.DOTALL):
        print("❌ Found detailed services merging instructions in MERGE_CHUNKS_DATA_PROMPT")
        return False

    print("✅ MERGE_CHUNKS_DATA_PROMPT: Services merging instructions removed")

    # Verify EXTRACT_SERVICES_ONLY_PROMPT still exists
    services_only_match = re.search(
        r'EXTRACT_SERVICES_ONLY_PROMPT = """',
        content
    )

    if not services_only_match:
        print("❌ EXTRACT_SERVICES_ONLY_PROMPT not found")
        return False

    print("✅ EXTRACT_SERVICES_ONLY_PROMPT: Still exists for step 3.5")

    return True

def test_orchestrator():
    """Check that _build_chunk_context doesn't include services section"""
    with open('backend/app/agent/orchestrator.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find _build_chunk_context method
    method_match = re.search(
        r'def _build_chunk_context\(self.*?\n(?=    def )',
        content,
        re.DOTALL
    )

    if not method_match:
        print("❌ _build_chunk_context method not found")
        return False

    method_content = method_match.group(0)

    # Check that services section is removed
    if re.search(r'УСЛУГИ ИЗ СПЕЦИФИКАЦИИ', method_content):
        print("❌ Found 'УСЛУГИ ИЗ СПЕЦИФИКАЦИИ' section in _build_chunk_context")
        return False

    if re.search(r'services = extracted_data\.get\(.*services.*\)', method_content):
        # Check if it's about service locations (allowed) or services list (not allowed)
        if re.search(r"services = extracted_data\.get\('services'\)", method_content):
            print("❌ Found services extraction in _build_chunk_context")
            return False

    print("✅ _build_chunk_context: Services section removed")

    return True

def test_step_3_5_exists():
    """Verify that step 3.5 (_extract_all_services) still exists"""
    with open('backend/app/agent/orchestrator.py', 'r', encoding='utf-8') as f:
        content = f.read()

    if not re.search(r'async def _extract_all_services\(self', content):
        print("❌ _extract_all_services method not found")
        return False

    if not re.search(r'await self\._extract_all_services\(state\)', content):
        print("❌ _extract_all_services not called in process_contract")
        return False

    print("✅ Step 3.5 (_extract_all_services): Still exists and is called")

    return True

def main():
    print("=" * 70)
    print("Testing: Removal of Duplicate Service Extraction from Step 3")
    print("=" * 70)
    print()

    all_passed = True

    print("1. Testing prompts.py...")
    if not test_prompts():
        all_passed = False
    print()

    print("2. Testing orchestrator.py...")
    if not test_orchestrator():
        all_passed = False
    print()

    print("3. Verifying step 3.5 exists...")
    if not test_step_3_5_exists():
        all_passed = False
    print()

    print("=" * 70)
    if all_passed:
        print("✅ All tests passed! Duplicate service extraction has been removed.")
    else:
        print("❌ Some tests failed. Please review the changes.")
    print("=" * 70)

    return 0 if all_passed else 1

if __name__ == '__main__':
    exit(main())
