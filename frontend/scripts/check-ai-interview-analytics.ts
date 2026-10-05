/**
 * AI Interview Analytics page (Phase 11.5.4), checked rather than assumed.
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-analytics.ts
 *
 * No browser, no backend. Labels exist in English and Arabic and none is
 * unused; every analytics response field is rendered; Matching says "skills
 * only - no score"; no hiring / score / ranking vocabulary is introduced;
 * loading, error and zero-data states exist; the layout is RTL-safe; there is
 * no hard-coded user-facing text; and the page is HR-workspace only.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { hr } from '../src/i18n/dictionaries/hr';
import { nav } from '../src/i18n/dictionaries/nav';
import { canAccessPage } from '../src/services/access';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

// Comments explain what the page is NOT (a score, a ranking...); they are not
// rendered, so the source scans below look at the code without them.
const page = read('../src/pages/hr/AiInterviewAnalyticsPage.tsx')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^\s*\/\/.*$/gm, '');
const types = read('../src/types/index.ts');
const api = read('../src/services/api.ts');
const app = read('../src/App.tsx');
const sidebar = read('../src/components/layout/Sidebar.tsx');
const arabic = /[؀-ۿ]/;
const PAGE_ID = 'hr-ai-interview-analytics';

console.log('1. Labels: English and Arabic, all used');
const used = new Set([...page.matchAll(/'(hr\.aiAnalytics\.[A-Za-z0-9_.]+)'/g)].map((m) => m[1]));
const defined = Object.keys(hr).filter((k) => k.startsWith('hr.aiAnalytics.'));
const missing = [...used].filter((k) => !hr[k]);
check('every hr.aiAnalytics label the page uses exists', missing.length === 0, missing.join(','));
check('every one has English text', defined.every((k) => hr[k].en.trim().length > 0));
const noArabic = defined.filter((k) => !arabic.test(hr[k].ar));
check('every one has Arabic text', noArabic.length === 0, noArabic.join(','));
const unused = defined.filter((k) => !used.has(k));
check('no hr.aiAnalytics label is defined and unused', unused.length === 0, unused.join(','));
for (const key of [`nav.${PAGE_ID}`, `page.${PAGE_ID}`]) {
  check(`${key}: English and Arabic (sidebar / top bar)`, !!nav[key] && arabic.test(nav[key].ar));
}

console.log('\n2. Every response field is represented');
const fields: Record<string, string[]> = {
  overview: ['total_interviews', 'scheduled', 'in_progress', 'completed'],
  activity: ['answers_recorded', 'main_questions_reached', 'follow_ups_answered', 'highest_question_reached'],
  analysis: ['completed', 'pending', 'failed'],
  context: ['job', 'cv', 'matching'],
  question_flow: ['main_questions', 'follow_ups', 'not_reached', 'order_comparable'],
};
const typeBlock = types.slice(types.indexOf('export interface AiInterviewAnalytics'),
  types.indexOf('}\n\n', types.indexOf('export interface AiInterviewAnalytics')) + 1);
for (const [group, keys] of Object.entries(fields)) {
  check(`type ${group}: exactly ${keys.join(', ')}`,
    keys.every((k) => typeBlock.includes(`${k}:`)) && typeBlock.includes(`${group}: {`));
  const alias = group === 'question_flow' ? 'flow' : group;
  check(`page renders every ${group} field`, keys.every((k) => page.includes(`${alias}.${k}`)),
    keys.filter((k) => !page.includes(`${alias}.${k}`)).join(','));
}
check('no extra field: the type has exactly the 18 backend fields',
  (typeBlock.match(/^\s{4}[a-z_]+: /gm) || []).length === 18);
check('api: getAiInterviewAnalytics -> GET /ai-interview/analytics through apiFetch',
  api.includes('async getAiInterviewAnalytics(): Promise<AiInterviewAnalytics>')
  && api.includes('apiFetch<AiInterviewAnalytics>("/ai-interview/analytics")'));

console.log('\n3. Wording: descriptive only');
check('Matching says "Skills only — no score" (English) and the Arabic equivalent',
  hr['hr.aiAnalytics.context.matchingHint'].en === 'Skills only — no score'
  && hr['hr.aiAnalytics.context.matchingHint'].ar.includes('دون درجة')
  && page.includes("description={t('hr.aiAnalytics.context.matchingHint')}"));
check('a notice says it is recorded activity and not a hiring decision',
  /not a hiring decision/.test(hr['hr.aiAnalytics.noticeTitle'].en) && page.includes("t('hr.aiAnalytics.noticeBody')"));
check('order not comparable is explained; today\'s bank is not called the original plan',
  /cannot be compared with today's Question Bank/.test(hr['hr.aiAnalytics.order.notComparableNote'].en)
  && /not necessarily the original session plan/.test(hr['hr.aiAnalytics.planNote'].en)
  && page.includes("t('hr.aiAnalytics.order.notComparableNote')"));
const english = defined.map((k) => hr[k].en).join(' \n ');
// The only permitted uses: "no score" and "not a hiring decision".
const cleaned = english.replace(/no score/gi, '').replace(/not a hiring decision/gi, '');
const forbidden = cleaned.match(/\b(score\w*|rank\w*|rating\w*|percent\w*|recommend\w*|hir(e|ed|ing)|reject\w*|suitab\w*|reasoning|performance|GPT|model)\b|%/gi) || [];
check('no score / ranking / percentage / recommendation / hiring / reasoning vocabulary', forbidden.length === 0,
  forbidden.join(','));
check('the page renders no percentage or score of its own', !/%|score|rank/i.test(page.replace(/matchingHint/g, '')));

console.log('\n4. States');
check('loading state', page.includes('<LoadingState') && page.includes("t('hr.aiAnalytics.loading')"));
check('error state with retry', page.includes('<ErrorState') && page.includes('onRetry={() => void load()}'));
check('zero data is a valid state - an explanation, and the zeros still shown',
  page.includes('nothingYet') && page.includes('data-testid="ai-analytics-empty"')
  && page.indexOf('data-testid="ai-analytics-empty"') < page.indexOf('testId="ai-analytics-overview"')
  && !/nothingYet\s*\)\s*return/.test(page));
check('highest question null is labelled, not shown as 0', page.includes("?? t('hr.aiAnalytics.activity.highestNone')"));

console.log('\n5. RTL and no hard-coded text');
const physical = page.match(/\b(ml|mr|pl|pr)-\d|\btext-(left|right)\b|\bborder-(l|r)\b|\b(left|right)-\d|\bspace-x-/g) || [];
check('direction-neutral layout classes only', physical.length === 0, physical.join(','));
const jsxText = [...page.matchAll(/>\s*([A-Za-z][^<>{}]*[A-Za-z])\s*</g)].map((m) => m[1].trim());
check('no hard-coded text between JSX tags', jsxText.length === 0, jsxText.join(' | '));
const literalProps = [...page.matchAll(/\b(title|subtitle|description|label|placeholder|message)="([^"]+)"/g)];
check('no hard-coded user-facing attribute strings', literalProps.length === 0, literalProps.map((m) => m[0]).join(','));

console.log('\n6. Entry point: the HR workspace only');
check('PageId declared and one HR sidebar entry',
  sidebar.includes(`| '${PAGE_ID}'`) && (sidebar.match(new RegExp(`id: '${PAGE_ID}'`, 'g')) || []).length === 1);
check('App renders it', app.includes(`case '${PAGE_ID}':`) && app.includes('<AiInterviewAnalyticsPage />'));
const access = [1, 2, 3, 4, 5].map((r) => canAccessPage(r, PAGE_ID as never));
check('Admin and HR can open it; Manager, Employee and Applicant cannot',
  JSON.stringify(access) === JSON.stringify([true, true, false, false, false]), JSON.stringify(access));

console.log(`\n  ${failed === 0 ? 'All AI Interview analytics checks passed.' : `${failed} analytics check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
