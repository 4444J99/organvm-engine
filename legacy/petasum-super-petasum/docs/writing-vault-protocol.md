# Writing Vault Protocol

> **Governance**: Commandment #2 (Privacy & Security First), #17 (Non-Destructive Autonomy)
> **Scope**: All confidential and regulated content in the ORGANVM system
> **Version**: 1.0

---

## Why This Exists

Creative and personal writing is the most sensitive content in the system.
Unlike code (which can be regenerated), original writing represents
irreplaceable intellectual property. A single misconfigured AI interaction
can expose years of unpublished work to a cloud provider's training pipeline.

The Writing Vault protocol defines a 9-component secure storage system for
CONFIDENTIAL and REGULATED content, ensuring that sensitive material is
stored securely, accessed intentionally, and never accidentally projected
to cloud AI providers.

---

## The 9 Components

### 1. Canonical Storage

A designated location for all vault-protected content.

- **Location**: Local filesystem under version control (git)
- **Path convention**: `~/Vault/` or `<project>/vault/` (never in a cloud-synced directory)
- **Structure**: Mirror the organ directory structure for organizational consistency
- **Rule**: The vault is the single source of truth for protected content.
  Copies in AI contexts, email, or cloud storage are projections (Layer 2),
  not authoritative.

```
~/Vault/
├── writing/           # Personal and creative writing
│   ├── drafts/
│   ├── published/
│   └── research/
├── financial/         # Financial records (REGULATED)
├── personal/          # Personal data (CONFIDENTIAL)
└── .vault-config.yaml # Vault configuration
```

### 2. Encryption at Rest

All vault content is encrypted when not actively being used.

- **Mechanism**: GPG-encrypted git (git-crypt) or filesystem encryption (FileVault/LUKS)
- **Minimum**: macOS FileVault (full-disk encryption) is the baseline
- **Recommended**: git-crypt for per-file encryption within git repos
- **Key management**: GPG key stored in 1Password or hardware security key
- **Rule**: Unencrypted vault content must never exist on unencrypted storage

### 3. Access Controls

Who and what can access vault content.

- **Human access**: Owner only. No shared access without explicit grant.
- **Agent access**: Interactive agents may read vault content during
  CONFIDENTIAL sessions. Non-interactive agents are prohibited from
  vault access unless explicitly authorized in the session manifest.
- **Cloud sync**: Vault directories MUST be excluded from Dropbox,
  iCloud, Google Drive, and any cloud sync service.
- **Backup**: Backblaze B2 with client-side encryption, or local
  encrypted backup only.

```yaml
# .vault-config.yaml
access:
  owner: "@4444j99"
  agents:
    interactive: read   # Can read during CONFIDENTIAL sessions
    non_interactive: deny  # Cannot access vault
  cloud_sync: deny       # Excluded from all cloud sync
  backup:
    service: backblaze-b2
    encryption: client-side
```

### 4. Versioning

All vault content is version-controlled with full history.

- **Mechanism**: Git (local repo, not pushed to GitHub for private content)
- **Commits**: Standard conventional commit format
- **Branches**: `main` only — no feature branches for vault content
- **History**: Never rewrite history (`git rebase`, `git filter-branch`).
  Deleted content should remain in git history for recovery.
- **Tags**: Date-based tags for significant versions (`v2026-03-08`)

### 5. Backups

Vault content has a dedicated backup strategy separate from general backups.

- **Frequency**: Daily (automated) + on-demand before risky operations
- **Destinations**: At least 2 independent backup locations
- **Encryption**: All backups encrypted before leaving the local machine
- **Verification**: Monthly backup restoration test
- **Retention**: Indefinite for creative writing; per-regulation for REGULATED data

### 6. Retention and Deletion

Clear rules for how long content is kept and how it's destroyed.

- **Creative writing**: Indefinite retention (never auto-delete)
- **Financial records**: 7 years (legal minimum in most jurisdictions)
- **Personal data**: Until purpose is fulfilled + 30 days
- **AI interaction records**: 1 year for CONFIDENTIAL, per-regulation for REGULATED
- **Deletion method**: Secure delete (overwrite) for files; `git filter-branch`
  for removing from history (only when legally required)
- **Deletion audit**: Log what was deleted, when, why, and by whom

### 7. Audit Logging

Every access to vault content is logged.

- **What's logged**: File path, access type (read/write), timestamp, accessor
  (human or agent ID), session context
- **Log location**: `~/Vault/.audit/access.jsonl` (append-only)
- **Rotation**: Monthly log rotation, compressed archives retained per backup policy
- **Review**: Monthly review of access logs for unexpected patterns

```jsonl
{"ts":"2026-03-08T14:30:00Z","file":"writing/drafts/novel-ch3.md","action":"read","accessor":"claude-code","session":"sess_abc123","classification":"confidential"}
{"ts":"2026-03-08T14:35:00Z","file":"writing/drafts/novel-ch3.md","action":"write","accessor":"@4444j99","session":"interactive","classification":"confidential"}
```

### 8. Incident Response

What to do when vault security is compromised.

**Incident levels:**

| Level | Description | Response Time |
|-------|-------------|---------------|
| **P1 — Breach** | Vault content exposed to unauthorized party | Immediate |
| **P2 — Leak** | Content accidentally projected to cloud provider | 4 hours |
| **P3 — Policy violation** | Classification rule violated, no exposure | 24 hours |

**Response procedure:**

1. **Contain**: Stop the process that caused the incident
2. **Assess**: Determine what was exposed, to whom, and scope
3. **Remediate**: Rotate credentials, revoke access, delete projections
4. **Record**: Log the incident in `~/Vault/.audit/incidents.jsonl`
5. **Prevent**: Update controls to prevent recurrence

**For P2 (cloud provider exposure):**
- Check provider's data retention policy
- Submit data deletion request if available
- Verify opt-out of training is active
- Document in incident log

### 9. AI Interaction Records

Every AI interaction involving vault content is recorded.

- **What's recorded**: Date/time, AI tool/provider, model version,
  what was projected (summary, not full content), what output was produced,
  whether output was reintegrated
- **Format**: Structured JSONL alongside the vault content
- **Purpose**: Provenance tracking for Layer 4 reintegration decisions
- **Retention**: Same as the content's retention period

```jsonl
{"ts":"2026-03-08T14:30:00Z","tool":"ollama","model":"llama3.2:3b","projected":"chapter 3 draft (2,400 words)","output":"editorial suggestions (800 words)","reintegrated":true,"reviewer":"@4444j99"}
```

---

## Vault Setup Checklist

- [ ] Create `~/Vault/` directory structure
- [ ] Enable FileVault (macOS) or LUKS (Linux) full-disk encryption
- [ ] Initialize git repo in vault directory (local only, no remote push)
- [ ] Exclude vault directory from Dropbox/iCloud/Google Drive sync
- [ ] Configure backup to encrypted destination
- [ ] Create `.vault-config.yaml` with access controls
- [ ] Create `.audit/` directory for access and incident logs
- [ ] Add vault paths to `.gitignore` in any cloud-synced parent directories
- [ ] Test backup restoration
- [ ] Document vault location in personal secure notes (1Password)

---

## Integration with ORGANVM

### Classification Routing

The Writing Vault stores content classified as CONFIDENTIAL or REGULATED.
When vault content is projected to an AI (Layer 2), the sensitivity-based
router in `agentic-titan/adapters/router.py` enforces local-only processing.

### Non-Interactive Agents

Per the safety protocol (`docs/NON-INTERACTIVE-AGENT-SAFETY.md`), non-interactive
agents have no vault access by default. Interactive sessions may read vault content
during CONFIDENTIAL classification sessions.

### Reintegration

AI output that modifies vault content follows the standard reintegration
rules (Layer 4 of the AI interaction model): human review, diff check,
provenance annotation.

---

## Relationship to Other Governance

| Document | Relationship |
|----------|-------------|
| `ai-interaction-model.md` (F-36) | Vault is Layer 1 (source of truth) |
| `data-classification.md` (F-37) | Vault stores Tier 3 (CONFIDENTIAL) and Tier 4 (REGULATED) |
| `NON-INTERACTIVE-AGENT-SAFETY.md` | Agents denied vault access by default |
| `agentic-titan/adapters/router.py` | Enforces local-only routing for vault content (F-24) |
| Commandment #2 | Privacy & Security First |
| Commandment #17 | Non-Destructive Autonomy — no permanent deletion |

---

## References

- **AI Interaction Model**: `docs/ai-interaction-model.md` — 4-layer data flow
- **Data Classification**: `docs/data-classification.md` — classification tiers
- **Safety Protocol**: `docs/NON-INTERACTIVE-AGENT-SAFETY.md` — agent constraints
- **Sensitivity Router**: `agentic-titan/adapters/router.py` — code enforcement
- **Pseudonymization**: F-39 (future) — redaction guidelines for projected content
- **Commandments**: `COMMANDMENTS.md` — #2, #17
