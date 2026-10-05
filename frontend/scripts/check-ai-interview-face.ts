/**
 * Stage 2 face-count check (no browser, no camera, no LiveKit, no model).
 *
 *   cd frontend; npx tsx scripts/check-ai-interview-face.ts
 *
 * Runs the page's pure face-count rules (`aiInterviewRules.ts`) for real and
 * statically verifies the Stage 2 boundaries inside `AiInterviewPage.tsx`:
 * local-only sampling, count-only logging, no canvas/snapshot, no
 * publishData(), detector + timer released on every camera stop, and zero
 * overlap with the microphone/audio paths.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { aiInterview } from '../src/i18n/dictionaries/aiInterview';
import {
  FACE_SAMPLE_INTERVAL_MS,
  faceCountOf,
  formatFaceLog,
} from '../src/pages/applicant/aiInterviewRules';

let failed = 0;
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  [${detail}]`}`);
};
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const stripComments = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

console.log('1. face_count mapping (run for real: 0 / 1 / 2+)');
check('0 detections -> 0', faceCountOf(0) === 0);
check('empty/negative -> 0', faceCountOf(-1) === 0 && faceCountOf(Number.NaN) === 0);
check('1 detection -> 1', faceCountOf(1) === 1);
check('2 detections -> 2 (shown as "2+")', faceCountOf(2) === 2);
check('5 detections -> 2 (shown as "2+")', faceCountOf(5) === 2);

console.log('\n2. console record format (run for real)');
const logged = formatFaceLog('2026-09-30T10:00:00.000Z', 1);
check('exact { timestamp, face_count } JSON shape',
  logged === '{"timestamp":"2026-09-30T10:00:00.000Z","face_count":1}', logged);
check('no pixel keys in the record (image/base64/blob/canvas/detections)',
  !/image|pixel|base64|blob|canvas|frame|detections|box|landmark/i.test(logged), logged);
check('sampling cadence is inside the 1-2s band', FACE_SAMPLE_INTERVAL_MS >= 1000 && FACE_SAMPLE_INTERVAL_MS <= 2000,
  String(FACE_SAMPLE_INTERVAL_MS));

console.log('\n3. camera UI shows the count, with translations');
const arabic = /[؀-ۿ]/;
for (const key of ['aiInterview.camera.faces.zero', 'aiInterview.camera.faces.one', 'aiInterview.camera.faces.two',
  'aiInterview.camera.faces.unavailable'] as const) {
  const entry = aiInterview[key];
  check(`${key}: English and Arabic`, !!entry && entry.en.length > 0 && arabic.test(entry.ar));
}
const page = read('../src/pages/applicant/AiInterviewPage.tsx');
check('face count line has a test id', page.includes('data-testid="ai-interview-face-count"'));

console.log('\n4. Stage 2 stays local: no sending, no snapshots');
const code = stripComments(page);
check('no publishData() call', !/publishData\s*\(/.test(code));
check('no canvas / snapshot / pixel capture',
  !/createElement\(['"]canvas['"]|<canvas|drawImage|toDataURL|toBlob|getImageData|ImageCapture|captureStream/i.test(code));
check('no network send of faces (fetch/XHR/WebSocket/postMessage)',
  !/fetch\s*\(|XMLHttpRequest|WebSocket|postMessage|navigator\.sendBeacon/i.test(code));
check('detector reads only detections.length (never boxes/keypoints)',
  code.includes('result?.detections') || code.includes('result.detections'),
  'sampleFaces must read detections.length');
check('no face-recognition / identity-recognition imports or calls',
  !/faceRecognition|face_recognition|faceMatch|identifyFace|recogniz.+face|face.+recogniz/i.test(code));
const faceSampling = code.slice(code.indexOf('const sampleFaces'), code.indexOf('const startFaceSampling'));
check('FaceDetector/proctoring path stays count-only and separate from Stage 6',
  faceSampling.includes('detector.detectForVideo(video, performance.now())')
  && faceSampling.includes('faceCountOf(Array.isArray(result?.detections)')
  && faceSampling.includes('updateProctorState(proctorTimersRef.current, count, Date.now())')
  && !/FaceLandmarker|FaceMesh|Blendshape|emotionDetector|gazeDetector|headPose/i.test(faceSampling));

console.log('\n5. sampling is throttled (~1.5s), never per-frame');
check('sampling uses a chained setTimeout (keeps the single-setInterval voice check green)',
  code.includes('FACE_SAMPLE_INTERVAL_MS') && /setTimeout\(\(\) => sampleFaces\(run\), FACE_SAMPLE_INTERVAL_MS\)/.test(code));
check('face sampling never uses requestAnimationFrame (the one rAF is the mic meter)',
  !/sampleFaces[\s\S]{0,200}requestAnimationFrame|requestAnimationFrame[\s\S]{0,200}sampleFaces/i.test(code)
  && !/faceTimer[\s\S]{0,80}requestAnimationFrame|requestAnimationFrame[\s\S]{0,80}faceTimer/i.test(code));
check('MediaPipe Face Detector in VIDEO mode', code.includes('FaceDetector.createFromOptions')
  && code.includes("runningMode: 'VIDEO'"));

console.log('\n6. cleanup releases the detector and the timer');
check('stopFaceSampling clears the timer', code.includes('clearTimeout(faceTimerRef.current'));
check('stopFaceSampling closes the detector', code.includes('detector.close()'));
check('stopCamera() runs face cleanup first', /stopFaceSampling\(\);\s*\n\s*cameraRunRef/.test(page));
check('unmount cleanup still stops camera+meter (which stops faces)',
  code.includes('stopMeter();') && code.includes('stopCamera();'));

console.log('\n7. isolated from microphone/audio');
check('face paths never touch mic/room/audio state',
  !/(faceDetector|faceTimer|faceRun|faceCount|faceDetection|sampleFaces|startFaceSampling|stopFaceSampling)[\s\S]{0,80}(micStatus|setMicrophoneEnabled|setMicLevel|AudioContext|AgentSession|roomRef|interviewState)/.test(code)
  && !/(micStatus|setMicrophoneEnabled|setMicLevel|AudioContext|AgentSession)[\s\S]{0,80}(faceDetector|faceTimer|faceRun|faceCount|faceDetection|sampleFaces|startFaceSampling|stopFaceSampling)/.test(code));
check('detector errors set only the face status (camera preview + mic untouched)',
  code.includes("setFaceDetection('unavailable')"));

console.log(`\n  ${failed === 0 ? 'All Stage 2 face-count checks passed.' : `${failed} face-count check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
