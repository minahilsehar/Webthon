# Product Requirements Document

## Product

**Examflow** is a responsive online examination system for institutions and competition organizers. It supports administrators, examiners, and candidates with server-enforced access controls.

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

The current application provides the project foundation, custom role-bearing user model, secure session settings, a responsive one-page introduction, sign-in/sign-out forms, and a local-only command to seed demo accounts. Exam, question, attempt, grading, reporting, and candidate workflows remain future implementation work; the current landing page does not claim that those workflows are available.

## Success criteria

- All three roles are represented in the custom user model.
- Signed-out users can see the responsive public page and sign-in form.
- Authentication uses server sessions; cookies are HttpOnly and SameSite=Lax.
- At common phone, tablet, and desktop widths, primary content remains readable and navigable.
- The public interface uses locally stored imagery and does not rely on an external image host.
- Automated tests and Django system checks pass for implemented behavior.

## Innovation direction

Prioritize failure-resilient exams: persist accepted answers server-side, use server-authoritative deadlines, and make save status visible. This is a product direction, not a claim that attempt handling is implemented yet.
