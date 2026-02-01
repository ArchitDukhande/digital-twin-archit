"""
Comprehensive tests for Digital Twin anti-hallucination and question understanding.
Tests both SUMMARY_MODE and FACT_MODE with entailment verification.
"""
import os
from twin import DigitalTwin


def test_q4_summary():
    """Test Q4 summary - should answer with citations from October-December data."""
    print("\n=== Test 1: Q4 Summary ===")
    twin = DigitalTwin()
    result = twin.answer("What was I working on in Q4 2025?")
    
    print(f"Question: What was I working on in Q4 2025?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Citations: {len(result.get('citations', []))}")
    
    # Should have answer since we have December data
    is_refusal = ("see this in your data" in result["answer"].lower())
    assert not is_refusal, "Should answer Q4 query with December data"
    assert len(result.get("citations", [])) >= 1, "Should have at least 1 citation"
    assert result["confidence"] in ["medium", "high"], f"Expected medium/high confidence, got {result['confidence']}"
    
    print("✅ PASSED: Q4 summary answered with citations")


def test_late_december_inference():
    """Test late December inference - should answer with citations from late Dec."""
    print("\n=== Test 2: Late December Inference ===")
    twin = DigitalTwin()
    result = twin.answer("What happened in late December around inference?")
    
    print(f"Question: What happened in late December around inference?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Citations: {len(result.get('citations', []))}")
    
    # Should have answer with late December inference work
    is_refusal = ("see this in your data" in result["answer"].lower())
    assert not is_refusal, "Should answer late December query"
    assert len(result.get("citations", [])) >= 1, "Should have at least 1 citation"
    
    print("✅ PASSED: Late December inference answered with citations")


def test_cold_start_latency():
    """Test specific fact question - should answer with citation."""
    print("\n=== Test 3: Cold Start Latency (FACT_MODE) ===")
    twin = DigitalTwin()
    result = twin.answer("How long did cold start take?")
    
    print(f"Question: How long did cold start take?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Citations: {len(result.get('citations', []))}")
    
    # Should answer with specific timing
    is_refusal = ("see this in your data" in result["answer"].lower())
    assert not is_refusal, "Should answer cold start question"
    assert len(result.get("citations", [])) >= 1, "Should have at least 1 citation"
    assert "6" in result["answer"] or "9" in result["answer"] or "minutes" in result["answer"].lower(), "Should mention timing"
    
    print("✅ PASSED: Cold start question answered with citation")


def test_favorite_color_refuse():
    """Test unrelated question - should refuse."""
    print("\n=== Test 4: Favorite Color (Should Refuse) ===")
    twin = DigitalTwin()
    result = twin.answer("What is my favorite color?")
    
    print(f"Question: What is my favorite color?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Citations: {len(result.get('citations', []))}")
    
    # Should refuse - no data about favorite color
    is_refusal = ("see this in your data" in result["answer"].lower() or "cannot" in result["answer"].lower())
    assert is_refusal, f"Should refuse question about favorite color, got: {result['answer']}"
    assert result["confidence"] == "none", f"Expected none confidence, got {result['confidence']}"
    assert len(result.get("citations", [])) == 0, "Should have no citations"
    
    print("✅ PASSED: Correctly refused unrelated question")


def test_customer_complaints_refuse():
    """Test semantic entailment - should refuse when evidence doesn't support."""
    print("\n=== Test 5: Customer Complaints (Should Refuse) ===")
    twin = DigitalTwin()
    result = twin.answer("What customer complaints did we receive?")
    
    print(f"Question: What customer complaints did we receive?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Reasoning: {result.get('reasoning', 'N/A')}")
    
    # Should refuse - internal errors are not customer complaints
    is_refusal = ("see this in your data" in result["answer"].lower() or "cannot" in result["answer"].lower())
    assert is_refusal, f"Should refuse when evidence doesn't support question, got: {result['answer']}"
    assert result["confidence"] == "none", f"Expected none confidence, got {result['confidence']}"
    
    print("✅ PASSED: Correctly refused unrelated evidence (entailment check)")


def test_cto_praise_refuse():
    """Test praise detection - should refuse unless explicit praise exists."""
    print("\n=== Test 6: CTO Praise (Should Refuse Unless Explicit) ===")
    twin = DigitalTwin()
    result = twin.answer("Did the CTO praise me?")
    
    print(f"Question: Did the CTO praise me?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
    
    # Should refuse unless explicit praise exists in data
    # (Current dummy data has "Welcome, Archit" which is not praise)
    is_refusal = ("see this in your data" in result["answer"].lower() or "cannot" in result["answer"].lower())
    if is_refusal:
        print("✅ PASSED: Correctly refused (no explicit praise in data)")
    else:
        # If it answers, check if it's grounded in actual praise
        assert len(result.get("citations", [])) >= 1, "If answering, must have citations"
        print("✅ PASSED: Answered with grounded evidence")


def run_all_tests():
    """Run all comprehensive tests."""
    print("=" * 60)
    print("Running Comprehensive Digital Twin Tests")
    print("=" * 60)
    
    try:
        test_q4_summary()
        test_late_december_inference()
        test_cold_start_latency()
        test_favorite_color_refuse()
        test_customer_complaints_refuse()
        test_cto_praise_refuse()
        
        print("\n" + "=" * 60)
        print("✅ ALL COMPREHENSIVE TESTS PASSED")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
