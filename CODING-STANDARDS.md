CODE-STANDARDS.md


# Golden Rules — 

This file is the authoritative standard for this repository.
Read it entirely before writing, modifying, or reviewing any code.
Every action taken in this codebase must be consistent with these rules.
If a task cannot be completed without violating a rule, stop and state which 
rule is in conflict before proceeding.

---

## 1. Codebase hygiene — no orphans, no dead weight

- Before adding any new symbol (function, class, module, constant, type, 
  interface), verify it will be referenced by at least one other unit of code 
  that is not itself a test of that symbol alone.
- After every change, scan the affected files for any symbol that is now 
  unreferenced. Remove it. Do not leave it "just in case."
- Imports that are unused must be deleted, not commented out.
- Commented-out code must be deleted, not preserved. If it is worth keeping, 
  it belongs in version control history, not in the file.
- Feature flags or environment guards that are no longer needed must be removed 
  along with both their branches.
- If a file contains only one exported symbol and that symbol is not referenced 
  anywhere outside the file, flag it for review before proceeding.

---

## 2. No mocks, stubs, or test doubles in non-test code

- Files outside the designated test directories must contain zero references to 
  any mocking library, stub factory, or hardcoded fake implementation.
- Test doubles (mocks, stubs, fakes, spies) live exclusively in test directories 
  and are never imported by application code.
- If application code needs to substitute a dependency for flexibility, that is 
  done through an interface or abstract contract — not through a mock. The mock 
  implements the interface in test scope only.
- Hardcoded data that exists only to simulate a real response (magic strings, 
  placeholder arrays, fake identifiers) must not exist in application code. If 
  it exists in a test, it must be clearly scoped to that test.
- Any `TODO: replace with real implementation` comment is a defect. Either 
  implement it or remove the code entirely.

---

## 3. Dependency direction — enforced at every change

- Domain logic (business rules, entities, value objects) must not import from 
  infrastructure, transport, or framework modules.
- Application layer (use cases, orchestration) may import from domain only.
- Infrastructure (data access, external clients, messaging) implements 
  interfaces defined in the domain or application layer — it does not define 
  contracts that the domain depends on.
- Transport layer (request handlers, controllers, consumers) imports from 
  application layer only. It converts external representations to domain 
  objects and back.
- If you find a dependency that violates this direction, do not work around it. 
  Restructure so the direction is correct before continuing.

---

## 4. Every failure is named and handled explicitly

- Every operation that can fail must have its failure case handled explicitly 
  in the code path — not with a generic catch-all unless that catch-all 
  re-raises or records with full context.
- A catch, rescue, or error handler that discards the error silently is 
  prohibited. It must either recover with documented intent, translate to a 
  domain-appropriate error, or propagate with added context.
- Error types are specific. A general-purpose error with a string message is 
  not acceptable for domain failures. Each distinct failure scenario has a 
  named type or code.
- Every error emitted toward a caller carries: a stable error code, a 
  human-readable message, the correlation/trace identifier of the originating 
  request, and a timestamp.
- Validation failures list the specific fields or conditions that failed — 
  not a single generic message.

---

## 5. All observable events are structured and contextual

- Every log statement, event emission, or metric recording must be structured 
  (key-value pairs or equivalent) — never a plain interpolated string.
- Every record must carry: timestamp (UTC), severity level, service name, 
  trace identifier, correlation identifier, and the specific event name.
- Severity levels have fixed meanings. Use them precisely:
    - ERROR: an operation failed; investigation may be required
    - WARN: the operation completed under adverse conditions
    - INFO: a significant business or state transition occurred normally
    - DEBUG: diagnostic detail; must never be active in production by default
- Personal data, credentials, tokens, secrets, payment details, and any 
  value whose exposure causes harm must never appear in any log statement, 
  metric label, or trace attribute. If a value must be referenced, use a 
  non-reversible derived identifier.
- Debug and trace level logging must be guarded by a runtime configuration 
  flag — not a compile-time or deploy-time flag.

---

## 6. Every external call is bounded and protected

- Every call to an external system (another service, a data store, a broker, 
  a third-party API) must have an explicit timeout. The timeout value is a 
  named configuration parameter — not a magic number inline.
- Every external call must handle the case where the dependency is unavailable 
  and return a named failure (not an unhandled exception).
- If repeated failures to a dependency are detected, the system must stop 
  sending calls to that dependency for a defined recovery window before 
  retrying. This behaviour is configured, not hardcoded.
- Retry logic, where present, must use bounded attempts with increasing 
  intervals and random jitter. Unbounded retries are prohibited.

---

## 7. Configuration is external, validated at startup, and documented

- No configuration value — timeout, endpoint, credential reference, feature 
  flag, threshold — may be hardcoded in application code. All are read from 
  the environment at runtime.
- At startup, all required configuration is read and validated before the 
  service accepts any traffic. If any required value is absent or fails 
  validation, the service must exit immediately with a clear description of 
  what is missing.
- Every configuration parameter is documented in `.env.example` (or 
  equivalent) with: its name, what it controls, whether it is required or 
  optional, its expected format or valid range, and a safe example value.
- Secrets are never stored as plain text in any file in this repository, 
  including `.env.example`. Example values for secrets use placeholder 
  notation only.

---

## 8. Business behaviour is testable without infrastructure

- Any function or module that encodes a business rule must be testable 
  by importing it directly with no database, broker, cache, or network 
  dependency present.
- Tests that require infrastructure (database, message broker, cache) are 
  integration tests and live in a separate directory from unit tests.
- Tests express the observable behaviour being verified in their name and 
  structure — not the internal implementation. A test that breaks when a 
  private function is renamed (but behaviour is unchanged) is testing 
  implementation, not behaviour.
- Every test is independent. It does not depend on another test running 
  first, does not share mutable state with another test, and produces the 
  same result regardless of execution order or environment.
- Test coverage for domain and application layers must meet the thresholds 
  defined in CI action workflow .

---

## 9. State changes and their consequences are atomic

- If a state change in the data store must be accompanied by a notification 
  or event to another system, these two effects must be coordinated so that 
  one cannot succeed while the other fails permanently.
- Avoid publishing events or sending notifications within the same 
  transaction as a data write unless the transaction mechanism guarantees 
  both. If it does not, use a coordination pattern that defers the 
  notification until the write is confirmed.
- Operations that mutate state must be designed to produce the same result 
  when applied more than once. Each mutation carries a caller-supplied or 
  system-generated idempotency key that the service uses to detect and safely 
  ignore duplicate applications.

---

## 10. The contract is formal and changes are explicit

- This service's public interface (inbound and outbound) is defined in a 
  formal contract document - api-specification.yml. If they dont exist, create them using openAPI specification.
- The contract is the source of truth. If code and contract diverge, the 
  code is wrong.
- Any change that removes a field, renames a field, changes a type, or 
  alters the semantics of an existing field is a breaking change and requires 
  a version increment.
- Adding optional fields or new operations to an existing version is 
  permitted without a version increment, provided it does not alter the 
  behaviour of existing consumers.
- CI must verify that the committed contract matches the implementation. 
  A drift between the two is a build failure.

---

## 11. Code review and change hygiene

- A change that introduces new behaviour without a corresponding test is 
  incomplete. Do not mark it ready for review.
- A change that fixes a bug without a test that would have caught the bug 
  is incomplete.
- If a change requires modifying more than one bounded context, it must be broken into 
  separate changes.
- Every public function, exported type, and non-obvious algorithm has a 
  comment that explains why it exists and any non-obvious constraints — 
  not what it does (the code shows that).
- Before raising a change for review, run: linting, formatting check, 
  unit tests, and integration tests locally. Do not rely on CI to catch 
  issues that can be caught before the change leaves your machine.

---

## How Claude Code must behave in this repo

- Read this file completely before taking any action.
- When generating new code, apply every applicable rule above proactively — 
  do not wait to be asked.
- When reviewing existing code, identify violations of these rules and 
  state them explicitly before suggesting or making changes.
- When a requested change would violate a rule, do not silently comply. 
  State which rule is in conflict and propose an approach that satisfies both 
  the request and the rule.
- When removing dead code or orphaned symbols as part of a task, list what 
  was removed and why.
- Never introduce a mock, stub, or hardcoded fake outside of a test directory 
  as a shortcut to making something work. If the real implementation does not 
  exist, scaffold the interface and leave the implementation as a clearly 
  named placeholder that causes a runtime failure if called — never one that 
  silently succeeds with fake data.