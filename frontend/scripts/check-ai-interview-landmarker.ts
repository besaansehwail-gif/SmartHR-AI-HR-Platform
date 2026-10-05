/** Stage 6 Face Landmarker checks (offline; no camera, LiveKit, or model). */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
  FACIAL_SAMPLE_CAPACITY,
  FACIAL_SAMPLE_WINDOW_MS,
  FACIAL_MAX_SAMPLE_GAP_MS,
  FacialSampleBuffer,
  geometrySampleFromResult,
  summarizeFacialMotion,
} from '../src/pages/applicant/facialBehavior';

const root = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, root)), 'utf8');
const page = read('frontend/src/pages/applicant/AiInterviewPage.tsx');
const code = page.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const stripComments = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

let failed = 0;
const check = (name: string, ok: boolean) => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
};

const identityMatrix = () => ({
  rows: 4,
  columns: 4,
  data: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
});
const landmarks = [
  { x: 0.2, y: 0.3, z: 0 },
  { x: 0.8, y: 0.7, z: 0.1 },
  { x: 0.5, y: 0.5, z: -0.1 },
];
const result = (faces = [landmarks], matrices: unknown[] = [identityMatrix()]) => ({
  faceLandmarks: faces,
  facialTransformationMatrixes: matrices,
  faceBlendshapes: [{ categories: [{ categoryName: 'unused', score: 1 }] }],
});
const motionSample = (
  timestampMs: number,
  centerX = 0.5,
  centerY = 0.5,
  yawDeg = 0,
  pitchDeg = 0,
  rollDeg = 0,
) => ({ timestampMs, centerX, centerY, yawDeg, pitchDeg, rollDeg });

console.log('1. Geometry extraction rejects invalid results');
const sample = geometrySampleFromResult(result(), 1_250);
check('valid single-face result yields timestamp, center, and three orientation angles',
  sample !== null && sample.timestampMs === 1_250
  && sample.centerX === 0.5 && sample.centerY === 0.5
  && sample.yawDeg === 0 && sample.pitchDeg === 0 && sample.rollDeg === 0);
const yawRadians = Math.PI / 6;
const yawMatrix = {
  rows: 4,
  columns: 4,
  data: [Math.cos(yawRadians), 0, -Math.sin(yawRadians), 0,
    0, 1, 0, 0, Math.sin(yawRadians), 0, Math.cos(yawRadians), 0,
    0, 0, 0, 1],
};
const extractedYaw = geometrySampleFromResult(result([landmarks], [yawMatrix]), 1)?.yawDeg;
check('yaw extraction follows the declared column-major matrix convention',
  extractedYaw !== undefined && Math.abs(extractedYaw - 30) < 1e-8);
check('only derived numeric fields are returned; blendshapes/raw landmarks are absent',
  sample !== null
  && Object.keys(sample).sort().join(',') === 'centerX,centerY,pitchDeg,rollDeg,timestampMs,yawDeg'
  && Object.values(sample).every((value) => typeof value === 'number'));
check('no face is ignored', geometrySampleFromResult(result([], []), 1) === null);
check('multiple faces are ignored', geometrySampleFromResult(result([landmarks, landmarks], [identityMatrix(), identityMatrix()]), 1) === null);
check('malformed landmark coordinates are ignored',
  geometrySampleFromResult(result([[{ x: Number.NaN, y: 0, z: 0 }]]), 1) === null);
check('missing or invalid transformation matrix is ignored',
  geometrySampleFromResult(result([landmarks], []), 1) === null
  && geometrySampleFromResult(result([landmarks], [{ ...identityMatrix(), data: [Number.NaN] }]), 1) === null);
check('degenerate transformation matrix is ignored',
  geometrySampleFromResult(result([landmarks], [{ ...identityMatrix(), data: Array(16).fill(0) }]), 1) === null);

console.log('\n2. The local temporal buffer is bounded');
check('sampling begins at 2 Hz with a 5-second, 10-sample maximum',
  FACE_LANDMARKER_SAMPLE_INTERVAL_MS === 500
  && FACIAL_SAMPLE_WINDOW_MS === 5_000 && FACIAL_SAMPLE_CAPACITY === 10);
const buffer = new FacialSampleBuffer();
for (let i = 0; i < 1_000; i += 1) {
  buffer.add({ ...sample!, timestampMs: i * 100, centerX: 0.5, centerY: 0.5, yawDeg: i, pitchDeg: 0, rollDeg: 0 });
}
check('long-running input stays bounded and evicts oldest samples', buffer.values().length === 10
  && buffer.values()[0].timestampMs === 99_000);
check('buffer entries contain only the six derived numeric fields',
  buffer.values().every((entry) =>
    Object.keys(entry).sort().join(',') === 'centerX,centerY,pitchDeg,rollDeg,timestampMs,yawDeg'));
buffer.clear();
buffer.add({ ...sample!, timestampMs: 0 });
buffer.add({ ...sample!, timestampMs: 1_000 });
buffer.add({ ...sample!, timestampMs: 6_000 });
check('samples outside the five-second window expire', buffer.values().length === 2
  && buffer.values()[0].timestampMs === 1_000);
buffer.clear();
check('clear releases all derived samples', buffer.values().length === 0);

console.log('\n3. Temporal motion summaries are deterministic and descriptive');
const constant = summarizeFacialMotion([
  motionSample(1_000), motionSample(1_500), motionSample(2_000),
]);
check('constant samples produce zero displacement, angle changes, rates, and variability',
  constant !== null
  && constant.sampleCount === 3 && constant.startTimestampMs === 1_000
  && constant.endTimestampMs === 2_000 && constant.elapsedMs === 1_000
  && constant.centerNetDisplacement === 0 && constant.centerPathLength === 0
  && constant.yawChangeDeg === 0 && constant.pitchChangeDeg === 0 && constant.rollChangeDeg === 0
  && constant.centerRatePerSecond === 0 && constant.yawRateDegPerSecond === 0
  && constant.centerStepStdDev === 0 && constant.yawStepStdDevDeg === 0);
const position = summarizeFacialMotion([
  motionSample(0, 0.1, 0.2), motionSample(500, 0.4, 0.6), motionSample(1_000, 0.5, 0.6),
]);
check('position change reports net/path displacement, coarse rate and step variability',
  position !== null
  && Math.abs(position.centerNetDisplacement - Math.hypot(0.4, 0.4)) < 1e-10
  && Math.abs(position.centerPathLength - (Math.hypot(0.3, 0.4) + 0.1)) < 1e-10
  && Math.abs(position.centerRatePerSecond - position.centerPathLength) < 1e-10
  && position.centerStepStdDev > 0);
const orientation = summarizeFacialMotion([
  motionSample(0, 0.5, 0.5, 10, -5, 20),
  motionSample(1_000, 0.5, 0.5, 25, 5, 35),
]);
check('orientation changes and absolute angular paths are reported per axis',
  orientation !== null
  && orientation.yawChangeDeg === 15 && orientation.pitchChangeDeg === 10
  && orientation.rollChangeDeg === 15 && orientation.yawPathDeg === 15
  && orientation.pitchPathDeg === 10 && orientation.rollPathDeg === 15
  && orientation.yawRateDegPerSecond === 15);
const wraparound = summarizeFacialMotion([
  motionSample(0, 0.5, 0.5, 179, 0, -179),
  motionSample(500, 0.5, 0.5, -179, 0, 179),
]);
check('angular deltas use shortest signed path across ±180 degrees',
  wraparound !== null && wraparound.yawChangeDeg === 2 && wraparound.rollChangeDeg === -2
  && wraparound.yawPathDeg === 2 && wraparound.rollPathDeg === 2);
const irregular = summarizeFacialMotion([
  motionSample(1_000, 0.2), motionSample(1_750, 0.5),
]);
check('irregular timing preserves exact timestamps and uses actual elapsed time for rates',
  irregular !== null && irregular.startTimestampMs === 1_000
  && irregular.endTimestampMs === 1_750 && irregular.elapsedMs === 750
  && Math.abs(irregular.centerRatePerSecond - 0.4) < 1e-10);
const incomplete = summarizeFacialMotion([motionSample(3_000), motionSample(3_500, 0.6)]);
check('incomplete startup window is summarized with its actual sample count and duration',
  incomplete !== null && incomplete.sampleCount === 2
  && incomplete.startTimestampMs === 3_000 && incomplete.elapsedMs === 500);
check('a single sample returns no summary instead of implying zero movement',
  summarizeFacialMotion([motionSample(1_000)]) === null);
const afterLongGap = summarizeFacialMotion([
  motionSample(0, 0.1), motionSample(500, 0.2),
  motionSample(500 + FACIAL_MAX_SAMPLE_GAP_MS + 1, 0.9),
]);
check('large timestamp gap is not bridged; latest one-sample run has no motion summary',
  afterLongGap === null);
const afterInvalid = summarizeFacialMotion([
  motionSample(0, 0.1), { ...motionSample(500, 0.2), yawDeg: Number.NaN },
  motionSample(1_000, 0.9), motionSample(1_500, 0.8),
]);
check('invalid sample splits runs; summary uses only the latest valid contiguous run',
  afterInvalid !== null && afterInvalid.sampleCount === 2
  && afterInvalid.startTimestampMs === 1_000
  && Math.abs(afterInvalid.centerPathLength - 0.1) < 1e-10);
check('summary is plain numeric data with no labels or raw sample arrays',
  constant !== null
  && Object.values(constant).every((value) => typeof value === 'number' && Number.isFinite(value))
  && !Object.values(constant).some((value) => Array.isArray(value) || typeof value === 'string'));

console.log('\n4. Camera/task integration stays local and isolated');
check('FaceLandmarker is lazily imported and configured for VIDEO geometry only',
  code.includes("await import('@mediapipe/tasks-vision')")
  && code.includes('vision.FaceLandmarker.createFromOptions')
  && code.includes("runningMode: 'VIDEO'")
  && code.includes('outputFacialTransformationMatrixes: true')
  && code.includes('outputFaceBlendshapes: false'));
check('the existing preview video element is passed to FaceLandmarker',
  /const timestampMs = performance\.now\(\);[\s\S]{0,120}landmarker\.detectForVideo\(video, timestampMs\)/.test(code)
  && /const video = cameraVideoRef\.current;/.test(code));
check('one existing camera track and no second permission request',
  (code.match(/createLocalVideoTrack\s*\(/g) || []).length === 1
  && !/getUserMedia\s*\(/.test(code));
check('FaceLandmarker startup follows the existing camera track opening',
  code.includes('startFaceLandmarkerSampling();')
  && code.includes('startFaceSampling();'));
check('initialization and inference failures clear only Stage 6 samples',
  code.includes('facialSamplesRef.current.clear();')
  && code.includes('facialMotionSummaryRef.current = null;')
  && code.includes('if (sample) {')
  && code.includes('facialSamplesRef.current.add(sample);')
  && code.includes('facialSamplesRef.current.clear();'));
check('camera cleanup cancels the Stage 6 timer, closes task, and clears its buffer',
  code.includes('stopFaceLandmarkerSampling();')
  && code.includes('window.clearTimeout(faceLandmarkerTimerRef.current)')
  && code.includes('landmarker.close();')
  && code.includes('facialSamplesRef.current.clear();'));
check('Stage 6 has no data publishing, network request, or measurement logging',
  !/publishData\s*\(|fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon/.test(code)
  && !/console\.(?:log|info|warn|error)\([^)]*(?:landmark|yaw|pitch|roll|sample)/i.test(code));
check('temporal summary is calculated only from the existing bounded sample buffer',
  code.includes('summarizeFacialMotion(facialSamplesRef.current.values())')
  && code.includes('faceLandmarkerTimerRef.current = window.setTimeout(')
  && !/setInterval|requestAnimationFrame/.test(code.slice(code.indexOf('const sampleFaceGeometry'), code.indexOf('const startFaceLandmarkerSampling'))));
check('summary has no send, report, persistence, or log path',
  !/facialMotionSummaryRef\.current[\s\S]{0,100}(fetch|publishData|ImageContent|record_audit|db\.|console\.)/.test(code));
check('Face Landmarker does not change Stage 2 detector/proctoring helpers',
  code.includes('detector.detectForVideo(video, performance.now())')
  && code.includes('updateProctorState(proctorTimersRef.current, count, Date.now())')
  && !/FaceLandmarker|faceLandmarker/.test(stripComments(read('frontend/src/pages/applicant/aiInterviewRules.ts'))));
check('Stage 5 worker and transport files are not part of the frontend task path',
  read('app/ai/interview/worker.py').includes('video_input=False')
  && read('app/ai/interview/agent.py').includes('ImageContent(image=frame'));

console.log(`\n  ${failed === 0 ? 'All Stage 6 Face Landmarker checks passed.' : `${failed} Face Landmarker check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
