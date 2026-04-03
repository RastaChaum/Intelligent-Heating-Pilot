# Workflow Model: One PR Per Feature (Iterative)

**TL;DR**: The repository uses speckit workflow agents only. Each stage writes to the
same feature branch and a different speckit agent performs the critical review.

## Visual Workflow

```text
Issue/Feature
  ↓
[Create branch via speckit.specify]
  ↓
PHASE 1: speckit.specify
  ├─ Creates spec.md
  └─ Reviewed by speckit.clarify

PHASE 2: speckit.plan
  ├─ Creates plan.md and design artifacts
  └─ Reviewed by speckit.checklist

PHASE 3: speckit.tasks
  ├─ Creates tasks.md
  └─ Reviewed by speckit.analyze

PHASE 4: speckit.implement
  ├─ Executes tasks on the same feature branch
  └─ Reviewed by speckit.review

PHASE 5: speckit.docs
  └─ Updates documentation when impacted, then returns to speckit.review if needed
```

## Key Rules

### ✅ **DO**

- **Commit to the SAME branch** all speckit phases
- **Push after each commit** (so PM can see progress)
- **If feedback received**: Refactor and commit more (don't create new PR)
- **Iterate until satisfied** at each gate before moving to next phase

### ❌ **DON'T**

- Don't create new PRs at each phase
- Don't create per-role branches or revive legacy role-based agent flow
- Don't use different commit strategies—be consistent
- Don't skip gates (user needs to validate before continuing)

## Example Flow (Iterative)

### Gate 1: Specification and Plan Review

```text
[Reviewer feedback]: "The boundary between domain and infrastructure is underspecified"
[Producer action]: Refine the artifact, commit, push
[User re-approval]: "Good, proceed to testing"
```

NO new PR created. Just more commits on the same branch.

### Gate 2: Task and Test Coverage Review

```text
[Reviewer feedback]: "Add regression coverage for missing outdoor sensor"
[Producer action]: Update plan/tasks, commit, push
[User re-approval]: "Coverage looks good"
```

Again, same branch, more commits.

### Gate 3: Implementation Review

```text
[Reviewer feedback]: "Implementation violates the documented boundary"
[Producer action]: Fix implementation, commit, push, verify tests still GREEN
[User re-approval]: "Bug fixed, looks good"
```

Same branch, more commits.

### Final Validation

```text
[speckit.review]: Verify code, tests, and documentation impact
[speckit.docs]: Update documentation when needed
[Repository workflow]: Merge once review and governance checks pass
```

Single PR, now closed with merge.

## Commit Messages

Use conventional commits to keep history clear:

```bash
git commit -m "design: add IHeatingCycleCache interface"
git commit -m "design: fix domain layer purity in coordinator"
git commit -m "test(bdd): add heating cycle cache scenario"
git commit -m "test(unit): improve edge case coverage"
git commit -m "feat: implement heating cycle cache logic"
git commit -m "feat: fix heating start bug on cold days"
git commit -m "refactor(app): simplify coordinator orchestration"
```

## Benefits of This Model

| Aspect | Benefit |
| ------ | ------- |
| **Single PR** | Fewer GitHub notifications, cleaner history |
| **Iterative** | Design/test/implementation can be refined without new PRs |
| **Collaborative** | All peer feedback in one PR conversation |
| **Clear scope** | Branch name = issue, not agent action |
| **Simple** | Less overhead, easier to understand flow |

## Common Questions

**Q: What if an early artifact is wrong?**
A: The producing speckit agent refines it on the same branch and the paired reviewer checks it again.

**Q: What if analyze or review finds a coverage hole?**
A: Update tasks or implementation on the same branch, then rerun the paired review stage.

**Q: What if the branch gets out of sync with integration?**
A: Rebase before merge (or merge integration into feature first). Tech Lead handles this during finalization.

**Q: Can agents work in parallel?**
A: Read-only analysis can run in parallel, but artifact production stays sequential so each reviewer validates a stable input.

---

**Reference**: See [agents/README.md](./agents/README.md) for the supported speckit agent set.
