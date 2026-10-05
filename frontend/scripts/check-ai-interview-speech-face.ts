/** Offline speech/mouth-motion checks; no camera, LiveKit, or model. */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  FACIAL_MAX_SAMPLE_GAP_MS,
  MOUTH_MOTION_ENTER_DEADBAND,
  MOUTH_MOTION_EXIT_DEADBAND,
  mouthApertureFromResult,
  SpeechMouthEpisode,
} from '../src/pages/applicant/facialBehavior';

const root = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, root)), 'utf8');
const page = read('frontend/src/pages/applicant/AiInterviewPage.tsx');
const pageCode = page.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const behavior = read('frontend/src/pages/applicant/facialBehavior.ts');

let failed = 0;
const check = (name: string, ok: boolean) => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
};

const landmarks = () => Array.from({ length: 468 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
const faceResult = (upperY = 0.4, lowerY = 0.5, leftX = 0.3, rightX = 0.7) => {
  const face = landmarks();
  face[13] = { x: 0.5, y: upperY, z: 0 };
  face[14] = { x: 0.5, y: lowerY, z: 0 };
  face[61] = { x: leftX, y: 0.5, z: 0 };
  face[291] = { x: rightX, y: 0.5, z: 0 };
  return { faceLandmarks: [face] };
};

console.log('1. Coarse normalized mouth aperture');
const aperture = mouthApertureFromResult(faceResult());
check('one usable face produces only a numeric normalized aperture',
  aperture !== null && Math.abs(aperture - 0.25) < 1e-12 && typeof aperture === 'number');
check('normalization uses vertical lip separation divided by mouth width',
  Math.abs((mouthApertureFromResult(faceResult(0.4, 0.6, 0.2, 0.8)) ?? 0) - 1 / 3) < 1e-12);
check('multiple faces and missing required landmark indices are unavailable',
  mouthApertureFromResult({ faceLandmarks: [landmarks(), landmarks()] }) === null
  && mouthApertureFromResult({ faceLandmarks: [landmarks().slice(0, 291)] }) === null);
const invalidPoint = landmarks();
invalidPoint[14] = { x: Number.NaN, y: 0.5, z: 0 };
check('invalid required landmark coordinates and degenerate mouth width are unavailable',
  mouthApertureFromResult({ faceLandmarks: [invalidPoint] }) === null
  && mouthApertureFromResult(faceResult(0.4, 0.5, 0.5, 0.5)) === null
  && mouthApertureFromResult(null) === null);

console.log('\n2. Episode-local sampled mouth movement');
const constant = new SpeechMouthEpisode();
constant.startSpeech(0);
constant.addFaceSample(500, 0.1);
constant.addFaceSample(1_000, 0.1);
const constantSummary = constant.endSpeech(1_500);
check('same aperture produces no observed mouth-motion samples',
  constantSummary?.validFaceSampleCountDuringSpeech === 2
  && constantSummary.mouthMotionSampleCountDuringSpeech === 0
  && constantSummary.mouthMotionSampleRatioDuringSpeech === 0);

const noise = new SpeechMouthEpisode();
noise.startSpeech(0);
noise.addFaceSample(500, 0.1);
noise.addFaceSample(1_000, 0.1 + MOUTH_MOTION_ENTER_DEADBAND / 2);
noise.addFaceSample(1_500, 0.1 + MOUTH_MOTION_ENTER_DEADBAND / 2 + MOUTH_MOTION_EXIT_DEADBAND / 4);
check('small aperture noise stays below the movement deadband',
  noise.endSpeech(2_000)?.mouthMotionSampleCountDuringSpeech === 0);

const hysteresis = new SpeechMouthEpisode();
hysteresis.startSpeech(0);
hysteresis.addFaceSample(500, 0.1);
hysteresis.addFaceSample(1_000, 0.16);
hysteresis.addFaceSample(1_500, 0.19);
hysteresis.addFaceSample(2_000, 0.2);
hysteresis.addFaceSample(2_500, 0.1);
const hysteresisSummary = hysteresis.endSpeech(3_000);
check('meaningful change enters motion and the lower exit threshold avoids toggling',
  hysteresisSummary?.mouthMotionSampleCountDuringSpeech === 3
  && MOUTH_MOTION_ENTER_DEADBAND > MOUTH_MOTION_EXIT_DEADBAND);

console.log('\n3. Invalid samples and timing gaps break continuity');
const unordered = new SpeechMouthEpisode();
unordered.startSpeech(0);
unordered.addFaceSample(500, 0.1);
unordered.addFaceSample(500, 0.2);
unordered.addFaceSample(1_000, 0.2);
unordered.addFaceSample(1_500, 0.3);
check('non-increasing timestamps reset continuity and are not counted',
  unordered.endSpeech(2_000)?.mouthMotionSampleCountDuringSpeech === 1);

const gap = new SpeechMouthEpisode();
gap.startSpeech(0);
gap.addFaceSample(500, 0.1);
gap.addFaceSample(500 + FACIAL_MAX_SAMPLE_GAP_MS + 1, 0.3);
const gapSummary = gap.endSpeech(2_200);
check('an excessive face-sample gap seeds a new run without bridging movement',
  gapSummary?.mouthMotionSampleCountDuringSpeech === 0
  && gapSummary.validFaceSampleCountDuringSpeech === 2);

const missing = new SpeechMouthEpisode();
missing.startSpeech(0);
missing.addFaceSample(500, 0.1);
missing.addFaceSample(1_000, null);
missing.addFaceSample(1_500, 0.3);
missing.addFaceSample(2_000, 0.36);
const missingSummary = missing.endSpeech(2_500);
check('invalid face samples reset continuity and movement is counted only after a new baseline',
  missingSummary?.validFaceSampleCountDuringSpeech === 3
  && missingSummary.mouthMotionSampleCountDuringSpeech === 1);

console.log('\n4. Speech-boundary correlation uses only in-episode face samples');
const startsBeforeSample = new SpeechMouthEpisode();
startsBeforeSample.startSpeech(100);
startsBeforeSample.addFaceSample(500, 0.1);
startsBeforeSample.addFaceSample(1_000, 0.16);
check('speech starting before the first face sample uses it as the baseline',
  startsBeforeSample.endSpeech(1_500)?.mouthMotionSampleCountDuringSpeech === 1);

const startsBetweenSamples = new SpeechMouthEpisode();
startsBetweenSamples.addFaceSample(500, 0.1);
startsBetweenSamples.startSpeech(750);
startsBetweenSamples.addFaceSample(1_000, 0.16);
startsBetweenSamples.addFaceSample(1_500, 0.22);
check('speech starting between samples does not attribute a pre-speech transition',
  startsBetweenSamples.endSpeech(1_750)?.mouthMotionSampleCountDuringSpeech === 1);

const endsBetweenSamples = new SpeechMouthEpisode();
endsBetweenSamples.startSpeech(0);
endsBetweenSamples.addFaceSample(500, 0.1);
endsBetweenSamples.addFaceSample(1_000, 0.16);
const ended = endsBetweenSamples.endSpeech(1_250);
endsBetweenSamples.addFaceSample(1_500, 0.3);
check('speech ending between samples excludes later samples',
  ended?.speechActiveDurationMs === 1_250
  && ended.validFaceSampleCountDuringSpeech === 2
  && ended.mouthMotionSampleCountDuringSpeech === 1);

const noFace = new SpeechMouthEpisode();
noFace.startSpeech(0);
const unavailable = noFace.endSpeech(1_000);
check('no face during speech reports unavailable movement, not zero movement',
  unavailable?.validFaceSampleCountDuringSpeech === 0
  && unavailable.mouthMotionSampleCountDuringSpeech === null
  && unavailable.mouthMotionSampleRatioDuringSpeech === null);

console.log('\n5. Numeric sample ratio and bounded long episodes');
const ratio = new SpeechMouthEpisode();
ratio.startSpeech(0);
[
  0.1, 0.16, 0.19, 0.2, 0.1, 0.13, 0.14, 0.08, 0.11, 0.12,
].forEach((value, index) => ratio.addFaceSample((index + 1) * 500, value));
const ratioSummary = ratio.endSpeech(6_000);
check('ratio is movement-active samples divided by valid speech-period face samples',
  ratioSummary?.validFaceSampleCountDuringSpeech === 10
  && ratioSummary.mouthMotionSampleCountDuringSpeech === 6
  && ratioSummary.mouthMotionSampleRatioDuringSpeech === 0.6);

const longEpisode = new SpeechMouthEpisode();
longEpisode.startSpeech(0);
for (let index = 1; index <= 1_000; index += 1) {
  longEpisode.addFaceSample(index * 500, index % 2 === 0 ? 0.1 : 0.16);
}
const longSummary = longEpisode.endSpeech(501_000);
check('an episode longer than five seconds retains only fixed scalar state',
  longSummary?.validFaceSampleCountDuringSpeech === 1_000
  && Object.values(longEpisode).every((value) =>
    value === null || typeof value === 'number' || typeof value === 'boolean')
  && !Object.values(longEpisode).some(Array.isArray));
check('episode output contains only bounded numeric summary fields',
  longSummary !== null
  && Object.values(longSummary).every((value) => value === null
    || (typeof value === 'number' && Number.isFinite(value))));

const reset = new SpeechMouthEpisode();
reset.startSpeech(0);
reset.addFaceSample(500, 0.1);
reset.reset();
check('cleanup reset drops the active episode and its counters',
  reset.endSpeech(1_000) === null
  && Object.values(reset).every((value) => value === null || value === 0 || value === false));
reset.startSpeech(2_000);
reset.addFaceSample(2_500, 0.1);
const afterReset = reset.endSpeech(3_000);
check('a later episode starts with fresh counters',
  afterReset?.validFaceSampleCountDuringSpeech === 1
  && afterReset.mouthMotionSampleCountDuringSpeech === 0);

console.log('\n6. Existing pipeline integration and privacy boundaries');
const samplingStart = pageCode.indexOf('const sampleFaceGeometry');
const samplingEnd = pageCode.indexOf('const startFaceLandmarkerSampling', samplingStart);
const sampling = pageCode.slice(samplingStart, samplingEnd);
check('mouth extraction uses the existing FaceLandmarker result and 2 Hz callback',
  sampling.includes('mouthApertureFromResult(result)')
  && sampling.includes('speechMouthEpisodeRef.current.addFaceSample(timestampMs')
  && pageCode.includes('FACE_LANDMARKER_SAMPLE_INTERVAL_MS'));
check('speech boundaries use the existing local speaking event and performance clock',
  pageCode.includes('room.localParticipant.on(ParticipantEvent.IsSpeakingChanged')
  && /const timestampMs = performance\.now\(\);[\s\S]{0,180}startSpeech\(timestampMs\)/.test(pageCode)
  && pageCode.includes('endSpeech(timestampMs)'));
check('episode and scalar summary reset on start, completion, cleanup, and camera cleanup',
  pageCode.includes('speechMouthEpisodeRef.current.reset();')
  && pageCode.includes('speechMouthSummaryRef.current = null;')
  && pageCode.includes('stopFaceLandmarkerSampling();'));
check('speech summary is only assigned locally and is not consumed by UI or a transport',
  pageCode.split('\n').filter((line) => line.includes('speechMouthSummaryRef.current'))
    .every((line) => /^\s*speechMouthSummaryRef\.current\s*=/.test(line))
  && !/speechMouthSummaryRef\.current[^;\n]*(?:SmartHRApi|fetch|publishData|console\.|JSON\.stringify)/.test(pageCode));
check('mouth helper and accumulator contain no network, LiveKit, database, report, or logging calls',
  !/\b(?:fetch|publishData|sendBeacon|XMLHttpRequest|WebSocket|console\.|logger\.|db\.|SessionLocal|ImageContent)\b/.test(behavior));
check('mouth measurement is not included in a published data payload or applicant UI',
  !/mouthAperture|mouthMotionSample|speechActiveDuration|mouthMotionSampleRatio/.test(
    pageCode.slice(pageCode.lastIndexOf('\n  return ('), pageCode.length),
  ));

console.log(`\n  ${failed === 0 ? 'All speech/mouth-motion checks passed.' : `${failed} speech/mouth-motion check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
