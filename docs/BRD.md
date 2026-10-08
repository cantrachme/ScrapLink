# ScrapLink — Business Requirements Document (BRD)

| Attribute | Value |
|---|---|
| Product | ScrapLink |
| Document | Business Requirements Document |
| Version | 1.0 — Draft for review |
| Date | 2026-10-08 |
| Owner | Product team |
| Status | Proposed MVP scope; not a statement of implemented features |
| Related documents | [PRD.md](./PRD.md), [TRD.md](./TRD.md) |

## 1. Executive summary

ScrapLink is a job-discovery web product intended to help users find **active and recently published job opportunities** from a single dashboard. LinkedIn job listings are the original target source. The product will use browser-enabled data extraction where access is authorized and allowed, normalize discovered job information, remove duplicates, and make results searchable and filterable in a React interface.

ScrapLink is **not yet a working scraper**. The first business objective is to validate whether reliable, sufficiently complete, legally usable job data can be collected at a sustainable cost. Scrapling is the proposed Python collection framework. Its inclusion does not grant permission to scrape any particular website.

**Important source constraint:** LinkedIn's published policies prohibit unauthorized bots, crawlers, and scraping software. LinkedIn collection must not be treated as an assumed deliverable. It requires an approved/authorized method and a documented source-access decision before implementation. Until then, the MVP should support permitted company career sites, licensed feeds, approved APIs, and controlled test pages. See §10.

## 2. Business problem

Finding relevant, fresh job openings is a repetitive and fragmented process:

- Users manually enter the same searches across job sites.
- Listings appear in different formats and can repeat across searches.
- 'Posted recently' and 'still accepting applications' are different facts; conventional results often blur them.
- Users have difficulty determining when a listing was first discovered or last checked.
- Manual work makes it hard to track collection failures and incomplete searches.

### 2.1 Opportunity

Provide one trusted search-and-results workflow that records where each job was found, when it was posted (if known), and whether it is still verifiably active. The product should make uncertain data visible rather than pretending it is confirmed.

## 3. Business objectives

| ID | Objective | Business value |
|---|---|---|
| BO-01 | Centralize job discovery | Less manual switching among sources |
| BO-02 | Prioritize recent jobs | Faster review of new opportunities |
| BO-03 | Distinguish active vs unknown vs closed | Avoid misleading results |
| BO-04 | Reduce duplicates | Less repeated evaluation |
| BO-05 | Expose collection progress and failures | User trust and operational visibility |
| BO-06 | Keep source integration replaceable | Lower dependency on one provider |
| BO-07 | Validate source access and unit economics before scale | Avoid building on an unsustainable dependency |

No revenue model has been agreed. Commercial pricing, paid subscriptions, and enterprise features are **out of scope and undecided**.

## 4. Target users and stakeholders

### 4.1 Initial user

An individual researcher, recruiter, or job-market analyst who searches for software and other professional roles and wants fresh listings in one place. This is a *proposed* initial persona, not a confirmed market segment.

### 4.2 Future user segments (not MVP commitments)

Recruitment operations teams, talent researchers, business development teams, job seekers, and workforce analysts. Prioritization requires separate research.

### 4.3 Stakeholders

| Stakeholder | Interest |
|---|---|
| Product owner | Scope, value, source feasibility |
| End user | Relevant and current job listings |
| Engineering | Reliable browser jobs, manageable operations |
| Data/source owner | Authorized collection and permitted use |
| Operations | Failure visibility, resource limits, recovery |

## 5. Business scope

### 5.1 MVP in scope

1. React page to configure a search using keywords/title, location, and date-posted range.
2. Backend search-run creation and background execution.
3. At least one **permitted** source integration using Scrapling; test pages may be used for initial technical validation.
4. Browser rendering for sources that legitimately require JavaScript execution.
5. Job record extraction, validation, normalization, and deduplication.
6. Persistent results and traceable source URLs.
7. Search-run status, counters, errors, and Server-Sent Events (SSE) updates.
8. Results table/cards with filtering and sorting.
9. Clear provenance, freshness, and verification status on each listing.
10. Local development and a reproducible deployment configuration.

### 5.2 Specifically conditional

**LinkedIn listings** are part of the product vision, **not an unconditional MVP acceptance criterion**. Integration proceeds only when the team has determined and documented a permitted/authorized collection path. No credential theft, CAPTCHA bypass, evasion of access controls, or unauthorized automated login is in scope.

### 5.3 Out of scope for MVP

- Candidate profile scraping, recruiter messaging, LinkedIn account automation, or outreach.
- Automatic job applications.
- AI matching/scoring, hiring-manager discovery, or candidate matching.
- Payments, subscriptions, multi-tenant billing, or complex role management.
- Mobile apps and browser extensions.
- Unlimited crawling, continuous monitoring, or guaranteed comprehensive coverage.
- Automatic assertion that an inaccessible job is closed.

## 6. End-to-end business workflow

1. User enters a job title/keywords, optional location, and posting-date range.
2. User submits a search.
3. System validates input and selects enabled, authorized sources.
4. System creates a uniquely identified run with `queued` status.
5. Worker fetches permitted listings and follows allowed pagination.
6. Extractor converts source pages to a common job schema.
7. Validation rejects invalid records and deduplicates the rest.
8. System stores jobs, provenance, timestamps, and run statistics.
9. Dashboard receives progress notifications and displays discovered jobs.
10. A later validation/check may update an existing job's activity status.

Failure at any step should be visible in the run details; partial successful results should remain available.

## 7. Success metrics and measurement

Initial values below are **proposed pilot targets**, to be revised after testing on approved sources.

| Metric | Definition | Proposed pilot target |
|---|---|---|
| Extraction precision | Correct required fields / sampled extracted records | ≥95% on manually reviewed sample |
| Duplicate rate | Duplicate listings remaining / stored listings sampled | <2% within a source |
| Run completion | Runs reaching completed or completed-with-errors / started runs | ≥95% on stable test sources |
| Visibility | Runs with timestamped final status and error details | 100% |
| Source attribution | Jobs with source URL and provider name | 100% |
| Freshness transparency | Results displaying discovered time and activity confidence | 100% |

**Coverage** needs a known denominator (e.g., source-provided count or manually audited set) and should **not** be claimed solely from the number of extracted jobs. Define performance SLAs after representative runs; no fixed speed or cost is promised in the MVP.

## 8. Key business rules

- A listing is **recent** only if its publisher-provided posting time is within the requested interval, or clearly labeled when only a relative/estimated date is available.
- A listing is **active** only if a recent, documented source check supports that status. Otherwise label `unknown`; confirmed expiry/removal may be `closed`.
- New discovery does not prove that a role is accepting applications.
- If a source blocks access or fails, report the failure; do not interpret it as a closed job.
- Preserve raw source context or a minimal extraction audit record where terms and retention policies permit it.
- Display source names and original listing links whenever allowed.
- Store UTC timestamps; convert to user-local time for display.
- Do not silently drop all partially collected results because one page failed.

## 9. Risks and dependencies

| Risk | Consequence | Mitigation |
|---|---|---|
| LinkedIn does not authorize required collection | Core vision cannot be delivered as originally imagined | Source feasibility gate; alternative permitted sources |
| Layout or JavaScript changes | Missing/bad fields | Source-specific adapters, fixtures, tests, anomaly alerts |
| Rate limiting or blocking | Partial runs and unstable performance | Respect source limits, stop/back off, report errors |
| Ambiguous posting dates | False 'recent' claims | Store date precision and original string |
| Misclassified activity status | Misleading results | Explicit `unknown`, verification evidence |
| Duplicate listings | Poor user experience | Provider IDs, canonical URLs, conservative matching |
| Large browser resource use | Hosting cost and instability | Bounded concurrency, timeouts, metrics |
| Legal, IP, or privacy obligations | Product and account risk | Source review, permission records, minimization and retention |

## 10. Source-access and compliance gate

Before enabling any source in production, record:

- Source/provider name, permitted URL patterns, and responsible contact.
- The contractual or documented basis for collection and storage/display.
- Whether authenticated access is allowed and the agreed authentication mechanism.
- Applicable request limits, robots guidance, licensing, geographic, and retention restrictions.
- Whether storing full descriptions, deep links, or derived fields is permitted.
- Date of approval and reviewer/owner.

LinkedIn specifically states that third-party scrapers, crawlers, and bots that automate activity on its site are not permitted under its user agreement. Any LinkedIn integration needs a separately approved path; publicly viewable HTML is not itself permission to collect or redistribute data.

References:
- LinkedIn prohibited software: https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software
- LinkedIn user agreement: https://www.linkedin.com/legal/user-agreement
- LinkedIn developer terms: https://developer.linkedin.com/legal

## 11. Assumptions and open business decisions

| Topic | Current position | Decision required |
|---|---|---|
| Primary source | LinkedIn is the intended target | Authorized access path or revise target |
| Pilot source | Permitted career sites/test fixtures | Choose first source(s) |
| First customer | Single internal user for MVP (proposal) | Confirm target audience |
| Search geography | Flexible text location input | Initial supported regions |
| Data retention | Configurable; no fixed duration yet | Set terms-based policy |
| Pricing | Not defined | Later discovery |
| Ownership of content | Belongs to source/rightsholder | Confirm display and licensing rules |
| Hosting | Local first; Docker-friendly design | Production cloud provider |

## 12. MVP release gates

The pilot may be released to an internal user only when:

1. At least one authorized source returns persisted, correctly attributed jobs.
2. Search and progress/results UI work end-to-end.
3. Duplicate handling and active/unknown/closed logic are tested.
4. Failed/partial runs are clearly identified.
5. No secrets or browser profiles are committed to Git.
6. Permissions and limitations are visible in internal deployment documentation.

A publicly marketed claim of **LinkedIn coverage** must be withheld unless an approved and reliable LinkedIn integration is actually available.

## 13. Document relationship

- **BRD** (this document): why the product exists, business scope, success, risks.
- **PRD**: user journeys, interface behavior, functional requirements, acceptance tests.
- **TRD**: system architecture, API contracts, data model, worker design, infrastructure and testing.
