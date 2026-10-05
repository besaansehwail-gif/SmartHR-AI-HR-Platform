/**
 * Stage 3 proctoring check (no browser, no camera, no LiveKit, no model).
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-proctor.ts
 *
 * Runs the pure sustained-condition rules (`aiInterviewRules.ts`) for real
 * over simulated 1.5s sample streams, and statically verifies the Stage 3
 * boundaries inside `AiInterviewPage.tsx`: same sampling loop, metadata-only
 * flags, no canvas/snapshot, no publishData(), and zero overlap with the
 * microphone/audio paths. Also re-asserts Stage 2 face_count is unchanged.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { aiInterview } from '../src/i18n/dictionaries/aiInterview';
import {
  MULTIPLE_FACES_SUSTAINED_MS,
  NO_FACE_SUSTAINED_MS,
  ProctorTimers,
  faceCountOf,
  formatFaceLog,
  formatProctorFlagLog,
  initialProctorTimers,
  isProctorFlag,
  updateProctorState,
} from '../src/pages/applicant/aiInterviewRules';
import type { FaceCount, ProctorState } from '../src/pages/applicant/aiInterviewRules';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const stripComments = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const STEP = 1500;
const feed = (t: ProctorTimers, counts: FaceCount[], t0 = 1_000_000): ProctorState[] => {
  let now = t0;
  const out: ProctorState[] = [];
  for (const c of counts) {
    out.push(updateProctorState(t, c, now));
    now += STEP;
  }
  return out;
};
const last = <T,>(xs: T[]): T => xs[xs.length - 1];

console.log('1. normal + below-threshold behaviour');
check('1) face_count 1 -> normal', last(feed(initialProctorTimers(), [1])) === 'normal');
check('2) 0 below 10s -> no_face, never sustained',
  feed(initialProctorTimers(), [0, 0, 0, 0, 0, 0]).every((s) => s === 'no_face'));
check('6) 2 below 5s -> multiple_faces, never sustained',
  feed(initialProctorTimers(), [2, 2, 2]).every((s) => s === 'multiple_faces'));

console.log('2. sustained flags fire');
check('3) 0 reaching 10s -> no_face_sustained',
  last(feed(initialProctorTimers(), [0, 0, 0, 0, 0, 0, 0, 0])) === 'no_face_sustained');
check('7) 2+ reaching 5s -> multiple_faces_sustained',
  last(feed(initialProctorTimers(), [2, 2, 2, 2, 2])) === 'multiple_faces_sustained');

console.log('3. timers reset immediately on normal');
const t4 = initialProctorTimers();
feed(t4, [0, 0, 0, 0]);
check('4) 0 then 1 before 10s -> back to normal, next 0 restarts',
  last(feed(t4, [1])) === 'normal'
  && last(feed(t4, [0], 1_000_000 + 5 * STEP)) === 'no_face');
const t8 = initialProctorTimers();
feed(t8, [2, 2]);
check('8) 2+ then 1 before 5s -> timer resets',
  last(feed(t8, [1])) === 'normal'
  && last(feed(t8, [2], 1_000_000 + 3 * STEP)) === 'multiple_faces');
const t5 = initialProctorTimers();
feed(t5, [0, 0, 0, 0, 0]);
feed(t5, [1]);
check('5) 0 -> normal -> 0 periods do not accumulate',
  feed(t5, [0, 0, 0, 0, 0]).every((s) => s === 'no_face'));
console.log('4. flicker never triggers');
check('9) rapid 1 <-> 2+ flicker does not trigger',
  feed(initialProctorTimers(), [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]).every((s) => !isProctorFlag(s)));
check('10) rapid 1 <-> 0 flicker does not trigger',
  feed(initialProctorTimers(), [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]).every((s) => !isProctorFlag(s)));
const tSwitch = initialProctorTimers();
feed(tSwitch, [0, 0, 0, 0, 0, 0]);
const switched = feed(tSwitch, [2, 2, 2, 2, 2], 1_000_000 + 6 * STEP);
check('switching 0 -> 2+ resets: 2+ needs its own full 5s',
  switched[0] === 'multiple_faces' && switched[switched.length - 1] === 'multiple_faces_sustained');

console.log('5. flag records are metadata only');
const flagA = formatProctorFlagLog('2026-09-30T10:00:00.000Z', 0, 'no_face_sustained');
const flagB = formatProctorFlagLog('2026-09-30T10:00:05.000Z', 2, 'multiple_faces_sustained');
check('11) exact { timestamp, face_count, flag } shape',
  flagA === '{"timestamp":"2026-09-30T10:00:00.000Z","face_count":0,"flag":"no_face_sustained"}'
  && flagB === '{"timestamp":"2026-09-30T10:00:05.000Z","face_count":2,"flag":"multiple_faces_sustained"}',
  `${flagA} | ${flagB}`);
check('12) no image/frame/pixel keys in flag records',
  !/image|pixel|base64|blob|canvas|frame|screenshot|video|detections|box|landmark|embed/i.test(flagA + flagB));
check('thresholds are the conservative defaults (10s / 5s)',
  NO_FACE_SUSTAINED_MS === 10_000 && MULTIPLE_FACES_SUSTAINED_MS === 5_000);

console.log('6. Stage 2 face_count unchanged');
check('13) 0/1/2+ mapping intact',
  faceCountOf(0) === 0 && faceCountOf(1) === 1 && faceCountOf(2) === 2 && faceCountOf(9) === 2);
check('Stage 2 log shape intact',
  formatFaceLog('2026-09-30T10:00:00.000Z', 1) === '{"timestamp":"2026-09-30T10:00:00.000Z","face_count":1}');

console.log('7. UI strings for the proctor states');
const arabic = /[؀-ۿ]/;
for (const key of ['aiInterview.camera.proctor.normal', 'aiInterview.camera.proctor.no_face',
  'aiInterview.camera.proctor.multiple_faces', 'aiInterview.camera.proctor.no_face_sustained',
  'aiInterview.camera.proctor.multiple_faces_sustained'] as const) {
  const entry = aiInterview[key];
  check(`${key}: English and Arabic`, !!entry && entry.en.length > 0 && arabic.test(entry.ar));
}
const page = read('../src/pages/applicant/AiInterviewPage.tsx');
check('proctor line has a test id', page.includes('data-testid="ai-interview-proctor"'));
check('no alarming wording in proctor strings',
  !Object.entries(aiInterview).filter(([k]) => k.startsWith('aiInterview.camera.proctor'))
    .some(([, e]) => /warning|violat|cheat|suspicious|prohibit|alert/i.test(e.en)));

console.log('8. Stage 3 stays local on the same loop');
const code = stripComments(page);
check('no publishData() call', !/publishData\s*\(/.test(code));
check('no canvas or pixel capture',
  !/createElement\(['"]canvas['"]|<canvas|drawImage|toDataURL|toBlob|getImageData|ImageCapture|captureStream/i.test(code));
check('no network send of proctor data',
  !/fetch\s*\(|XMLHttpRequest|WebSocket|postMessage|navigator\.sendBeacon/i.test(code));
check('no second sampling timer (one setTimeout chain feeds both stages)',
  (code.match(/setTimeout\(\(\) => sampleFaces\(run\), FACE_SAMPLE_INTERVAL_MS\)/g) || []).length === 2
  && !/setInterval\(\(\) => sampleFaces|setInterval\(\(\) => updateProctor/.test(code));
check('detector unchanged (VIDEO FaceDetector, detections.length only)',
  code.includes("runningMode: 'VIDEO'") && code.includes('result?.detections'));
const faceSampling = code.slice(code.indexOf('const sampleFaces'), code.indexOf('const startFaceSampling'));
check('proctor decision remains based only on FaceDetector face_count',
  faceSampling.includes('faceCountOf(Array.isArray(result?.detections)')
  && faceSampling.includes('updateProctorState(proctorTimersRef.current, count, Date.now())')
  && !/FaceLandmarker|FaceMesh|Blendshape|emotionDetector|gazeDetector|gazeEstimator|headPose/i.test(faceSampling));

console.log('9. flags never touch the interview; cleanup resets timers');
check('flag path only sets proctor display state',
  code.includes('const state = updateProctorState(proctorTimersRef.current, count, Date.now());')
  && code.includes('setProctorState(state);'));
check('stopFaceSampling resets proctor timers and display',
  code.includes('proctorTimersRef.current = initialProctorTimers()')
  && code.includes('proctorFlagRef.current = null')
  && code.includes('setProctorState(null)'));

console.log('10. isolated from microphone and audio');
check('14) proctor paths never touch mic or room state',
  !/(proctorTimers|proctorFlag|proctorState|updateProctorState|traceProctorFlag)[\s\S]{0,80}(micStatus|setMicrophoneEnabled|setMicLevel|AudioContext|AgentSession|roomRef|interviewState)/.test(code)
  && !/(micStatus|setMicrophoneEnabled|setMicLevel|AudioContext|AgentSession)[\s\S]{0,80}(proctorTimers|proctorFlag|proctorState|updateProctorState|traceProctorFlag)/.test(code));

console.log(`\n  ${failed === 0 ? 'All Stage 3 proctoring checks passed.' : `${failed} proctoring check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);