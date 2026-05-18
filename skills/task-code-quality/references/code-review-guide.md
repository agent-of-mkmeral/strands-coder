# Code Review Reference Guide

> **Used by:** `task-code-quality` (Phase 1)
> **Purpose:** Detailed procedures for reviewing code changes in PRs — structural analysis, API bar raising, quality checks, and documentation verification.

## Structural Review

Analyze the overall structure and architecture of the changes:

- Review the file organization and directory structure
- Check if new files follow existing naming conventions
- Verify that changes align with the project's architectural patterns
- Identify any potential breaking changes
- Check for proper separation of concerns

## API Bar Raising Review

If the PR introduces or modifies public APIs, evaluate the API design from a customer perspective:

- Check if the PR has `needs-api-review` or `completed-api-review` labels
- Verify the PR includes API documentation in the description:
  - Expected use cases for the new feature
  - Example code snippets demonstrating usage
  - Complete API signatures with default parameter values
  - Module exports (what's exported from each module)
- Evaluate the API against SDK tenets (https://github.com/strands-agents/docs/blob/main/team/TENETS.md) and decision records (https://github.com/strands-agents/docs/blob/main/team/DECISIONS.md)
- Verify the API addresses documented use cases
- Check if default parameters/behavior represent the most common usage
- Assess the level of abstraction and extensibility:
  - What is customizable and what is not?
  - Is it the proper level of abstraction?
- Identify use cases that are not addressed and question why
- Flag if the PR requires API review but lacks the `needs-api-review` label for:
  - New public classes or abstractions customers will use
  - New primitives or frequently-used functionality
  - Changes to existing public API contracts

## Code Quality Checklist

- Check for language-specific best practices as defined in repository guidelines
- Verify code is readable with clear variable/function names and logical structure
- Check that code is maintainable with modular design and loose coupling
- Check for code complexity and suggest simplifications
- Identify unclear or confusing code patterns
- Verify proper error handling
- Check for potential performance issues
- Verify design decisions are documented (why certain patterns were chosen, alternatives considered, tradeoffs made)

## Testing Review

- Verify that new functionality has corresponding tests
- Check that tests follow the patterns defined in repository documentation
- Ensure tests are in the correct directories as specified in guidelines
- Check for proper test organization and naming
- Identify missing edge cases or error scenarios
- Verify integration tests are included when appropriate

## Documentation Review

- Verify documentation exists for all public APIs as required by repository guidelines
- Check that documentation is clear, helpful, and concise
- Check the PR description for a "Documentation PR" section
- Verify any linked documentation PR points to `https://github.com/strands-agents/docs/pull/...`
- If no documentation PR is linked, check for a justification explaining why updates are not required
- Valid justifications include: internal refactor with no public API changes, test-only changes, CI/config changes
- If neither a valid documentation PR link nor a justification is present → blocking issue (Request Changes)

## Inline Comment Best Practices

- Use `suggestion` blocks with exact fixes wherever possible
- Explain the "why" for each suggestion
- Do NOT comment on style/formatting that linters would catch
- Focus on substantive issues: bugs, security, performance, maintainability
- Skip nits (comment wording, bracket position, filename conventions)
- Categorize feedback:
  - **Critical**: Must be fixed (security, breaking changes, major bugs)
  - **Important**: Should be fixed (quality, maintainability, standards)
  - **Suggestion**: Nice to have (optimizations)
- Limit to 10-15 comments per review to avoid overwhelming the author
- Do NOT add inline comments praising good coding practices

## Review Submission Format

```markdown
**Assessment**: [✅ Approve | ⚠️ Request Changes | 💬 Comment]

[Brief high-level summary - 1-2 sentences max. This is the ONLY expanded text.]

<details>
<summary>Review Details</summary>

- **[Category]**: [High-level pattern or theme]
- **[Category]**: [High-level pattern or theme]

</details>
```

## Focus Area Priorities

1. **Functionality**: Does the code work as intended? Edge cases and error conditions handled?
2. **Readability**: Clear with descriptive names and logical structure?
3. **Maintainability**: Modular, loosely coupled, easy to modify?
4. **Security**: Vulnerabilities or data exposure risks?
5. **Performance**: Bottlenecks or inefficient algorithms?
6. **Testing**: Comprehensive coverage including edge cases?
7. **Language Best Practices**: Follows language-specific best practices per repo guidelines?
8. **Design Documentation**: Design decisions, alternatives, and tradeoffs documented?
