/**
 * Social Hub access, checked rather than assumed.
 *
 * This is convenience, not security - `require_staff` on every /social/*
 * route is the boundary - but a nav entry an Applicant can reach would still
 * be a bug, and adding a page is exactly when it happens.
 */
import { canAccessPage, landingPageFor } from '../src/services/access';

const PAGES = [
  'soc-feed',
  'soc-people',
  'soc-messages',
  'soc-profile',
  'soc-notifications',
] as const;

let failed = 0;

for (const role of [1, 2, 3, 4, 5]) {
  const allowed = PAGES.filter((p) => canAccessPage(role, p as never));
  const expected = role === 5 ? 0 : PAGES.length;
  const ok = allowed.length === expected;
  if (!ok) failed += 1;

  console.log(
    `  ${ok ? 'PASS' : 'FAIL'}  role ${role}: ${allowed.length}/${PAGES.length} Social Hub pages` +
      (role === 5 ? '  (Applicant must be 0)' : '')
  );
}

console.log(`\n  landingPageFor(5) = ${landingPageFor(5)}  (must not be a soc- page)`);
if (String(landingPageFor(5)).startsWith('soc-')) failed += 1;

/*
 * Moderation is narrower than the Social Hub itself: Admin and HR only.
 *
 * It is named `hr-social-moderation` rather than `soc-moderation` precisely
 * so this comes out right - `workspaceOf()` sends every `soc-` page to the
 * social workspace, which roles 1-4 all have, so a `soc-` name would have put
 * the nav entry in front of Managers and Employees. This asserts the naming
 * is doing that job, and will fail loudly if anybody renames it back.
 */
console.log('');
for (const role of [1, 2, 3, 4, 5]) {
  const can = canAccessPage(role, 'hr-social-moderation' as never);
  const expected = role === 1 || role === 2;
  const ok = can === expected;
  if (!ok) failed += 1;

  console.log(
    `  ${ok ? 'PASS' : 'FAIL'}  role ${role}: moderation ${can ? 'allowed' : 'denied'}` +
      `  (expected ${expected ? 'allowed' : 'denied'})`
  );
}

console.log(failed ? `\n${failed} FAILED` : '\nAll access checks passed.');
process.exit(failed ? 1 : 0);
