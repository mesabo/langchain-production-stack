"""LLMOps stack unit tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.stack import count_tokens, CostTracker

def test_count_tokens_positive():
    assert count_tokens("hello world foo bar") > 0

def test_cost_tracker_records():
    t = CostTracker()
    t.record("hello", "world", 100.0)
    assert len(t.calls) == 1
    assert t.calls[0]["n_tokens_in"] > 0
    assert t.calls[0]["n_tokens_out"] > 0

def test_cost_tracker_total_tokens():
    t = CostTracker()
    t.record("hello", "world", 50.0)
    t.record("foo bar baz", "qux quux", 70.0)
    assert t.total_tokens > 0

def test_cost_tracker_summary_keys():
    t = CostTracker()
    t.record("test", "response", 100.0)
    s = t.summary()
    assert "n_calls" in s and "total_tokens" in s and "avg_latency_ms" in s
