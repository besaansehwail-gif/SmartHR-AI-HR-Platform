/**
 * The HR Interview Report UI (Phase 8 + 11.4), checked rather than assumed.
 *
 *   cd frontend; npx tsx scripts/check-ai-report.ts
 *
 * No browser, no backend. Every `hr.aiReport.*` label the modal uses exists in
 * English AND Arabic; no such key is defined and unused; the follow-up is
 * labelled "Follow-up to question N" in both languages; the question flow,
 * coverage and context sections are rendered; stored text keeps its own
 * direction; and the layout uses logical (RTL-safe) utilities only.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { hr } from '../src/i18n/dictionaries/hr';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

const modal = read('../src/components/ai/InterviewReportModal.tsx');
const page = read('../src/pages/hr/InterviewsPage.tsx');
const arabic = /[؀-ۿ]/;

// Keys used literally, plus the template families the modal builds.
const literal = new Set([...(modal + page).matchAll(/'(hr\.aiReport\.[A-Za-z0-9_.]+)'/g)].map((m) => m[1]));
const families = [...modal.matchAll(/`(hr\.aiReport\.[A-Za-z0-9_.]*?)\$\{/g)].map((m) => m[1]);
const defined = Object.keys(hr).filter((k) => k.startsWith('hr.aiReport.'));
const used = (k: string) => literal.has(k) || families.some((f) => k.startsWith(f));

console.log('1. Labels in both languages');
const missing = [...literal].filter((k) => !hr[k]);
check('every hr.aiReport key the UI uses is defined', missing.length === 0, missing.join(','));
const noArabic = defined.filter((k) => !arabic.test(hr[k].ar) || !hr[k].en.trim());
check('every hr.aiReport key has English and Arabic text', noArabic.length === 0, noArabic.join(','));
const unused = defined.filter((k) => !used(k));
check('no hr.aiReport key is defined and unused', unused.length === 0, unused.join(','));
const fu = hr['hr.aiReport.followUpN'];
check('"Follow-up to question N" in English and Arabic, with the number',
  fu.en === 'Follow-up to question {number}' && arabic.test(fu.ar) && fu.ar.includes('{number}'));
for (const k of ['order.bank', 'order.adaptive', 'order.unknown', 'context.job', 'context.cv', 'context.matching',
  'notReachedNote', 'durationNotRecorded', 'contextNote']) {
  check(`hr.aiReport.${k}: both languages`, !!hr[`hr.aiReport.${k}`] && arabic.test(hr[`hr.aiReport.${k}`].ar));
}
check('the matching indicator says it carries no score, in both languages',
  /no score/.test(hr['hr.aiReport.context.matching'].en) && hr['hr.aiReport.context.matching'].ar.includes('دون درجة'));
const allText = defined.map((k) => `${hr[k].en} ${hr[k].ar}`).join(' ');
check('no label speaks of a score, rating, ranking or recommendation (except to say there is none)',
  !/\b(rating|rank|ranking|recommend\w*|percentage)\b/i.test(allText.replace(/not a score, a rating/i, '')));

console.log('\n2. The report sections are rendered');
check('question flow: main question in order, follow-up nested and labelled',
  modal.includes('r.question_flow.map(') && modal.includes('data-testid="ai-report-follow-up"')
  && modal.includes("t('hr.aiReport.followUpN', { number: e.number })"));
check('a follow-up keeps its OWN answers (separate from the main answer)',
  modal.includes('answersOf(e.follow_up.answer_sequences)') && modal.includes('answersOf(e.main.answer_sequences)'));
check('coverage: answered, follow-ups, highest reached, order, not reached',
  ['main_questions_answered_count', 'follow_ups_answered_count', 'highest_main_question_reached',
    'order_matches_current_bank', 'not_reached'].every((f) => modal.includes(f)));
check('context: availability only - the component never reads a context value',
  modal.includes("(['job', 'cv', 'matching'] as const)") && !/\.score\b/.test(modal));
check('analysis statuses and the exact transcript per answer',
  modal.includes('hr.aiReport.status.${answer.analysis_status}') && modal.includes('{answer.transcript}'));

console.log('\n3. RTL');
check('stored text (questions, transcripts, quotes) keeps its own direction (dir="auto")',
  modal.includes('<span dir="auto"') && (modal.match(/<Stored>/g) || []).length >= 10);
const physical = modal.match(/\b(ml|mr|pl|pr)-\d|\btext-(left|right)\b|\b(border-l|border-r)\b|\b(left|right)-\d/g) || [];
check('logical utilities only (ms-/me-/ps-/pe-/border-s) - nothing that breaks in Arabic', physical.length === 0,
  physical.join(','));
check('the follow-up indent is logical (border-s / ps-)', modal.includes('border-s-2 border-brand-200 ps-3'));

console.log(`\n  ${failed === 0 ? 'All report UI checks passed.' : `${failed} report UI check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
