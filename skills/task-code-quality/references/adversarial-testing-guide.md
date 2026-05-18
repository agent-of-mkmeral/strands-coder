# Adversarial Testing Reference Guide

> **Used by:** `task-code-quality` (Phase 2)
> **Purpose:** Detailed procedures for breaking code changes in PRs. Every finding must include a runnable artifact.

## Principles

1. **Prove, don't opine.** Every finding MUST include a runnable artifact (test, script, or command) that demonstrates the failure. "I think this might break" is not a finding.
2. **Spec over implementation.** Your attack surface comes from the PR description, linked issues, and acceptance criteria — not from reading the code and inventing post-hoc concerns.
3. **Adversarial by design.** Assume the code is wrong until proven otherwise. Your incentive is to find what's broken, not to confirm it works.
4. **Artifacts are the deliverable.** Your output is a set of pass/fail artifacts. If all pass, the code survived your review. If any fail, they speak for themselves.
5. **No overlap with the reviewer.** You don't comment on naming, style, architecture, or documentation. That's the reviewer's job. You break things.

## Understanding the Attack Surface

Before writing any tests, extract the attack surface from the PR:

- You MUST read the PR description and linked issue thoroughly
- You MUST use `use_github` with a GraphQL query to identify all changed files and their scope
- You MUST extract explicit and implicit acceptance criteria from the PR description
- You MUST identify the public API surface being added or modified
- You MUST categorize the change type: new feature, bugfix, refactor, dependency change, config change
- You MUST note any claims the author makes ("this handles X", "backward compatible", "no breaking changes")
- Document your attack surface as a checklist:
  - Input boundaries and edge cases
  - Error paths and failure modes
  - Concurrency and ordering assumptions
  - Backward compatibility claims
  - Security-sensitive areas (auth, credentials, user input, serialization)
  - Integration points with external systems

## Test Generation Categories

### 1. Edge Case Testing

Target the boundaries of inputs, states, and configurations.

- Write tests for boundary values: empty inputs, None/null, maximum sizes, negative numbers, unicode, special characters
- Write tests for type confusion: passing wrong types where the code doesn't explicitly validate
- Write tests for missing or malformed configuration
- Write tests that exercise optional parameters in combinations the author likely didn't consider
- All tests MUST follow the project's test patterns (pytest, directory structure mirroring `src/`)
- All tests MUST be runnable with `hatch test` or `pytest` directly
- Name test files with the prefix `test_adversarial_` to distinguish them from the author's tests

### 2. Failure Mode Testing

Target error handling, recovery, and degraded operation.

- Write tests that force exceptions in dependencies (mock failures in I/O, network, model calls)
- Write tests for timeout and cancellation scenarios if the code involves async or long-running operations
- Write tests that verify error messages are informative (not swallowed, not leaking internals)
- Write tests for resource cleanup on failure (files closed, connections released, locks freed)
- Test what happens when the code is called in an unexpected order or state

### 3. Contract Verification

Verify the code actually fulfills the claims in the PR description.

- Write at least one test per acceptance criterion extracted from the PR
- Write tests that verify backward compatibility if the author claims it
- Write tests that verify the public API contract matches documentation/docstrings
- Test that default parameter values produce the documented default behavior
- If the PR claims "no breaking changes," write a test that uses the old API surface and verify it still works

### 4. Security Probing

Target security-sensitive patterns. Skip this section if the change has no security surface.

- Check for hardcoded credentials, API keys, or tokens in the diff
- Test for injection vulnerabilities if the code constructs commands, queries, or prompts from user input
- Test for path traversal if the code handles file paths
- Test for unsafe deserialization if the code loads data from external sources
- Verify that sensitive data is not logged or exposed in error messages
- Check that any new dependencies don't introduce known vulnerabilities (check version pinning)

### 5. Concurrency and Race Conditions

Target timing-dependent behavior. Skip if the change is purely synchronous and single-threaded.

- Write tests that exercise concurrent access to shared state if applicable
- Write tests for async code that verify proper await chains and cancellation handling
- Test for deadlocks in code that acquires multiple locks or resources
- Use `threading` or `asyncio` test patterns to simulate concurrent callers

## Execution and Evidence Collection

- Run all adversarial tests and record results
- Capture the full output (stdout, stderr, tracebacks) for every failing test
- Verify that each failing test is a genuine issue, not a test bug — re-run failures to confirm they're deterministic
- Categorize each finding:
  - **Bug**: The code produces incorrect results or crashes
  - **Unhandled Edge Case**: The code doesn't account for a valid input or state
  - **Contract Violation**: The code doesn't match what the PR/docs claim
  - **Security Issue**: The code has a security vulnerability
  - **Flaky Behavior**: The code produces inconsistent results across runs
- Discard any test that fails due to your own test code being wrong — fix the test or drop it
- Do NOT report speculative issues without a failing artifact

## Reporting Format

Each finding MUST be wrapped in a `<details>/<summary>` block:

```markdown
<details>
<summary>Finding N — [Category] ([Severity]): One-line description</summary>

**Reproduction**:
[Minimal code snippet or command that demonstrates the failure]
**Observed behavior**: [What actually happens]
**Expected behavior**: [What should happen based on the spec/PR description]
**Fix**: [Suggested fix if obvious]
**Artifact**: [Link to or inline the failing test]

</details>
```

Summary format:
```markdown
**TL;DR**: [PASS — no issues found | FAIL — N issues found]. [One sentence scope summary].

<details>
<summary>Adversarial Testing Report</summary>

**Scope**: [Brief description of what was tested]
**Tests written**: [count]
**Tests passing**: [count]
**Tests failing (findings)**: [count]

| # | Category | Severity | Description |
|---|----------|----------|-------------|
| 1 | Bug | Critical | [one-line description] |

[Individual findings in nested <details> blocks]

<details>
<summary>What Survived (N tests passed)</summary>

[List of areas that survived testing]

</details>

</details>
```

## Troubleshooting

### Large PRs
- Focus on the public API surface and integration points first
- Prioritize security-sensitive and error-handling paths
- Skip internal refactors that don't change behavior

### Unfamiliar Codebase
- Read `AGENTS.md` and test fixtures in `tests/fixtures/` to understand mocking patterns
- Look at existing tests for the modified files to understand expected patterns
- Use `mocked_model_provider.py` and other test fixtures when writing adversarial tests

### Flaky Tests
- Run failing tests 3 times before reporting
- If a test fails intermittently, categorize as "Flaky Behavior" and note the failure rate
- Ensure your tests don't depend on execution order or global state
