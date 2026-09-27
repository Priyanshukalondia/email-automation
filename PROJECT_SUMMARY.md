# Laptop Outreach Automation

A Python project for sending personalized laptop-brand outreach emails in a safe, review-first workflow.

## What it does
- Reads your profile and outreach settings from `config.json`
- Loads target companies from `targets.csv`
- Renders personalized email drafts from templates
- Requires manual approval before sending
- Sends only approved rows with rate limiting and duplicate protection
- Logs successful sends to `logs/sent.jsonl`

## Core workflow
1. Update profile details in `config.json`
2. Run `python outreach.py validate`
3. Run `python outreach.py preview`
4. Review generated drafts in `drafts/`
5. Set `approved=yes` only for the rows you want to send
6. Run `python outreach.py send --confirmed`

## Safety
- No sending occurs by default
- Duplicate brand/email pairs are skipped
- SMTP credentials must be provided through environment variables
- The project is intentionally conservative and review-first

## Test status
- Unit tests are in `tests/test_outreach.py`
- Run: `python -m unittest tests/test_outreach.py`
