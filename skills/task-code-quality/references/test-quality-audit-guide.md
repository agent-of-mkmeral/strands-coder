# Test Quality Audit Reference Guide

> **Used by:** `task-code-quality` (Phase 3)
> **Purpose:** Detailed procedures for critiquing existing tests to determine if they provide real assurance or false confidence.

## Principles

1. **Tests exist to prove behavior, not to exist.** A test that passes but doesn't actually validate anything is worse than no test — it creates false confidence that masks real risk.
2. **Intent vs Reality.** What a test claims to verify (via its name and docstring) and what it actually verifies (via its assertions) are often two different things. Your job is to expose every gap.
3. **Prove, don't opine.** Every critique MUST cite the specific test code, the specific source code, and the specific gap between them.
4. **Prioritize by risk.** Focus on tests for code that could cause real damage (data loss, security holes, silent failures) before nitpicking edge cases in utility functions.

## Critical Analysis Framework

### Intent vs Reality Analysis

For each test, determine if it tests what it claims to test:

- Read each test's name, docstring, and assertions
- Determine what the test CLAIMS to verify (from its name/docstring)
- Determine what the test ACTUALLY verifies (from its assertions and setup)
- Flag every gap between claim and reality
- Categorize gaps:
  - **Misleading**: Test name says one thing, assertions check something else entirely
  - **Incomplete**: Test name describes a scenario but assertions only partially validate it
  - **Trivial**: Test exists but assertions are so weak they'd pass with broken code
  - **Tautological**: Test essentially tests that the mock returns what the mock was told to return

### Coverage Gap Analysis

Identify what's NOT tested that should be:

- Identify untested code paths by reading the source and mapping against tests:
  - Error handling branches (`try/except`, `if error:`, `raise`)
  - Conditional branches (`if/elif/else`)
  - Default parameter behaviors
  - Edge case inputs (empty, None, zero, negative, boundary, unicode, very large)
- Identify untested state transitions:
  - What happens when operations are called in unexpected order?
  - What happens when the same operation is called twice?
  - What happens during concurrent access?
- Identify untested integration points:
  - API boundaries between components
  - Serialization/deserialization round-trips
  - External service failure modes

### Test Quality Red Flags

#### Mock Abuse
- Tests that mock so much they test nothing real (mock the input, mock the processing, mock the output — what's left?)
- Tests where the mock setup is more complex than the code under test
- Tests that verify mock interactions instead of behavior ("assert mock.called" without checking the result)
- Mocked responses that don't match real response shapes from the service

#### Assertion Weakness
- Tests with no assertions (just "doesn't raise" — which passes for broken code too)
- Tests with trivial assertions (`assert result is not None` — nearly everything passes this)
- Tests that assert on type only (`isinstance`) when they should assert on value
- Tests that use `assert True` or `assert len(result) > 0` as a proxy for real validation
- Tests that check string containment (`"error" in str(result)`) instead of specific error types/messages

#### False Positive Risk
- Tests that would pass even if the function returned a hardcoded value
- Tests that would pass even if the function did nothing
- Tests where removing the implementation doesn't cause the test to fail
- Tests that rely on implementation details that could change (method call order, internal variable names)

#### Test Isolation Issues
- Tests that depend on execution order
- Tests that share mutable state (module-level variables, class variables)
- Tests that depend on environment variables without proper setup/teardown
- Tests that leak resources (open files, running threads, patches not cleaned up)

## Strands SDK-Specific Patterns

### Common Patterns to Watch For
- Tests that mock `model` but never verify the model was called with correct parameters
- Tests that mock tool execution but don't verify tool results are properly handled
- Tests that check `Agent()` creation succeeds but don't verify the agent actually works
- Tests that verify event emission but don't verify event content/ordering
- Tests that mock `BedrockModel`/`LiteLLMModel` responses but use unrealistic response shapes
- Tests of `system_prompt` that verify string presence but not behavioral impact
- Tests of tool loading that verify tools are imported but not that they're callable with expected signatures
- Tests of session management that verify save/load but not content integrity across cycles

### Coverage Gaps to Check
- Tool execution error handling (tool raises, tool returns malformed result, tool times out)
- Model provider fallback/retry behavior
- Session state corruption or loss scenarios
- Agent cycle limits and infinite loop protection
- Token counting edge cases (near-limit, over-limit, zero)
- Multi-turn conversation state management
- MCP server connection/disconnection handling
- Hook/callback invocation ordering and error isolation
- Plugin lifecycle (load, activate, deactivate, error during activation)
- Streaming vs non-streaming response handling divergence

### SDK-Specific Quality Issues
- Tests that patch `strands.Agent.__call__` — this bypasses the entire agent loop
- Tests that use `MagicMock(spec=Agent)` but never verify the mock's behavior matches the real Agent
- Tests that verify tool registration but not tool invocation
- Tests that check `system_prompt` string but not how it's used in model calls
- Tests that mock `boto3` so aggressively they wouldn't catch real AWS SDK breaking changes
- Tests of async/streaming code that use synchronous mocks (hiding timing-dependent bugs)

### Use Case Alignment Checks
- Happy path with realistic inputs
- Common mistake patterns (wrong types, missing required fields, typos in config)
- Migration scenarios (old API → new API if backward compatibility is claimed)
- Multi-step workflows (not just individual function calls in isolation)
- Agent with tools actually orchestrating a multi-turn conversation
- Tool returning unexpected types or large payloads
- Model returning malformed/truncated responses
- Agent hitting max recursion / max tokens during execution
- Session restore after partial conversation

## Reporting Format

```markdown
**TL;DR**: [CONFIDENT — tests provide real assurance | CONCERNED — significant gaps found | FALSE CONFIDENCE — tests are passing but proving little].

<details>
<summary>🔍 Devil's Advocate Test Review</summary>

**Scope**: [What tests and code were reviewed]
**Tests reviewed**: [count]
**Findings**: [count by severity: N critical, N major, N minor]

### Summary Verdict
[2-3 sentence harsh-but-fair assessment of overall test quality]

### Critical Findings
<details>
<summary>Finding 1 — [Severity]: [one-line description]</summary>

**Test**: `test_file.py::TestClass::test_method`
**Claims to verify**: [what the test name/docstring says]
**Actually verifies**: [what the assertions really check]
**Gap**: [specific problem]
**Risk**: [what could go wrong in production]
**What good looks like**: [concrete suggestion]

</details>

### Missing Test Coverage
| Priority | Scenario | Why It Matters |
|----------|----------|----------------|
| Critical | [scenario] | [risk] |

### Recommendations
1. [Highest priority fix]
2. [Second priority fix]

</details>
```

## Key Distinction from Adversarial Testing

| Skill | Focus | Output |
|-------|-------|--------|
| **Adversarial Testing** | Writes NEW tests to break code | Failing test artifacts |
| **Test Quality Audit** (this) | Critiques EXISTING tests for effectiveness | Audit report on test quality |

The adversarial tester asks: "Can I break this code?"
The test quality auditor asks: "Do these tests actually prove anything?"
