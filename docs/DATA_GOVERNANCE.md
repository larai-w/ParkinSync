# Data Governance and Publication Boundaries

ParkinSync is a research-engineering prototype for recording caregiver observations and contextual
telemetry. This policy is the release gate for any participant data. It does not replace applicable
law, an institutional ethics review, or a data-processing agreement.

## Current repository boundary

The public repository may contain source code, schemas, tests, deterministic synthetic fixtures, and
reviewed documentation. It must not contain participant identities, facility names, private health
records, raw interview notes, credentials, or unpublished application material. The tracked analytics
fixture is generated solely from the public schema and is not evidence about a person, household, or
care setting.

Superseded CSV and chart files with an insufficient public provenance record were removed from the
current tree. Repository history is also a publication surface: a suspected historical disclosure must
be escalated to the data steward for containment, access review, and a separately approved history-
remediation decision.

## Roles and authority

| Role | Responsibility | Boundary |
|---|---|---|
| Participant | The person described by a record; receives notice and exercises consent, access, withdrawal, and deletion rights. | Another role cannot waive the participant's rights unless documented authority applies. |
| Household member | Helps coordinate devices or shared context. | Household access does not imply authority to publish or approve secondary use. |
| Caregiver | Records observations within the agreed care workflow and may correct their own entries. | Caregiver authorship does not grant research or publication rights over participant data. |
| Care professional | Reviews records within an assigned care relationship. | Care access does not include secondary research use by default. |
| Product operator | Maintains the service, resolves support incidents, and uses the minimum data needed for an approved purpose. | Cannot expand purpose, retention, or audience without review. |
| Data steward | Maintains the data inventory, access log, retention schedule, deletion evidence, and release register. | Must be independent from the author of a proposed public analysis when feasible. |
| Research lead / ethics reviewer | Owns the protocol and determines whether formal human-subjects review is required. | Approval must precede recruitment or collection; retrospective approval is not acceptable. |

## Consent lifecycle

Every collection involving participant data must have a consent record outside this repository. The
record must identify the participant or authorized representative, notice version, approved purposes,
data categories, recipients, retention period, effective date, and evidence of the consent action.

1. **Versioning:** assign an immutable version and effective date to each notice. Re-consent is required
   before a material change to purpose, collected fields, recipients, or retention takes effect.
2. **Withdrawal:** authenticate the request, stop future collection, revoke active access, identify
   downstream copies, and record completion. Withdrawal must not be treated as a reason to reduce care.
3. **Deletion:** delete or irreversibly de-identify covered records and derived row-level copies within
   the declared service window, which defaults to 30 calendar days. Any exception must have a documented
   basis, scope, owner, and expiry communicated to the requester.
4. **Retention:** each approved collection must define an expiry for raw, pseudonymous, aggregate, log,
   and backup data before collection starts. The data steward reviews expiries at least monthly. Public
   synthetic fixtures may be retained because they contain no participant observations.
5. **Access:** grant least-privilege, role-based access for a named purpose and expiry. Review access at
   least quarterly and after role changes; log exports and administrative access.

## Product improvement and research

Product-improvement review is limited to operating and improving the agreed service, such as checking
workflow completion, reliability, usability, and data-quality failures. It cannot be used to make
generalizable health claims or silently expand collection.

Human-subjects research includes systematic investigation intended to create generalizable knowledge,
cross-participant health analysis, experimental assignment, secondary use outside the consented service
purpose, or external publication of participant-derived findings. It requires a written protocol,
documented consent basis, and an independent ethics determination before recruitment, collection, or
analysis begins. Product access alone is not research consent.

## Secondary review of annotations

A protocol may use a second reviewer to measure annotation consistency only when the consent and access
scope allow it.

1. Freeze an eligible set and select a reproducible subset using the ceiling of 10%, with at least one
   and no more than 20 records when the eligible set is non-empty.
2. Expose only a pseudonymous record key, the bounded annotation field, and the minimum context needed
   to apply a written rubric. Hide names, precise addresses, free-text fields, and unrelated timestamps.
3. Use a reviewer who did not create the original annotation. Record agreement and disagreement without
   silently overwriting either judgment.
4. Resolve disagreements through documented adjudication, retain the audit trail for the protocol's
   declared period, and report uncertainty rather than presenting reviewed labels as ground truth.

## Publication tiers

| Tier | Material | Allowed destination | Release gate |
|---|---|---|---|
| 0 | Schemas, field definitions, architecture, and code | Public repository | Security and claims review; no participant values or identifying metadata. |
| 1 | Deterministic synthetic fixtures and benchmarks generated without participant records | Public repository | Generator, synthetic marker, provenance manifest, reproducibility test, and non-clinical label. |
| 2 | Participant-derived aggregate findings | Reviewed public report only | Protocol and consent permit publication; ethics determination complete; cells smaller than 10 and revealing complements/outliers are suppressed; uncertainty and methods are reported. |
| 3 | Pseudonymous longitudinal records | Controlled-access research environment only | Approved protocol, data-use agreement, named recipients, audit logging, expiry, and re-identification review. Never Git. |
| 4 | Identifiable records, precise raw timestamps, free text, or source forms | Restricted operational or approved research systems only | Explicit purpose and consent/authority, encryption, strict access, retention expiry, and incident procedure. Never Git. |

Synthetic data must be designed from the schema and invented scenarios, not by perturbing, resampling,
or copying participant records. A publication reviewer must be able to regenerate Tier 1 artifacts
without access to private data.

## Time-series re-identification review

Longitudinal records can identify a person even after names are removed. Before a Tier 2 or Tier 3
release, the data steward and an independent reviewer must document:

- direct identifiers and embedded metadata, including filenames and free text;
- combinations of age, household, facility, location, device, schedule, and role;
- exact timestamps, rare events, missingness patterns, and distinctive longitudinal sequences;
- linkage risk from weather, public events, social posts, or another released dataset;
- group sizes, outliers, complementary tables, and whether repeated releases enable reconstruction;
- mitigations such as field removal, time binning, date shifting, category grouping, suppression,
  aggregation, access controls, and release rejection; and
- residual risk, reviewer names, decision date, approved audience, and expiry.

A release is rejected when the residual risk is not justified by the stated purpose. Pseudonymization
alone is not treated as anonymization.

## Approval path for expanded collection

Before any multi-participant or multi-site collection begins:

1. Write the research question or product purpose, data flow, data dictionary, recruitment plan,
   retention schedule, and stop criteria.
2. Complete security, access, vendor, data-location, and re-identification reviews.
3. Prepare versioned participant information, consent, withdrawal, access, and deletion procedures.
4. Obtain an independent determination from the responsible institutional review body about required
   ethics or human-subjects approval, and obtain that approval when required.
5. Record written sign-off from the protocol owner and data steward; for multiple sites, also record each
   site's authorization and data responsibilities.
6. Verify the approved configuration with synthetic data before recruitment or participant collection.

Changes to purpose, sites, participant groups, fields, recipients, or retention return to the relevant
review step. Exploratory correlations never authorize diagnosis, treatment, or medication changes.

Last reviewed: 2026-08-01.
