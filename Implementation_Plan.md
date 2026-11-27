# Implementation Plan

Work in small changes that keep the project runnable. The custom user model must exist before the first database migration.

## Completed foundation

- [x] Establish Django 5 project and dependency manifest.
- [x] Add `accounts.User` extending `AbstractUser`, with administrator, examiner, and candidate roles.
- [x] Configure PostgreSQL, environment-based settings, Argon2, django-axes, database sessions, CSRF, and secure cookie defaults.
- [x] Generate the initial custom-user migration; do not apply it until PostgreSQL is configured.
- [x] Add a responsive Django-templated landing page, local SVG artwork, and built-in session login/logout routes.
- [x] Add a DEBUG-only demo-account command that requires a password from the environment.
- [x] Add six theme/elevation tokens as the first approved design-system phase.
- [x] Add a local Tailwind CLI build and shared token-driven button, card, input, and badge styles; update the public shell with mobile bottom navigation.
- [x] Add a database role CHECK-constraint migration and secure non-debug PostgreSQL defaults; migration remains unapplied pending a reachable database.
- [x] Add product and technical documentation.

## Next implementation increments

1. **Local runtime and demo setup:** validate under Python 3.12, configure PostgreSQL, run the demo-account seed command, then apply migrations.
2. **Access foundations:** add role-aware authorization helpers and focused tests before adding protected workflows.
3. **Exam authoring:** add exam and question models/forms/admin, lifecycle validation, and examiner ownership tests.
4. **Enrollment:** add candidate assignment and availability checks.
5. **Attempt delivery:** persist attempt snapshots and answers, enforce server deadlines, support resume and idempotent submission.
6. **Evaluation:** implement objective scoring, manual written grading, review, and controlled publication.
7. **Monitoring and resilience:** record attempt events, show save/connectivity status, and test interrupted/retried requests.
8. **Reports and secondary features:** add access-controlled PDF, verifiable report IDs, imports, analytics, sandbox isolation, workspace preferences, and scratchpad.
9. **Quality and presentation:** run full tests, check accessibility and responsive layouts, document demo users, and prepare deployment separately.

## Completion gates

- Each increment has focused tests and passes Django system checks.
- Never create or apply the initial migrations before confirming the custom user setting.
- Do not mark an unimplemented feature complete in the interface or documentation.
- Validate on Python 3.12 and PostgreSQL before declaring local setup complete.
