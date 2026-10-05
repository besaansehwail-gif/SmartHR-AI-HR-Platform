/**
 * Per-session AI Interview language flow, checked without a browser or LiveKit.
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-language.ts
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { aiInterview } from '../src/i18n/dictionaries/aiInterview';

const page = readFileSync(
  fileURLToPath(new URL('../src/pages/applicant/AiInterviewPage.tsx', import.meta.url)),
  'utf8',
);
const api = readFileSync(
  fileURLToPath(new URL('../src/services/api.ts', import.meta.url)),
  'utf8',
);
let failed = 0;
let passed = 0;

const check = (name: string, ok: boolean) => {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
};

const startWithLanguage = page.slice(
  page.indexOf('const startWithLanguage'),
  page.indexOf('const start = useCallback'),
);
const startWrapper = page.slice(
  page.indexOf('const start = useCallback'),
  page.indexOf('const confirmLanguageAndStart'),
);
const confirmHandler = page.slice(
  page.indexOf('const confirmLanguageAndStart'),
  page.indexOf('/** A refused Start'),
);
const restartControl = page.slice(page.indexOf('const restartControl'), page.indexOf('return (\n    <div'));
const readyControls = page.slice(page.indexOf("{view === 'ready'"), page.indexOf('/* ------------------------------------------ session / complete'));
const modalOpen = page.indexOf('isOpen={languageModalOpen}');
const modalStart = page.lastIndexOf('<Modal', modalOpen);
const modal = page.slice(modalStart, page.indexOf('</Modal>', modalStart));

console.log('1. Selection gates every Start path');
check('Start wrapper only opens the language modal', startWrapper.includes('setLanguageModalOpen(true)')
  && !startWrapper.includes('startAiInterviewSession') && !startWrapper.includes('room.connect'));
check('session creation occurs only in the confirmed language handler path',
  confirmHandler.includes('startWithLanguage(selectedLanguage)')
  && startWithLanguage.includes('startAiInterviewSession(selectedId, language)'));
check('room.connect remains downstream of session creation',
  startWithLanguage.indexOf('startAiInterviewSession') < startWithLanguage.indexOf('room.connect'));
check('ready Start, Retry and Start-New-Session controls all use the gated wrapper',
  readyControls.includes('onClick={start}')
  && readyControls.includes("t('aiInterview.action.retry')")
  && readyControls.includes("t('aiInterview.action.start')")
  && restartControl.includes('onClick={start}'));
check('cancel only closes the modal and cannot start a session',
  modal.includes("onClose={() => setLanguageModalOpen(false)}")
  && modal.includes("onClick={() => setLanguageModalOpen(false)}")
  && !modal.includes('startWithLanguage')
  && confirmHandler.includes('startWithLanguage(selectedLanguage)'));
check('selection is required before Continue', modal.includes('disabled={selectedLanguage === null}')
  && modal.includes("language === 'en' || language === 'ar'"));
check('chosen language is visible in the select before confirmation',
  modal.includes('value={selectedLanguage ?? \'\'}')
  && modal.includes("t('aiInterview.language.english')")
  && modal.includes("t('aiInterview.language.arabic')"));
check('language selector uses the chosen language direction without changing global locale',
  modal.includes("dir={selectedLanguage === 'ar' ? 'rtl' : 'ltr'}")
  && modal.includes('lang={selectedLanguage ?? undefined}')
  && !modal.includes('setLocale'));
check('API includes selected language in the session request',
  api.includes('startAiInterviewSession(interviewId: number, language?:')
  && api.includes('...(language ? { language } : {})'));

console.log('\n2. Bilingual labels');
for (const key of [
  'aiInterview.language.title',
  'aiInterview.language.subtitle',
  'aiInterview.language.label',
  'aiInterview.language.choose',
  'aiInterview.language.english',
  'aiInterview.language.arabic',
  'aiInterview.language.cancel',
  'aiInterview.language.continue',
]) {
  check(`${key} has English and Arabic`, !!aiInterview[key]?.en.trim() && !!aiInterview[key]?.ar.trim());
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
