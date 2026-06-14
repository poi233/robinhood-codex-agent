# Repo Skills Setup

This repo carries trading-analysis skills under `.agents/skills/`. The scheduled technical research
prompt can use these skills as analysis context, but the skills are advisory only and cannot
authorize trades.

## Skills

- `chan-structure-trading`
- `brooks-trading-range-price-action`
- `equity-fundamentals-analysis`
- `trading-research-casebook-maintenance`

## Install

```bash
./src/scripts/skills/install_repo_skills.sh
./src/scripts/skills/verify_repo_skills.sh
```

By default the installer copies skills into both:

```text
$HOME/.agents/skills
$HOME/.codex/skills
```

Override targets with a colon-separated list:

```bash
REPO_SKILL_TARGETS="$HOME/.codex/skills" ./src/scripts/skills/install_repo_skills.sh
```

## Source Of Truth

```text
.agents/skills/
```

Installed skills are real copies, not symlinks. Re-run the installer after editing repo skills.

## Validation

```bash
./src/scripts/skills/verify_repo_skills.sh
python3 -m unittest tests.test_install_repo_skills tests.test_technical_signal_schema -v
```

Expected results:

- Every installed skill has `SKILL.md`.
- Reference and casebook directories are present when the repo source has them.
- Prompt wiring tests confirm technical and premarket prompts reference the generated signal files.
