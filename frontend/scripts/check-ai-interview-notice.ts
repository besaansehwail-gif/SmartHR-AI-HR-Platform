/**
 * The AI Interview notice (Phase 10), checked rather than assumed.
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-notice.ts
 *
 * Before pressing Start, an applicant is told: the interviewer is an AI, the
 * TEXT of their answers is saved (not the audio), each answer is analysed by
 * AI, HR can read the answers and the analysis, and the AI makes no hiring
 * decision. This checks that every point exists in English AND Arabic, that
 * the page renders all of them in the ready view BEFORE the Start button, and
 * that the wording claims nothing SmartHR does not do.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { aiInterview } from '../src/i18n/dictionaries/aiInterview';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};

const page = readFileSync(
  fileURLToPath(new URL('../src/pages/applicant/AiInterviewPage.tsx', import.meta.url)), 'utf8');

// The points the page renders, read from the page itself.
const declared = page.match(/const NOTICE_POINTS\s*=\s*\[([^\]]*)\]/);
const points = declared ? [...declared[1].matchAll(/'([^']+)'/g)].map((m) => m[1]) : [];
check('the page declares the notice points', points.length > 0);
check('...covering AI, storage, analysis, HR review and no AI decision',
  ['ai', 'stored', 'analysed', 'hrReview', 'noDecision'].every((p) => points.includes(p)), points.join(','));

// Both languages, for the title and every point.
const keys = ['aiInterview.notice.title', ...points.map((p) => `aiInterview.notice.${p}`)];
const arabic = /[؀-ۿ]/;
for (const key of keys) {
  const entry = aiInterview[key];
  check(`${key}: English and Arabic present`,
    !!entry && entry.en.trim().length > 0 && arabic.test(entry.ar) && entry.en !== entry.ar);
}
const defined = Object.keys(aiInterview).filter((k) => k.startsWith('aiInterview.notice.'));
check('no notice key is defined and unused', defined.every((k) => keys.includes(k)),
  defined.filter((k) => !keys.includes(k)).join(','));

// Placement: in the ready view, before the Start button.
const ready = page.indexOf("view === 'ready'");
const notice = page.indexOf("t('aiInterview.notice.title')");
const startButton = page.indexOf("t('aiInterview.action.start')");
const sessionView = page.indexOf('session / complete');
check('the notice is rendered in the ready view', ready > -1 && notice > ready && notice < sessionView);
check('...before the Start button', notice > -1 && startButton > -1 && notice < startButton);
check('...rendering every point', page.includes('NOTICE_POINTS.map(') && page.includes('`aiInterview.notice.${point}`'));

// Accuracy: what it says, and what it must not say.
const en = keys.map((k) => aiInterview[k].en).join(' ');
check('says the interviewer is an AI', /AI interviewer, not a person/.test(en));
check('says the answers are saved - as text', /turned into text, and that text is saved/.test(en));
check('does not claim a voice recording is kept', /does not save a recording of your voice/.test(en));
check('says each answer is analysed by AI', /analysed by AI/.test(en));
check('says HR can read the answers and the analysis', /HR team can read your answers and the AI analysis/.test(en));
check('says the AI makes no hiring decision', /does not make hiring decisions/.test(en));
check('mentions no score, rating, percentage or ranking (the analysis has none)',
  !/\b(score|scored|rating|rated|percent|percentage|rank|ranking)\b/i.test(en));

console.log(`\n  ${failed === 0 ? 'All notice checks passed.' : `${failed} notice check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
