# CP6A-10 Account Linking — Contract Decision Required

Status: `HOLD_OWNER_DECISION_REQUIRED_BEFORE_IDENTITY_MIGRATION`

## Verified current contract

- `backend/infrastructure/migrations/012_google_identity.sql` defines `btl.google_identities` with `subject` as primary key and `user_id` as `UNIQUE`; the table has a database trigger refusing UPDATE, DELETE, and TRUNCATE.
- The same migration freezes `users.password_enabled` transitions behind a trigger.
- `backend/identity/google_store.py` resolves Google login by immutable provider subject. If the subject is new and its verified email already belongs to a password account, it returns `GOOGLE_ACCOUNT_CONFLICT`; it does not merge by email.
- `backend/identity/google.py` explicitly describes the opt-in flow as having no email linking.
- Existing workspaces, memberships, Sessions, and financial records use the internal `users.id` / workspace identity. They must remain unchanged.

## Minimal safe design proposal

Add `btl.account_identities(provider, provider_subject, user_id, verified_at, created_at)` with:

- `UNIQUE(provider, provider_subject)` and `UNIQUE(provider, user_id)` for the currently supported one-identity-per-provider rule.
- Internal `users.id` as the canonical account identity; identity linking never merges or renumbers users, workspaces, Sessions, or financial evidence.
- One-time backfill from verified, password-enabled accounts (normalized verified email as the email-login subject) and existing Google subject mappings. Existing Google rows remain byte-for-byte immutable; the new table becomes the single lookup authority only after the application cutover is explicitly accepted. Unverified email addresses must not be backfilled as login identities.
- Linking requires an authenticated existing account, recent reauthentication, a purpose-bound OAuth state/nonce/PKCE flow, verified provider subject, and a transaction that locks the user and identity keys. Email equality is never sufficient proof or a merge signal.
- Any provider subject already linked to another account returns a conflict. It never moves the identity or combines accounts. Logout/revocation continues to revoke sessions by the unchanged internal user ID.

## Why implementation is paused here

The current Google login authority is an immutable one-subject-to-one-user table. A linkable account-identity registry requires changing the login lookup authority and handling uniqueness across the old and new mappings. Keeping the existing table as an independent authority would leave two competing mappings and would not safely support a second Google identity. This is an identity-contract change even if implemented with an additive table; it needs an owner decision before a migration or authentication cutover.

## Owner decision requested

Authorize the proposed additive identity registry and application lookup cutover, including the one-time additive backfill and rollback policy, or keep Google account linking out of Product V1. No identity migration, table creation, backfill, provider-link callback, or auth behavior change has been made in this checkpoint.
