"""AgentFlow tool registry tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.graph import build_math_registry

def test_registry_add():
    r = build_math_registry()
    assert abs(r.dispatch("add", {"a": 3.0, "b": 4.0}) - 7.0) < 1e-9

def test_registry_sqrt():
    r = build_math_registry()
    assert abs(r.dispatch("sqrt", {"x": 16.0}) - 4.0) < 1e-9

def test_registry_lookup():
    r = build_math_registry()
    fact = r.dispatch("lookup", {"topic": "pi"})
    assert "3.14" in fact

def test_registry_all_tools():
    r = build_math_registry()
    assert len(r.all()) == 5

def test_dispatch_unknown():
    r = build_math_registry()
    result = r.dispatch("nonexistent", {})
    assert "ERROR" in result
