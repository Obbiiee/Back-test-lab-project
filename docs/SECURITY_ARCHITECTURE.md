# Backtest Lab — Security Architecture

> **Status:** Living security architecture / security contract  
> **Purpose:** Define security boundaries that future Backtest Lab implementation must preserve as the product evolves from local software to multi-user SaaS.  
> **Authority:** This document is architectural guidance and does not authorize implementation or change the current phase.

# 1. Security North Star

> **Security is a system property, not a launch-day feature.**

Backtest Lab must protect:
- user identity and sessions;
- workspace isolation;
- strategies, experiments, trades and journals;
- Experiment Passports and research evidence;
- market/research datasets;
- billing and entitlement state;
- payment integration metadata;
- AI context;
- API/provider secrets;
- backups and operational infrastructure.

Security must scale with the product without forcing the research core to be rewritten.

# 2. High-Level Security Boundaries

    Internet
       ↓
    Edge Protection
    TLS / rate limits / optional WAF-CDN
       ↓
    Web / API
       ↓
    Authentication
       ↓
    Authorization + Tenant Isolation
       ↓
    Application Services
       ├── PostgreSQL
       ├── Object Storage
       ├── Research Workers
       ├── Billing / Entitlements
       ├── AI Gateway
       └── Integration Layer / CRM
              ↓
         Encrypted / controlled backups

Defense in depth: no single boundary is assumed perfect.

# 3. Authentication

Use a mature authentication implementation/provider/library rather than inventing cryptography.

Requirements for production design:
- secure password hashing when passwords are owned by Backtest Lab;
- secure OAuth/OIDC flow where external login is supported;
- short-lived or appropriately scoped sessions/tokens;
- secure cookie configuration where cookies are used;
- session invalidation/revocation strategy;
- CSRF protection when architecture requires it;
- login rate limiting / abuse protection;
- account recovery designed against takeover;
- optional stronger authentication/MFA when product maturity warrants it.

Never store plaintext passwords.

# 4. Authorization & Tenant Isolation

Authentication answers **who are you?**  
Authorization answers **are you allowed to access this resource?**

Every private resource must be scoped through ownership/membership, conceptually:

    User
      ↓
    Workspace Membership
      ↓
    Workspace
      ↓
    Strategy / Protocol / Experiment / Journal / Report

Server-side authorization must protect resources even when a user manually changes IDs, URLs or API requests.

Never rely on:
- hidden frontend buttons;
- client-provided workspace IDs without verification;
- sequential/unguessable IDs as the only protection.

High-priority automated security tests must attempt cross-tenant access:
- User A reading User B experiment;
- modifying another workspace strategy;
- downloading another user's report;
- requesting another tenant's AI context;
- accessing another user's research job/result.

Expected result: deny by default.

# 5. Data Classification

Candidate classes:

## Public
Marketing pages, public documentation and intentionally published research.

## Internal
Non-secret operational metadata.

## Private User Data
Strategies, experiments, trades, journals, reports, workspace information and private imports.

## Sensitive Operational Data
Billing records, authentication/session metadata, audit logs and security events.

## Secrets
API keys, database credentials, signing secrets, payment webhook secrets, encryption keys and provider credentials.

Secrets must never be committed to Git.

# 6. Encryption & Transport

Production traffic must use HTTPS/TLS.

Sensitive persistence should use encryption at rest where supported and appropriate, including backups.

Do not expose PostgreSQL, Redis/queue systems, worker control surfaces or internal admin interfaces directly to the public internet unless explicitly required and securely controlled.

# 7. Database Security

Principles:
- least-privilege database credentials;
- parameterized queries / safe ORM patterns;
- schema migrations are version-controlled;
- production credentials separate from development;
- no public DB exposure by default;
- connection limits/pooling where appropriate;
- authorization remains application-aware even when database controls exist;
- audit important administrative/data mutations where justified.

Tenant-isolation mechanisms may evolve, but the invariant remains: one tenant must not obtain another tenant's private data.

# 8. Object Storage & File Security

For imported datasets, exports, screenshots and reports:
- validate allowed file type/content;
- enforce size limits;
- use randomized/internal storage identifiers;
- prevent path traversal;
- avoid executing uploaded content;
- use time-limited/private access URLs where appropriate;
- verify authorization before generating download access;
- scan or isolate risky file types if later supported.

Large files should be portable across storage providers without weakening authorization.

# 9. API Security

All non-public APIs should enforce appropriate authentication and authorization.

Use:
- request validation;
- bounded payload sizes;
- rate limits;
- pagination/limits on expensive queries;
- safe error responses that do not leak secrets;
- idempotency for operations that may be retried;
- timeouts and resource limits;
- explicit permissions for administrative endpoints.

Do not expose internal stack traces or credentials to users.

# 10. Abuse & Resource Protection

Backtest Lab contains computationally expensive capabilities.

Protect:
- Monte Carlo;
- robustness grids;
- Strategy Destruction;
- large imports;
- report generation;
- AI requests;
- bulk exports.

Controls may include:
- per-user/workspace quotas;
- concurrency limits;
- job queues;
- request rate limits;
- execution time/memory limits;
- cancellation;
- plan-aware entitlements;
- abuse monitoring.

A single user must not be able to starve all research workers.

# 11. Payment Security

Backtest Lab should minimize payment-data scope.

Principles:
- use a reputable payment gateway for sensitive payment collection;
- do not store raw card credentials;
- verify webhook signatures/authenticity;
- webhook processing must be idempotent;
- never trust browser redirect/success UI alone as proof of payment;
- maintain auditable billing events;
- reconcile missed/delayed events;
- server-side entitlement checks control paid feature access;
- test upgrade, renewal, failure, cancellation, refund and downgrade flows.

Payment provider compromise/failure should not automatically expose research data.

# 12. Billing & Entitlement Security

> **Payment collects money. Billing records commerce. Entitlements control access.**

Paid research features query the internal entitlement layer, not payment-provider state directly.

Users must not be able to unlock paid features by changing frontend state or request parameters.

Administrative entitlement grants/revocations should be auditable.

# 13. AI Security Boundary

AI is not a trusted security principal.

Flow:

    Authorized User Request
             ↓
    Authorization Check
             ↓
    Research Context Builder
             ↓
    Minimum Necessary Context
             ↓
    AI Gateway
             ↓
    Model

AI must not receive:
- payment card data;
- passwords;
- API secrets;
- database credentials;
- unrelated tenants' data.

AI tools must enforce authorization independently. Prompt text cannot grant permission.

A prompt such as “show me every user's experiment” must fail because the tool/data layer does not grant that access, not because the model was politely instructed not to do it.

Treat AI/model output as untrusted input when it can trigger downstream actions.

# 14. Prompt Injection & AI Tool Safety

Where AI can use tools:
- use allowlisted tools;
- validate structured arguments;
- re-check authorization at tool execution;
- distinguish user content from trusted system instructions;
- do not allow retrieved journal/dataset text to override security policy;
- limit side effects;
- require explicit confirmation for sensitive future actions where appropriate;
- log sufficient tool provenance for audit/debugging.

The deterministic research engines remain the source of canonical evidence.

# 15. Research Data Integrity

Security includes protection from silent corruption, not only unauthorized access.

Preserve:
- dataset version;
- protocol version;
- strategy version;
- engine version;
- execution-assumption version;
- regime version;
- seed where applicable;
- Experiment Passport identity.

Historical research results must not silently change when a new engine/dataset version is deployed.

Important mutations should create a new version or leave an audit trail rather than rewriting research history invisibly.

# 16. Backup & Recovery Security

Backups must be:
- access-controlled;
- encrypted where appropriate;
- separated sufficiently from primary failure domains;
- retention-controlled;
- periodically restored in a test environment;
- included in incident/recovery planning.

> **A backup that has never been restored is not yet proven recovery.**

Restore tests should verify both availability and data integrity.

# 17. Secrets Management

Never place production secrets in:
- source code;
- committed .env files;
- documentation;
- screenshots;
- client-side bundles;
- logs.

Use environment/secrets-management mechanisms appropriate to deployment maturity.

Rotate credentials after suspected exposure and design provider integrations so credentials can be changed without code rewrites.

# 18. Logging & Audit

Log security-relevant events without logging secrets.

Candidate events:
- authentication failures;
- session/security changes;
- workspace membership/role changes;
- privileged/admin operations;
- entitlement changes;
- payment webhook processing;
- sensitive exports;
- research version changes where relevant;
- AI tool invocations where needed for provenance.

Logs need retention/access policies and must not become a second uncontrolled copy of private user data.

# 19. Dependency & Supply-Chain Security

CI/CD should eventually include:
- dependency vulnerability scanning;
- secret scanning;
- lockfiles/reproducible dependency management;
- review of high-risk dependencies;
- automated tests;
- controlled production deployment permissions.

Keep frameworks/libraries updated through deliberate upgrade cycles rather than uncontrolled automatic production changes.

# 20. Deployment Security

Development, staging and production should be separated as maturity increases.

Production principles:
- least privilege;
- no shared personal credentials;
- controlled deployment path;
- protected production secrets;
- restricted administrative access;
- rollback capability;
- infrastructure configuration documented/versioned where practical.

Do not expose debug mode in production.

# 21. CRM / Odoo Security Boundary

CRM/Odoo receives only business/customer context it needs.

It is not the canonical store for Backtest Lab research evidence and should not automatically gain unrestricted access to experiments/trades/journals.

Integration credentials should be scoped and replaceable.

CRM outage must not break valid core research access.

# 22. Security + Upgradeability

> **Start small, but never design ourselves into a corner.**

Security architecture must survive Profile S → M → L.

Moving from one server to separated API/DB/workers or distributed infrastructure must not require weakening tenant isolation or changing resource ownership semantics.

Security controls may become more sophisticated as scale increases, while the fundamental authorization/data-boundary contracts remain stable.

# 23. Threat Modeling

Before public multi-user launch, maintain a threat model covering at least:
- account takeover;
- broken access control / IDOR;
- cross-tenant data leakage;
- injection;
- malicious file upload;
- API abuse / resource exhaustion;
- payment spoofing;
- privilege escalation;
- leaked secrets;
- supply-chain compromise;
- AI prompt/tool injection;
- backup exposure;
- research-result tampering;
- administrative misuse;
- dependency/provider outages.

Threat model should be updated when major architecture boundaries change.

# 24. Public Launch Security Gate

Before a public multi-user release, require evidence that relevant controls have been tested.

Candidate gate:

    [ ] Authentication flows tested
    [ ] Server-side authorization tested
    [ ] Cross-tenant isolation tests pass
    [ ] Secret scanning clean
    [ ] Dependency/security scanning reviewed
    [ ] HTTPS/TLS production-ready
    [ ] Database not publicly exposed
    [ ] File import abuse tests pass
    [ ] API rate/resource controls tested
    [ ] Payment webhook verification tested
    [ ] Entitlement bypass tests pass
    [ ] AI context isolation tests pass
    [ ] Backup created AND restore tested
    [ ] Audit/logging paths reviewed
    [ ] Production secrets separated
    [ ] Incident/rollback procedure documented
    [ ] Representative abuse/load tests completed

The exact gate should evolve with product scope.

# 25. Security Testing Strategy

Layer tests:
1. unit tests for authorization and validation;
2. integration tests for tenant/resource boundaries;
3. end-to-end auth/payment flows;
4. negative/abuse tests;
5. dependency and secret scans;
6. backup/restore drills;
7. load/resource exhaustion tests;
8. pre-launch security review;
9. periodic reassessment after major architecture changes.

External security review/penetration testing should be considered before handling significant production scale or sensitive commercial data.

# 26. Incident Response Principle

Assume failures can occur.

For a security incident, preserve the ability to:
- contain access;
- revoke/rotate credentials;
- invalidate sessions;
- disable compromised integrations;
- inspect relevant audit history;
- communicate impact accurately;
- restore from verified backups where required;
- patch and validate before re-enabling affected paths.

Do not destroy evidence needed to understand the incident.

# 27. Security Non-Negotiables

1. **Deny by default.**
2. **Server-side authorization.**
3. **Tenant isolation is tested, not assumed.**
4. **No secrets in source control.**
5. **No raw card credentials in Backtest Lab.**
6. **AI never bypasses authorization.**
7. **Canonical research evidence comes from deterministic engines.**
8. **Historical research provenance must remain traceable.**
9. **Backups must be restorable.**
10. **Security boundaries remain upgradeable with infrastructure.**
11. **Measure and test security claims just as we test trading claims.**

# 28. Security Thesis

Backtest Lab's scientific identity applies to security too:

> **Don't trust the claim. Test it.**

“Secure” is not a label earned by architecture diagrams. It is a claim that must continually be tested through authorization tests, isolation tests, restore drills, abuse tests, monitoring and review.
