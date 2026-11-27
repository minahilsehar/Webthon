# Product Requirements Document

## Product

**Imtihanify** is a responsive online examination system for institutions and competition organizers. It supports administrators, examiners, and candidates with server-enforced access controls.

## Problem

Online examinations need clear administration, dependable timing and answer handling, fair evaluation, and privacy-conscious access. Candidates should understand what is available to them, while examiners need a reviewable path from exam setup to published results.

## Users

- **Administrator:** manages accounts, roles, permissions, and platform operations.
- **Examiner:** configures exams, manages questions and candidates, monitors attempts, grades responses, and publishes results.
- **Candidate:** accesses assigned exams, completes and submits attempts, and views their own published results.

## Product requirements

1. Authenticate users with Django session authentication and enforce authorization on the server.
2. Allow examiners to create, schedule, publish, and manage examinations and question assignments.
3. Enroll eligible candidates and enforce exam availability and duration using server time.
4. Support single-choice, multiple-select, and written-response questions.
5. Save candidate progress and provide clear submission and connectivity status.
6. Monitor attempts and record relevant events without treating indicators as proof of misconduct.
7. Grade objective answers consistently, support manual written-response grading, and gate results behind examiner publication.
8. Restrict results and reports to authorized users; provide useful actual-data summaries.
9. Support accessible responsive layouts and clear role-based navigation.
10. Provide local setup, environment template, and a safe demo-data command.

## Current implementation

The application has administrator, examiner, and candidate roles; protected exam setup and enrollment; scheduled draft/published exams; objective-choice questions; server-timed attempt start/resume, question snapshots, answer autosave with an IndexedDB offline queue, objective scoring, result publication, attempt history, and a basic examiner monitoring/results view. Account CSV import, profile and theme preferences, sign-in Turnstile verification, and the Imtihanify web-app manifest are also present.

The implementation does not yet meet the complete competition specification. In particular, it lacks reusable categorized/difficulty-rated question banks, written-response questions and manual grading, question randomization, candidate question navigation/review flags, exam announcements and incident records, question analytics, PDF and verifiable reports, a candidate-facing sandbox, question import, exam-workspace customization, and a scratchpad. No production deployment or representative exam-load benchmark is configured.

## Success criteria

- All three roles are represented in the custom user model.
- Signed-out users can see the responsive public page and sign-in form.
- Authentication uses server sessions; cookies are HttpOnly and SameSite=Lax.
- At common phone, tablet, and desktop widths, primary content remains readable and navigable.
- The public interface uses locally stored imagery and does not rely on an external image host.
- Automated tests and Django system checks pass for implemented behavior.

## Innovation challenge

The current implementation partially addresses failure-resilient examinations: accepted answers are stored server-side, deadlines use server time, active attempts can be resumed, and unsynchronized answer edits are queued in IndexedDB. This is not a complete offline guarantee; expiry finalization, prolonged outages, and large-scale concurrency still need end-to-end/load validation.
