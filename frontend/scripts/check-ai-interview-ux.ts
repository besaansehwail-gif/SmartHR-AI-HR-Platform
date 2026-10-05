/**
 * AI Interview page UX for the Phase 9/10 rules, checked rather than assumed.
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-ux.ts
 *
 * No browser, no backend, no model. Runs the page's rules module
 * (`aiInterviewRules.ts`) for real, checks every refusal code has an English
 * AND Arabic sentence, that `ApiError` carries the backend's `code`, and that
 * the page wires them: Start disabled outside the window, the window line
 * before Start, refusals translated by code, and no restart once finished.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { aiInterview } from '../src/i18n/dictionaries/aiInterview';
import { START_ERROR_CODES, startErrorKey, startWindow } from '../src/pages/applicant/aiInterviewRules';
import { ApiError } from '../src/services/api';
import type { AiInterviewListing } from '../src/types';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

console.log('1. Start window (the page\'s own rule, run for real)');
const listing: AiInterviewListing = {
  interview_id: 1, job_title: 'X', status: 'scheduled',
  scheduled_at: '2026-10-05T09:00:00', opens_at: '2026-10-05T08:45:00', closes_at: '2026-10-05T09:30:00',
  is_test: false, attempts_exhausted: false,
};
const at = (s: string) => new Date(s).getTime();
check('before opens_at -> early (Start disabled)', startWindow(listing, at('2026-10-05T08:44:59')) === 'early');
check('exactly opens_at -> open', startWindow(listing, at('2026-10-05T08:45:00')) === 'open');
check('exactly closes_at -> open (inclusive, like the backend)', startWindow(listing, at('2026-10-05T09:30:00')) === 'open');
check('after closes_at -> late (Start disabled)', startWindow(listing, at('2026-10-05T09:30:01')) === 'late');
check('no window sent -> unknown (the backend decides)',
  startWindow({ ...listing, opens_at: null, closes_at: null }, Date.now()) === 'unknown');
check('unparseable window -> unknown', startWindow({ ...listing, opens_at: 'soon' }, Date.now()) === 'unknown');
check('no interview selected -> unknown', startWindow(null, Date.now()) === 'unknown');

console.log('\n2. Refusal codes -> translated sentences');
const required = ['too_early', 'too_late', 'attempts_exhausted', 'attempt_finished', 'session_active', 'completed'];
check('the required codes are all mapped (session_active = the concurrent-session refusal)',
  required.every((c) => startErrorKey(c) === `aiInterview.errorCode.${c}`));
check('an unknown code -> null (the backend detail is shown instead)', startErrorKey('something_new') === null);
check('no code -> null', startErrorKey(null) === null && startErrorKey(undefined) === null);
const arabic = /[؀-ۿ]/;
for (const code of START_ERROR_CODES) {
  const entry = aiInterview[`aiInterview.errorCode.${code}`];
  check(`errorCode.${code}: English and Arabic`, !!entry && entry.en.length > 0 && arabic.test(entry.ar));
}
for (const code of ['too_early', 'too_late']) {
  const entry = aiInterview[`aiInterview.errorCode.${code}`];
  check(`errorCode.${code} names the time in both languages`, entry.en.includes('{time}') && entry.ar.includes('{time}'));
}
for (const w of ['early', 'open', 'late']) {
  const entry = aiInterview[`aiInterview.window.${w}`];
  check(`window.${w}: English and Arabic, with the time`,
    !!entry && arabic.test(entry.ar) && entry.en.includes('{time}') && entry.ar.includes('{time}'));
}
const review = aiInterview['aiInterview.complete.review'];
check('completed state text in both languages', !!review && arabic.test(review.ar));
const unused = Object.keys(aiInterview).filter((k) =>
  (k.startsWith('aiInterview.errorCode.') && !(START_ERROR_CODES as readonly string[]).includes(k.slice(22)))
  || (k.startsWith('aiInterview.window.') && !['early', 'open', 'late'].includes(k.slice(19))));
check('no errorCode/window key is defined and unused', unused.length === 0, unused.join(','));

console.log('\n3. ApiError carries the backend code, and keeps the detail');
const err = new ApiError('This AI Interview opens at 2026-10-05 08:45', 409, 'too_early');
check('still an Error, message = backend detail', err instanceof Error && err.message.startsWith('This AI Interview opens'));
check('status and code kept', err.status === 409 && err.code === 'too_early');
check('code defaults to null', new ApiError('x', 500).code === null);
const api = read('../src/services/api.ts');
check('apiFetch reads `code` beside `detail` and throws ApiError',
  api.includes("typeof errorData.code === 'string'") && api.includes('throw new ApiError(message, response.status, code)'));

console.log('\n4. The page wires it');
const page = read('../src/pages/applicant/AiInterviewPage.tsx');
check('Start is disabled outside the window',
  page.includes('disabled={!configured || selectedId === null || !insideWindow}'));
check('...and so is the restart confirmation', page.includes('disabled={!configured || !insideWindow}'));
check('the clock ticks, so Start enables itself when the window opens',
  /setInterval\(\(\) => setNow\(Date\.now\(\)\)/.test(page));
const ready = page.indexOf("view === 'ready' ?");
const windowLine = page.indexOf('data-testid="ai-interview-window"');
const startBtn = page.indexOf("t('aiInterview.action.start')");
check('the window line is in the ready view, before Start', ready > -1 && windowLine > ready && windowLine < startBtn);
check('the scheduled time is still shown (job header)', page.includes("t('aiInterview.job.scheduled'"));
check('refusals are translated by code, falling back to the detail',
  page.includes('startErrorKey(e.code)') && page.includes('if (!key) return fallback;'));
// Phase 11.6.1 made it stricter: also not after a final backend refusal (retryAllowed).
check('no restart action once the interview is finished',
  page.includes('&& !finishedInterview && retryAllowed && !attemptsExhausted && restartControl')
  && page.includes('completed && questionPresented'));
check('the completed state says HR can now review it', page.includes("t('aiInterview.complete.review')"));

console.log(`\n  ${failed === 0 ? 'All AI Interview UX checks passed.' : `${failed} UX check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
