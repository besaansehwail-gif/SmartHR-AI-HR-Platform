/**
 * Stage 4 camera-proctoring payload check (no browser, no camera, no LiveKit).
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-publish.ts
 *
 * Architecture finding first: the applicant token is minted with
 * `can_publish_data=False` (`app/services/ai_interview_service.py:87`,
 * asserted by `scripts/test_ai_interview_foundation.py:234`), the page only
 * calls `registerTextStreamHandler('lk.transcription')` (receive-only), and no
 * backend/agent code handles data packets - so this script asserts Stage 4
 * does NOT wire `publishData()` and does NOT touch the token/backend. What it
 * DOES test for real is the gated metadata-only payload shape + validator in
 * `aiInterviewRules.ts`: build/validate/serialize, key allow-list, value
 * ranges, and rejection of every image/frame/stream smuggling shape.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  CAMERA_PROCTORING_KEYS,
  CAMERA_PROCTORING_TOPIC,
  CAMERA_PROCTORING_TYPE,
  FACE_SAMPLE_INTERVAL_MS,
  MULTIPLE_FACES_SUSTAINED_MS,
  NO_FACE_SUSTAINED_MS,
  buildCameraProctoringPayload,
  faceCountOf,
  formatProctorFlagLog,
  initialProctorTimers,
  isValidCameraProctoringPayload,
  serializeCameraProctoringPayload,
  updateProctorState,
} from '../src/pages/applicant/aiInterviewRules';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const stripComments = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

console.log('0. architecture: publishing is NOT currently permitted');
const svc = read('../../app/services/ai_interview_service.py');
check('applicant token forbids data publishing', svc.includes('can_publish_data=False'));
const page = read('../src/pages/applicant/AiInterviewPage.tsx');
const code = stripComments(page);
check('Stage 4 wires no publishData() call', !/publishData\s*\(/.test(code));
check('token and backend contracts untouched by Stage 4',
  !/can_publish_data\s*=\s*True/.test(svc) && !/publishData/.test(svc));

console.log('1. valid face_counts are publishable');
check('1) face_count 0 builds + validates + serializes', (() => {
  const p = buildCameraProctoringPayload('2026-10-01T10:00:00.000Z', 0, null);
  const s = serializeCameraProctoringPayload(p);
  return isValidCameraProctoringPayload(p) && s === JSON.stringify(p);
})());

check('2) face_count 1 builds + validates + serializes', (() => {
  const p = buildCameraProctoringPayload('2026-10-01T10:00:01.000Z', 1, null);
  return isValidCameraProctoringPayload(p) && serializeCameraProctoringPayload(p) !== null;
})());
check('3) face_count 2 (2+) builds + validates + serializes', (() => {
  const p = buildCameraProctoringPayload('2026-10-01T10:00:02.000Z', 2, null);
  return isValidCameraProctoringPayload(p) && serializeCameraProctoringPayload(p) !== null;
})());

console.log('2. sustained flags are publishable');
check('4a) no_face_sustained flag payload validates', (() => {
  const p = buildCameraProctoringPayload('2026-10-01T10:00:10.000Z', 0, 'no_face_sustained');
  const s = serializeCameraProctoringPayload(p);
  return isValidCameraProctoringPayload(p)
    && s === '{"type":"camera_proctoring","timestamp":"2026-10-01T10:00:10.000Z","face_count":0,"flag":"no_face_sustained"}';
})());
check('4b) multiple_faces_sustained flag payload validates', (() => {
  const p = buildCameraProctoringPayload('2026-10-01T10:00:05.000Z', 2, 'multiple_faces_sustained');
  return isValidCameraProctoringPayload(p) && serializeCameraProctoringPayload(p) !== null;
})());
check('flag matches the Stage 3 record it came from', (() => {
  const stage3 = formatProctorFlagLog('2026-10-01T10:00:05.000Z', 2, 'multiple_faces_sustained');
  const p = buildCameraProctoringPayload('2026-10-01T10:00:05.000Z', 2, 'multiple_faces_sustained');
  const parsed = JSON.parse(serializeCameraProctoringPayload(p) as string) as { flag: string };
  return stage3 === '{"timestamp":"2026-10-01T10:00:05.000Z","face_count":2,"flag":"multiple_faces_sustained"}'
    && parsed.flag === 'multiple_faces_sustained';
})());

console.log('3. invalid values are rejected');
check('5a) face_count -1 rejected',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: -1, flag: null }));
check('5b) face_count 3 rejected',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: 3, flag: null }));
check('5c) face_count "1" (string) rejected',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: '1', flag: null }));
check('5d) face_count NaN rejected',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: Number.NaN, flag: null }));
check('unknown flag rejected',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: 'looking_away' }));
check('wrong type tag rejected',
  !isValidCameraProctoringPayload({ type: 'face_count', timestamp: 't', face_count: 1, flag: null }));
check('empty timestamp rejected',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: '', face_count: 1, flag: null }));
check('null and arrays rejected', !isValidCameraProctoringPayload(null) && !isValidCameraProctoringPayload([]));
check('serialize returns null for invalid payloads', serializeCameraProctoringPayload(
  { type: CAMERA_PROCTORING_TYPE, timestamp: 't', face_count: 3 as 2, flag: null }) === null);
console.log('4. payload contains ONLY the approved metadata keys');
check('6) exact key set { type, timestamp, face_count, flag }',
  CAMERA_PROCTORING_KEYS.join(',') === 'type,timestamp,face_count,flag'
  && Object.keys(buildCameraProctoringPayload('t', 1, null)).join(',') === 'type,timestamp,face_count,flag');
check('extra keys rejected (detector result smuggling)',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, detections: [] }));
check('extra keys rejected (geometry smuggling)',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, boundingBox: {} }));
check('extra keys rejected (track smuggling)',
  !isValidCameraProctoringPayload({ type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, track: {} }));

console.log('5. no image, stream, or binary shapes can pass');
const poisons = [
  ['7a) image key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, image: 'data:image/png;base64,x' }],
  ['7b) frame key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, frame: [0, 1, 2] }],
  ['7c) pixels key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, pixels: 'AAA=' }],
  ['7d) base64 key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, base64: 'AAA=' }],
  ['8a) MediaStream key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, stream: {} }],
  ['8b) MediaStreamTrack key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, track: {} }],
  ['9a) canvas key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, canvas: {} }],
  ['9b) ImageData key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, imageData: {} }],
  ['9c) Blob key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, blob: {} }],
  ['9d) ArrayBuffer key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, buffer: {} }],
  ['9e) screenshot key', { type: 'camera_proctoring', timestamp: 't', face_count: 1, flag: null, screenshot: 'x' }],
] as const;
for (const [name, poison] of poisons) {
  check(`${name} rejected`, !isValidCameraProctoringPayload(poison));
}

console.log('6. no duplicate loop, Stages 2 and 3 unchanged, audio untouched');
check('10) no duplicate sampling loop (same chained setTimeout, no new timer)',
  (code.match(/setTimeout\(\(\) => sampleFaces\(run\), FACE_SAMPLE_INTERVAL_MS\)/g) || []).length === 2
  && !/setInterval\(\(\) => sampleFaces|setInterval\(\(\) => updateProctor|setInterval\(\(\) => publish|setTimeout\(\(\) => publish/.test(code));
check('11) Stage 2 detector path unchanged',
  code.includes("runningMode: 'VIDEO'") && code.includes('result?.detections')
  && code.includes('FACE_SAMPLE_INTERVAL_MS') && code.includes('setFaceCount(count)'));
check('12) Stage 3 aggregation unchanged',
  code.includes('updateProctorState(proctorTimersRef.current, count, Date.now())')
  && code.includes('setProctorState(state);')
  && code.includes('proctorTimersRef.current = initialProctorTimers()')
  && NO_FACE_SUSTAINED_MS === 10_000 && MULTIPLE_FACES_SUSTAINED_MS === 5_000);
check('13) mic, room, STT, VAD, agent, TTS code paths untouched', (() => {
  const marker = 'Stage 4: reference to the gated payload shape';
  const at = code.indexOf(marker);
  const block = at === -1 ? '' : code.slice(at, at + 1200);
  const leaks = ['setMicrophoneEnabled', 'AudioContext', 'AgentSession', 'registerTextStreamHandler']
    .some((k) => block.includes(k));
  const cross = /(setMicrophoneEnabled|AudioContext|AgentSession|roomRef)[\s\S]{0,80}(buildCameraProctoringPayload|isValidCameraProctoringPayload|serializeCameraProctoringPayload|CAMERA_PROCTORING)/.test(code)
    || /(buildCameraProctoringPayload|isValidCameraProctoringPayload|serializeCameraProctoringPayload|CAMERA_PROCTORING)[\s\S]{0,80}(setMicrophoneEnabled|AudioContext|AgentSession)/.test(code);
  return !leaks && !cross;
})());
check('Stage 2 and 3 pure helpers still behave',
  faceCountOf(2) === 2 && faceCountOf(9) === 2
  && updateProctorState(initialProctorTimers(), 1, 1_000_000) === 'normal');
check('reserved topic is namespaced and referenced once',
  CAMERA_PROCTORING_TOPIC === 'smarthr.camera.proctoring' && code.includes('CAMERA_PROCTORING_TYPE'));

console.log(`\n  ${failed === 0 ? 'All Stage 4 publish-shape checks passed.' : `${failed} publish-shape check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);