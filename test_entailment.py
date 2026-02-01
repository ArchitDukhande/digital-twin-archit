"""
Unit tests for semantic entailment checking in VerifierGate.
Tests the critical anti-hallucination feature.
"""
import os
from dotenv import load_dotenv
from openai import OpenAI
from layers.verifier_gate import VerifierGate

load_dotenv()

def test_no_entailment_customer_complaints():
    """
    Test that related but non-supporting evidence is rejected.
    Question asks about customer complaints, but evidence only shows internal errors.
    Expected: refusal with no citations.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    verifier = VerifierGate(client, "gpt-4o-mini")
    
    question = "What customer complaints did we receive?"
    evidence = {
        "has_evidence": True,
        "evidence": [{
            "quote": "invoke requests failed with a no-capacity error",
            "chunk_id": "test:chunk:1",
            "file": "data/test.md",
            "timestamp": None,
        }]
    }
    
    result = verifier.generate_answer(question, evidence, [])
    
    print("\n=== Test 1: No Entailment (Customer Complaints) ===")
    print(f"Question: {question}")
    print(f"Evidence: {evidence['evidence'][0]['quote']}")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Citations: {len(result['citations'])}")
    
    # Assertions
    assert "do not see" in result['answer'].lower(), "Should refuse when evidence doesn't support question"
    assert result['confidence'] == 'none', "Confidence should be none"
    assert len(result['citations']) == 0, "Should have no citations"
    # Reasoning can be either "does not support" or "insufficient evidence"
    assert ("does not support" in result['reasoning'].lower() or 
            "insufficient" in result['reasoning'].lower()), "Reasoning should indicate rejection"
    
    print("✅ PASSED: Correctly refused unrelated evidence")


def test_entailment_cold_start():
    """
    Test that directly supporting evidence is accepted.
    Question asks about cold start time, evidence explicitly states it.
    Expected: answer with citations.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    verifier = VerifierGate(client, "gpt-4o-mini")
    
    question = "How long did cold start take?"
    evidence = {
        "has_evidence": True,
        "evidence": [{
            "quote": "From a fully cold state, it took about 6–9 minutes to get the first successful response.",
            "chunk_id": "test:chunk:2",
            "file": "data/test.md",
            "timestamp": None,
        }]
    }
    
    # Mock retrieved chunks for citation building
    retrieved_chunks = [{
        "chunk": {
            "id": "test:chunk:2",
            "file": "data/test.md",
            "text": "From a fully cold state, it took about 6–9 minutes to get the first successful response.",
            "timestamp": None,
        },
        "score": 0.9,
    }]
    
    result = verifier.generate_answer(question, evidence, retrieved_chunks)
    
    print("\n=== Test 2: Entailment Success (Cold Start) ===")
    print(f"Question: {question}")
    print(f"Evidence: {evidence['evidence'][0]['quote']}")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Citations: {len(result['citations'])}")
    
    # Assertions
    assert "do not see" not in result['answer'].lower(), "Should answer when evidence supports question"
    assert result['confidence'] in ['medium', 'high'], "Confidence should be medium or high"
    assert len(result['citations']) > 0, "Should have citations"
    assert "6" in result['answer'] or "minutes" in result['answer'].lower(), "Answer should mention the duration"
    
    print("✅ PASSED: Correctly answered with supporting evidence")


if __name__ == "__main__":
    print("Running VerifierGate entailment tests...\n")
    
    try:
        test_no_entailment_customer_complaints()
        test_entailment_cold_start()
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
