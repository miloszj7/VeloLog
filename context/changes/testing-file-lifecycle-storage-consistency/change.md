---
change_id: testing-file-lifecycle-storage-consistency
title: File lifecycle and storage/row consistency test coverage
status: new
created: 2026-08-30
updated: 2026-08-30
archived_at: null
---

## Notes

Open a change folder for rollout Phase 2 of context/foundation/test-plan.md: "File lifecycle and storage/row consistency".
Risks covered: #1 (Deleting or replacing a trip's track leaves its file on the volume forever — or removes a file that is still in use), #3 (A trip's row survives but its track becomes unreachable). Test types planned: integration (commit-callback aware), management-command.
Risk response intent:
- #1: Prove every delete and replace path reclaims exactly what it should — asserted after commit, not before. Challenge that a passing deletion test proves deletion at all (a post-commit side effect asserted before the commit passes vacuously). Avoid asserting a receiver fired instead of asserting the file is gone.
- #3: Prove a trip whose file is missing from storage renders a deliberate error state and never claims success. Challenge that statistics rendering means the file is present (statistics are stored columns, deliberately decoupled from the file). Avoid only exercising the happy path where row and file agree.
After creating the folder, follow the downstream continuation rule: run /10x-research next.
