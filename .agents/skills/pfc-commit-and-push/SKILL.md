---
name: pfc-commit-and-push
description: Commit current changes and push to GitHub. Use when the user says "commit", "save", "push", or "sync".
---

# Commit and Push

When committing and pushing:

1. Check for changes:
   ```bash
   git status
   ```
2. If no changes, tell the user there's nothing to commit
3. Review the changes to determine an appropriate commit message
4. Stage relevant files (avoid staging secrets or temporary files):
   ```bash
   git add [specific files]
   ```
5. Commit with an appropriate message following the convention:
   - `task: ...` for task changes
   - `checkin: ...` for check-in data
   - `goal: ...` for goal updates
   - `report: ...` for generated reports
   - `system: ...` for structural changes
6. Push to origin:
   ```bash
   git push
   ```
7. Confirm to the user what was committed and pushed

Never commit `.env` or files containing secrets.
