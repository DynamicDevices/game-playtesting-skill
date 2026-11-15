# Unity adapter static findings and security review

Independent review: DynamicDevices self-hosted Sandchest scan
`57dcec64-8260-406d-8869-28f94e40c66c`, completed on candidate
`ce0f9b0c201203805db27057229030985a6b44f5`, base
`f322f901ec506bb871c2945c4eebf6e1970f4bc0`.

Authoritative result: completed, no errors, zero findings, no warnings and no
skipped files. All six executable/configuration files in the effective diff were
reviewed (runner, adviser, common helpers, report, coverage and settings template;
1,171 changed lines). This is security review, not a claim that Unity or a game
was tested live, or that Preloop publication works.

## Static dispositions

Briar inspected these findings against the actual source, focused regression
tests and the independent result above. The fingerprint-bound baseline records
only those specific intentional behaviours; a changed source or scanner may
produce new findings and needs fresh triage. No wildcard suppression is intended.

| Rule | Findings | Disposition and boundary |
| --- | ---: | --- |
| AST4 | 6 | Inspected subprocess calls use argument lists without a shell. They launch explicitly selected local development tools, the fixed sibling adviser/report, a locally configured validator, or the exact selected credential item. Executables, project code and settings must be trusted by the operator; this is not an untrusted-project sandbox. |
| E2 | 1 | The runner passes its environment to local development children. This is ordinary process inheritance, not an upload of environment values. Ambient credentials are consequently visible to trusted local project/tool code; do not run untrusted projects or grant this runner a privileged environment. No claim of environment isolation is made. |
| PE3 | 19 | Inspected matches refer to the explicitly requested optional Keychain integration, template keys, defaults and its documentation. They do not enumerate unrelated items or read arbitrary credential files. Missing explicit selection fails closed; the selected key uses the fixed Anthropic API origin. This intentional feature still requires the user's agreement to third-party transmission and spending. |
| EA2 | 1 | The matched phrase "without consent" instructs the adviser to decline data sharing, not to operate without authorisation. The source also prohibits real-money purchases, adverts, reviews, sign-in and external sharing. These model instructions are not an enforcement boundary: the caller/bot must supply only authorised actions, and configured never-offer patterns filter options before model or memory selection. |
| LP3 | 1 | The portable skill has no declared runtime-permission metadata. The supported skill frontmatter does not itself issue or enforce execution permissions. Its instructions explicitly require per-task app/device authority and stop on unexpected payment/account/consent choices. An invented permission field would not supply enforcement; actual caller/runtime authority remains necessary. |

These dispositions do not waive runtime authority, independent review, CI,
branch protection or exact policy signatures. Do not reuse this baseline to
approve new credential sources, arbitrary network destinations or changed
subprocess behaviour.

## Tests and known limits

### PR #8: explicit route selection

Manual review reproduced an inherited PLAYTEST_ROUTE reaching the bot when no
route was selected. The correction clears that value before accepting a
nonempty `--route`. Fake-editor regressions cover omitted, empty and explicit
routes; no real Unity/game/device or credential request ran.

SkillSpector 2.8.2 reported eight unmatched findings after these intentional
runner/documentation changes: five AST4 subprocess calls, one E2 environment
inheritance match and two PE3 Keychain documentation matches. Each finding text
was verified present in the original independently reviewed source at
`ce0f9b0c201203805db27057229030985a6b44f5`; both credential-documentation contexts
are byte-for-byte unchanged. No subprocess primitive, credential source or API
destination was added or broadened. The E2 boundary remains trusted local
development code with an inherited environment, not an isolation claim.

Only those eight source-content fingerprints were refreshed after this review.
The other17 fingerprints (covering20 findings), existing dispositions, scanner
version and empty wildcard-rule list are unchanged. There are25 fingerprints
covering28 findings in total. This is maintenance of the recorded intentional
behaviour, not new independent security approval, suppression of a new behaviour
or an ASE admission exception. ASE's separate no-baseline intake stays blocked
until its own requirements are satisfied. The combined three-PR candidate passed
40 application tests,126 review-integration tests and template validation.

35 offline application tests and 111 integration tests pass. Regressions cover
screenshot confinement, selected credential failure, origin pinning, preservation
of workspace changes, incomplete-run rejection and invalid-session failure.
The synthetic template validates as `not_run`; no real game, device, SDK request
or credential lookup was exercised. Existing contributor attribution is retained.

Assisted-by: Briar
