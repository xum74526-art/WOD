# KAI maintained braces patch

This private package is a source fork of [`braces` 3.0.3](https://github.com/micromatch/braces/tree/3.0.3),
used by the iOS and Android build tools through an npm override. It preserves the
upstream public API and MIT license. It is not an upstream security release.

Upstream provenance:

- npm archive: `https://registry.npmjs.org/braces/-/braces-3.0.3.tgz`
- npm integrity: `sha512-yQbXgO/OSZVD2IsiLlro+7Hf6Q18EJrKSEsdoMzKePKXct3gvD8oLcOQdIzGupr5Fj+EDe8gO/lxc1BzfMpxvA==`
- source commit: `74b2db2938fad48a2ea54a9c8bf27a37a62c350d`

## Security change

As of 2026-10-08, [CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
has no published upstream fix. Deep brace/parenthesis patterns can exhaust the
recursive walkers' stack even below the existing 10,000-character input limit.

- `lib/parse.js` rejects more than 100 nested brace/parenthesis blocks, before
  creating or walking the offending subtree. Quoted, escaped and bracket-class
  literals do not count as blocks.
- `lib/depth.js` validates caller-provided ASTs iteratively, before `compile`,
  `expand` or `stringify` recurse. Cyclic child graphs also reach the depth bound.
- `expand` bounds upward parent traversal, including malformed caller ASTs.
- Rejections are `SyntaxError` with `code: ERR_BRACES_MAX_DEPTH`, rather than
  uncontrolled stack exhaustion. The ceiling cannot be disabled via options.
- The existing input-length and expansion-range limits remain in effect.

Unchanged upstream sources: `index.js`, `lib/constants.js`, `lib/utils.js`.
The only runtime dependency, `fill-range`, remains the upstream 7.1.1 release.
This patch addresses recursion depth; it does not claim to bound every possible
Cartesian expansion or make arbitrary untrusted glob execution safe.

## Installation and validation

Both clients declare `braces=file:../../packages/braces`, apply that same version
to all transitive callers with `overrides.braces=$braces`, and enable
`install-links=true`. Run `npm ci --prefix apps/ios` and
`npm ci --prefix apps/android` from a full repository checkout. No postinstall
patch script, downloaded fork, or committed package archive is needed.

Run `npm run test:dependency-security` after installation. These tests verify the
actual installed source against this directory, exercise the CVE input through
all public entry points and direct walker imports, test deep/cyclic ASTs, and
check ordinary glob/range behavior and existing resource limits. They run in
`check:all`, `audit:deps` and each mobile CI job.

Registry audits do not cover repository-local forks. Therefore a clean npm audit
is insufficient by itself; the installed-source and behavioral tests above are
mandatory. `fill-range` and other registry dependencies remain in the npm audit.
No advisory is ignored and the audit severity threshold is unchanged.

## Removal condition

Once upstream publishes a fix, review it against these regression cases, replace
both overrides with the fixed upstream version and regenerate both lockfiles.
Remove this fork and `install-links=true` only after security tests and both App
and H5 builds pass against the replacement. Update the installed-source assertions
to check that fixed release, retaining the exploit and compatibility tests.
