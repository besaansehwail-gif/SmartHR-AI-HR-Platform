/** Permanent AI Interview fixture frontend contract; static and offline. */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, root)), 'utf8');
const page = read('frontend/src/pages/applicant/AiInterviewPage.tsx');
const types = read('frontend/src/types/index.ts');
const dictionary = read('frontend/src/i18n/dictionaries/aiInterview.ts');
const api = read('frontend/src/services/api.ts');

let passed = 0;
let failed = 0;
const check = (name: string, condition: boolean) => {
  if (condition) passed += 1;
  else failed += 1;
  console.log(`  ${condition ? 'PASS' : 'FAIL'}  ${name}`);
};

check('the API listing carries an explicit test-fixture discriminator',
  types.includes('is_test: boolean'));
check('the permanent test interview is auto-selected unless a caller preselects another',
  page.includes('const testInterview = list.find((interview) => interview.is_test)')
  && page.includes('preferred?.interview_id')
  && page.includes('testInterview?.interview_id'));
check('the existing Start AI Interview action is retained',
  dictionary.includes("'aiInterview.action.start': { en: 'Start AI Interview'"));
check('the fixture is visibly identified as development-only in both locales',
  page.includes("t('aiInterview.test.badge')")
  && page.includes("t('aiInterview.test.notice')")
  && dictionary.includes("'aiInterview.test.badge':")
  && dictionary.includes("'aiInterview.test.notice':"));
check('test interview does not require a start window or consume the attempt limit',
  page.includes("const windowNow = startWindow(selected, now)")
  && page.includes('const attemptsExhausted = selected?.attempts_exhausted === true'));
check('starting still posts the selected Interview ID to the existing session endpoint',
  api.includes('startAiInterviewSession(interviewId: number')
  && api.includes('JSON.stringify({ interview_id: interviewId')
  && page.includes('SmartHRApi.startAiInterviewSession(selectedId, language)'));
check('the same LiveKit, microphone and camera session paths remain in use',
  page.includes('await room.connect(session.server_url, session.participant_token)')
  && page.includes('setMicrophoneEnabled(true)')
  && page.includes('createLocalVideoTrack(')
  && page.includes('publishCameraTrack(room, track)'));

console.log(`\n  ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
