/**
 * AI Interview voice UX (Phase 11.6.1), checked rather than assumed.
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-voice-ux.ts
 *
 * No browser, no LiveKit, no model. Runs the page's state rules
 * (`aiInterviewRules.ts`) for real over the REAL sources - the page phase,
 * LiveKit's connection states (read from livekit-client's own type
 * definitions), the interview controller's states and LiveKit's agent states -
 * and checks every state shown has a translated label, that nothing is
 * simulated, that the wording never evaluates the applicant, and that the
 * layout is RTL-safe with no hard-coded text.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { aiInterview } from '../src/i18n/dictionaries/aiInterview';
import {
  AGENT_STATES,
  CONNECTIONS,
  FINAL_START_ERRORS,
  INTERVIEW_STATES,
  MIC_STATUSES,
  TURN_STEPS,
  VIEW_STATES,
  connectionOf,
  micFailureOf,
  startRetryAllowed,
  turnOf,
  viewStateOf,
} from '../src/pages/applicant/aiInterviewRules';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const stripComments = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

const pageRaw = read('../src/pages/applicant/AiInterviewPage.tsx');
const page = stripComments(pageRaw);
const arabic = /[؀-ۿ]/;
const has = (key: string) => !!aiInterview[key] && aiInterview[key].en.trim() !== '' && arabic.test(aiInterview[key].ar);

console.log('1. Every state shown maps to a real source');
const lkEnum = read('../node_modules/livekit-client/dist/src/room/Room.d.ts');
const lkStates = [...(lkEnum.match(/enum ConnectionState \{([\s\S]*?)\}/)?.[1] ?? '').matchAll(/= "([^"]+)"/g)].map((m) => m[1]);
check('livekit-client ConnectionState read from its own type definitions', lkStates.length >= 4, lkStates.join(','));
check('every LiveKit connection state is folded into a shown connection state',
  lkStates.every((s) => CONNECTIONS.includes(connectionOf(s))), lkStates.map((s) => `${s}->${connectionOf(s)}`).join(' '));
check('LiveKit reconnecting / signalReconnecting -> "reconnecting"',
  connectionOf('reconnecting') === 'reconnecting' && connectionOf('signalReconnecting') === 'reconnecting');
check('the page takes the connection from RoomEvent.ConnectionStateChanged, not a timer',
  page.includes('RoomEvent.ConnectionStateChanged') && page.includes('setConnection(connectionOf(state))'));

const reach: Record<string, string> = {};
const note = (v: string, how: string) => { reach[v] = reach[v] ?? how; };
note(viewStateOf('connecting', null, false, null, null), 'phase connecting');
note(viewStateOf('connected', 'reconnecting', true, 'listening', 'listening'), 'LiveKit reconnecting');
note(viewStateOf('connected', 'connected', false, null, null), 'agent not yet in the room');
note(viewStateOf('error', null, false, null, null), 'phase error');
note(viewStateOf('ended', 'disconnected', false, null, null), 'phase ended');
for (const s of INTERVIEW_STATES) note(viewStateOf('connected', 'connected', true, s, null), `controller ${s}`);
for (const a of AGENT_STATES) note(viewStateOf('connected', 'connected', true, null, a), `agent ${a}`);
check('every shown state is reachable from a real input', VIEW_STATES.every((v) => v in reach),
  VIEW_STATES.filter((v) => !(v in reach)).join(','));
check('no real input produces a state outside the list', Object.keys(reach).every((v) => (VIEW_STATES as string[]).includes(v)));
const map = (s: (typeof INTERVIEW_STATES)[number]) => viewStateOf('connected', 'connected', true, s, null);
check('controller intro / asking / speaking -> "Interviewer is speaking"',
  ['intro', 'asking', 'speaking'].every((s) => map(s as never) === 'speaking'));
check('controller listening -> "Your turn"', map('listening') === 'yourTurn');
check('controller processing / follow-up decision / adaptive selection -> "Thinking" (never "speaking")',
  ['processing', 'follow_up_decision', 'adaptive_selection'].every((s) => map(s as never) === 'thinking'));
check('controller ending -> "Finishing" - distinct from speaking and from completed',
  map('ending') === 'ending' && map('ending') !== 'speaking');
check('nothing known -> "waiting", never "Your turn" (no fake listening)',
  viewStateOf('connected', 'connected', true, null, null) === 'waiting'
  && viewStateOf('connected', 'connected', true, null, 'initializing') === 'waiting');
check('the turn strip lights only real turns', turnOf('speaking') === 'interviewer' && turnOf('yourTurn') === 'you'
  && turnOf('thinking') === 'thinking' && turnOf('waiting') === null && turnOf('failed') === null);
check('completed is its own screen (the finished card), not a status-panel state',
  page.includes("view === 'complete'") && page.includes("t('aiInterview.complete.title')") && !VIEW_STATES.includes('completed' as never));

console.log('\n2. Microphone and errors');
check('microphone failures classified from the browser\'s own error name',
  micFailureOf({ name: 'NotAllowedError' }) === 'denied' && micFailureOf({ name: 'NotFoundError' }) === 'unavailable'
  && micFailureOf({ name: 'NotReadableError' }) === 'error' && micFailureOf(new Error('x')) === 'error');
check('the microphone status is the real outcome of setMicrophoneEnabled',
  page.includes("setMicStatus('pending')") && page.includes('await room.localParticipant.setMicrophoneEnabled(true)')
  && page.includes("setMicStatus('active')") && page.includes('setMicStatus(failure)'));
check('LiveKit\'s MediaDevicesError is classified too', page.includes('RoomEvent.MediaDevicesError, (e: Error)'));
check('"You are speaking" comes from LiveKit\'s IsSpeakingChanged', page.includes('ParticipantEvent.IsSpeakingChanged')
  && page.includes('setLocalSpeaking(speaking)'));
check('microphone blocked: a clear instruction, in both languages', has('aiInterview.mic.help.denied')
  && /Allow microphone access/.test(aiInterview['aiInterview.mic.help.denied'].en));
check('connection error state', has('aiInterview.error.connection') && page.includes("t('aiInterview.error.connection')"));
check('agent unavailable / cannot continue states kept', page.includes("t('aiInterview.error.agentLeft')")
  && page.includes("t('aiInterview.ended.title')"));
check('no exception text reaches the screen (our sentences only; backend refusals keep their own detail)',
  !page.includes('e instanceof Error ? e.message') && page.includes("t('aiInterview.error.startFailed')"));
check('no "Try again" after a final refusal (backend codes), no restart after completion',
  FINAL_START_ERRORS.every((c) => !startRetryAllowed(c)) && startRetryAllowed('session_active') && startRetryAllowed(null)
  && page.includes("(phase !== 'error' || retryAllowed)")
  && page.includes('!finishedInterview && retryAllowed && !attemptsExhausted && restartControl'));

console.log('\n2b. Recovery (Phase 11.6.3)');
check('a microphone lost DURING the interview (the track\'s real "ended" event) -> microphone problem + instruction',
  page.includes("mediaStreamTrack.addEventListener('ended'") && page.includes("setMicStatus('error')")
  && page.includes("setError(t('aiInterview.mic.help.error'))"));
const listening = viewStateOf('connected', 'connected', true, 'listening', 'listening');
check('reconnect returns to exactly the state it left (no replay, no advance)',
  viewStateOf('connected', 'reconnecting', true, 'listening', 'listening') === 'reconnecting'
  && viewStateOf('connected', 'connected', true, 'listening', 'listening') === listening && listening === 'yourTurn');
check('a reconnect that fails ends as "stopped" - never the completed screen',
  viewStateOf('ended', 'disconnected', false, 'listening', null) === 'stopped');

console.log('\n2c. State integrity (Phase 11.6.4)');
check('attempts exhausted (the backend\'s count, in the list) -> no Start, no restart, the reason shown',
  page.includes('const attemptsExhausted = selected?.attempts_exhausted === true')
  && page.includes("(phase !== 'error' || retryAllowed) && !attemptsExhausted")
  && page.includes('retryAllowed && !attemptsExhausted && restartControl')
  && page.includes("t('aiInterview.errorCode.attempts_exhausted')"));
check('after a session ends, the list is re-read from the backend (an event - no timer, nothing created)',
  /if \(phase !== 'ended' && phase !== 'error'\) return;\s*SmartHRApi\.getMyAiInterviews\(\)/.test(page));
check('Start is only ever a click - no automatic new attempt on load or refresh',
  (page.match(/onClick=\{start\}/g) || []).length === 2 && !/useEffect\([^)]*start\(\)/.test(page));
check('"Your turn" only from a listening state; "Thinking" never after the session ended; "Finishing" never completed',
  viewStateOf('ended', 'disconnected', false, 'processing', 'thinking') === 'stopped'
  && viewStateOf('connected', 'connected', true, 'ending', null) === 'ending'
  && INTERVIEW_STATES.filter((s) => viewStateOf('connected', 'connected', true, s, null) === 'yourTurn')
    .join() === 'listening');

console.log('\n3. Labels: English and Arabic, none missing, none unused');
const families: [string, readonly string[]][] = [
  ['aiInterview.state.', VIEW_STATES.flatMap((v) => (v === 'failed' ? [v] : [v, `${v}Hint`]))],
  ['aiInterview.connection.', CONNECTIONS],
  ['aiInterview.mic.status.', MIC_STATUSES],
  ['aiInterview.mic.help.', ['denied', 'unavailable', 'error']],
  ['aiInterview.turn.', TURN_STEPS],
  ['aiInterview.interviewState.', INTERVIEW_STATES],
  ['aiInterview.agentState.', AGENT_STATES],
];
for (const [prefix, values] of families) {
  const missing = values.filter((v) => !has(prefix + v));
  check(`${prefix}* for every real value, both languages`, missing.length === 0, missing.join(','));
}
const src = [
  pageRaw, read('../src/pages/applicant/aiInterviewRules.ts'), read('../src/pages/applicant/ApplicantApplicationsPage.tsx'),
  read('../src/pages/applicant/ApplicantDashboardPage.tsx'),
].join('\n');
const literal = new Set([...src.matchAll(/'(aiInterview\.[A-Za-z0-9_.]+)'/g)].map((m) => m[1]));
const templates = [...src.matchAll(/`(aiInterview\.[A-Za-z0-9_.]*?)\$\{/g)].map((m) => m[1]);
const defined = Object.keys(aiInterview);
const missingLiteral = [...literal].filter((k) => !aiInterview[k]);
check('every literal aiInterview key used exists', missingLiteral.length === 0, missingLiteral.join(','));
check('every aiInterview key has English and Arabic', defined.every(has), defined.filter((k) => !has(k)).join(','));
const unused = defined.filter((k) => !literal.has(k) && !templates.some((p) => k.startsWith(p)));
check('no aiInterview key is defined and unused', unused.length === 0, unused.join(','));

console.log('\n4. Nothing simulated');
check('no random numbers anywhere on the page', !/Math\.random/.test(page));
check('the microphone level comes only from an AnalyserNode on the published track',
  page.includes('createAnalyser()') && page.includes('getByteTimeDomainData') && (page.match(/setMicLevel\(/g) || []).length === 2);
check('the only interval is the start-window clock - no timer drives a level, a state or progress',
  (page.match(/setInterval\(/g) || []).length === 1 && /setInterval\(\(\) => setNow\(Date\.now\(\)\)/.test(page));
check('no waveform / visualiser component', !/waveform|visuali[sz]er|oscilloscope/i.test(page));

console.log('\n5. Wording');
const voiceKeys = defined.filter((k) => /^aiInterview\.(state|mic|turn|connection)\./.test(k)
  || ['aiInterview.error.connection', 'aiInterview.error.startFailed'].includes(k));
const voiceText = voiceKeys.map((k) => aiInterview[k].en).join(' \n ');
const bad = voiceText.match(/\b(score\w*|rating|rank\w*|percent\w*|recommend\w*|hir(e|ed|ing)|evaluat\w*|assess\w*|correct\w*|good answer|quality|judg\w*)\b/gi) || [];
check('voice labels never evaluate the applicant or their answer', bad.length === 0, bad.join(','));
check('"You are speaking" is about sound, not the answer', !/answer/i.test(aiInterview['aiInterview.mic.speaking'].en)
  && !/answer/i.test(aiInterview['aiInterview.mic.notSpeaking'].en));
check('"Thinking" does not claim analysis or speech recognition',
  !/analy|recogni|transcrib/i.test(aiInterview['aiInterview.state.thinkingHint'].en));

console.log('\n6. RTL, accessibility, no hard-coded text');
const physical = page.match(/\b(ml|mr|pl|pr)-\d|\btext-(left|right)\b|\bborder-(l|r)\b|\b(left|right)-\d|\bspace-x-/g) || [];
check('direction-neutral layout classes only', physical.length === 0, physical.join(','));
check('status is never colour alone: the turn step carries text and aria-current',
  page.includes("aria-current={current ? 'step' : undefined}") && page.includes("t('aiInterview.turn.now')"));
check('pills carry text beside their icon', page.includes("t(`aiInterview.connection.${connection}`)")
  && page.includes("t(`aiInterview.mic.status.${micStatus}`)"));
check('status changes are announced (aria-live)', (page.match(/aria-live="polite"/g) || []).length >= 2);
// Text between a tag's ">" and the next "<" - not an arrow's "=>" (code).
const jsxText = [...page.matchAll(/(?<!=)>\s*([A-Za-z][^<>{}]*[A-Za-z])\s*</g)].map((m) => m[1].trim());
check('no hard-coded text between JSX tags', jsxText.length === 0, jsxText.join(' | '));
const literalProps = [...page.matchAll(/\b(title|subtitle|description|label|placeholder|message|aria-label)="([^"]*[A-Za-z][^"]*)"/g)];
check('no hard-coded user-facing attribute strings', literalProps.length === 0, literalProps.map((m) => m[0]).join(','));

console.log(`\n  ${failed === 0 ? 'All AI Interview voice UX checks passed.' : `${failed} voice UX check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
