# Issue Refinement Reference Guide

> **Used by:** `task-implementer` (Step 0 triage), `task-research`
> **Purpose:** Detailed procedures for analyzing, clarifying, and refining issues before implementation.

## Analysis Framework

### Feature Request Analysis

- Check for existing documentation in: `AGENTS.md`, `CONTRIBUTING.md`, `README.md`
- Investigate any links provided in the feature request
- Identify the list of functional requirements and acceptance criteria
- Determine the appropriate file paths and programming language
- Identify potential gaps or inconsistencies in requirements
- Note any technical specifications mentioned
- Identify missing or ambiguous requirements
- Consider edge cases and implementation challenges
- Distinguish between clear requirements and assumptions

### Research Existing Patterns

- Identify the main programming languages and frameworks used
- Search the current repository for relevant code, patterns, and information related to the task
- Locate relevant existing code that relates to the feature request
- Understand the current architecture and design patterns
- Note any existing similar features or related functionality
- Create a dependency map showing how the new feature will integrate
- Note the identified implementation paths

### Scope Assessment

- Identify the work required to implement the feature
- Review the current state of the repository and identify potential issues during implementation
- Determine if the task is small enough for a single PR (can a single developer complete it in about a week?)
- Consider test implementation complexities
- Note if any GitHub workflows are needed or changes to existing workflows
- Note any concerns in your progress file

## Clarification Process

### When to Ask Questions
- Skip clarification if the task is already in an implementable state given your research
- Ask questions if you've identified genuine ambiguities that would affect implementation correctness

### Question Guidelines
- Clarify if GitHub workflow changes are needed (suggest `.github_temp` directory since you may not have permission to push to `.github`)
- Ask about ambiguous functionality
- Clarify technical implementation details
- Ask about user experience expectations
- Ask for input on non-obvious edge cases
- Clarify questions regarding information from provided links
- Ask about non-functional requirements not explicitly stated
- Group related questions logically
- Include questions about integration with existing systems
- Ask about performance and scalability requirements

### Breaking Down Large Tasks
- Provide justification for why an issue should be broken down
- Suggest how the issue should be split into smaller feature requests
- Number sub-tasks based on parent task number (e.g., parent task #4 → sub-tasks 4.1, 4.2, 4.3)
- Identify dependencies between sub-tasks
- Determine the order of implementation

### Task Description Update Format

When updating an issue with refined requirements:

```markdown
# Overview
[Brief description of the feature]

## Implementation Requirements
Based on clarification discussion and repository analysis:

### Technical Approach
- **Framework Integration**: [Details]
- **Database Changes**: [Details if applicable]
- **Architecture**: [Details]

### Functional Requirements
- [Requirement 1]
- [Requirement 2]

### Files to Modify
- `path/to/file.py` - [What changes]
- `path/to/other.py` - [What changes]

### Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Integration tests pass]
- [ ] [Existing functionality remains intact]
```

## Iteration Limits
- Maximum 5 rounds of clarifying questions to prevent endless loops
- After 5 rounds, proceed with best available understanding and document assumptions
