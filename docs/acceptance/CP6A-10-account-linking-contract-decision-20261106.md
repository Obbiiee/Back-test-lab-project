# CP6A-10 Account Linking — Implementation Contract

Status: `IMPLEMENTATION_CANDIDATE — DATABASE AND BROWSER ACCEPTANCE PENDING`

## Existing account identity

Email/password and Google users retain their existing internal `users.id`. Workspaces, memberships, Sessions, journals, and financial evidence are never merged or renumbered. The immutable `google_identities` table remains a compatibility mirror; the additive `account_identities` registry is the canonical provider lookup.

## Linking rules

- Email equality alone never links identities or combines accounts.
- Linking starts from an active, verified password account and requires a fresh password check.
- Google identity proof uses the existing one-time browser-bound OAuth state, PKCE, nonce, and verified provider subject.
- A provider subject already owned by another internal user is refused. Each internal user can link at most one identity per provider.
- New email/password identities enter the registry only in the transaction that verifies the email. Only verified existing accounts are backfilled.
- Google-only accounts still cannot set a password through password recovery. Logout and revocation remain scoped to the unchanged internal user ID.

## Migration and rollback

Migration `023_account_identities.sql` is additive. It records the backfill source and timestamp without claiming to know the original email-verification time. Google subject rows remain immutable. Runtime-role privileges are added through the existing explicit grant operation; application startup does not run migrations.

Rolling application code back leaves email/password access intact. The mirrored Google subject mapping is retained but the earlier application may not support Google login for a linked password account. Do not delete or reassign identity rows during rollback.

## Acceptance still required

This code remains a candidate until an isolated PostgreSQL run accepts migration/backfill, concurrent linking conflicts, restricted-role grants, existing Google-login compatibility, and cold recovery. A browser journey must cover reauthentication, verified Google linking, next Google login resolving to the same user ID, and email collision refusal. Live credentials and production databases were not used or changed in this checkpoint.
