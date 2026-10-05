/** Offline face-presence checks; no camera, LiveKit, network, or model. */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  FACE_PRESENCE_MAX_CENTER,
  FACE_PRESENCE_MIN_CENTER,
  FACE_PRESENCE_MULTIPLE_FACES_SUSTAINED_MS,
  FACE_PRESENCE_NO_FACE_SUSTAINED_MS,
  FACE_PRESENCE_OUT_OF_FRAME_SUSTAINED_MS,
  SpeechFacePresenceEpisode,
  classifyFacePresence,
} from '../src/pages/applicant/facialBehavior';

const root = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, root)), 'utf8');
const page = read('frontend/src/pages/applicant/AiInterviewPage.tsx');
const pageCode = page.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const behavior = read('frontend/src/pages/applicant/facialBehavior.ts');
const rules = read('frontend/src/pages/applicant/aiInterviewRules.ts');

let failed = 0;
let passed = 0;
const check = (name: string, ok: boolean) => {
  if (!ok) failed += 1;
  else passed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
};

const face = (centerX = 0.5, centerY = 0.5) => ({
  faceLandmarks: [[
    { x: centerX - 0.1, y: centerY - 0.1 },
    { x: centerX + 0.1, y: centerY + 0.1 },
  ]],
});
const noFace = { faceLandmarks: [] };
const multipleFaces = { faceLandmarks: [face().faceLandmarks[0], face().faceLandmarks[0]] };
const sample = (episode: SpeechFacePresenceEpisode, t: number, result: unknown) =>
  episode.addObservation(t, result);
const finish = (episode: SpeechFacePresenceEpisode, endMs: number) => episode.endSpeech(endMs);

console.log('1. Presence classification and broad frame boundary');
check('one valid face inside the frame -> face_present',
  classifyFacePresence(face()) === 'face_present');
check('no face landmarks -> no_face',
  classifyFacePresence(noFace) === 'no_face');
check('more than one face -> multiple_faces',
  classifyFacePresence(multipleFaces) === 'multiple_faces');
check('one face with unusable center coordinates -> face_position_unavailable',
  classifyFacePresence({ faceLandmarks: [[{ x: Number.NaN, y: 0.5 }]] }) === 'face_position_unavailable');
check('one face outside the X boundary -> out_of_frame',
  classifyFacePresence(face(0.05, 0.5)) === 'out_of_frame');
check('one face outside the Y boundary -> out_of_frame',
  classifyFacePresence(face(0.5, 0.95)) === 'out_of_frame');
check('both inclusive 0.10 and 0.90 center boundaries are accepted',
  classifyFacePresence(face(0.1, 0.9)) === 'face_present'
  && FACE_PRESENCE_MIN_CENTER === 0.1 && FACE_PRESENCE_MAX_CENTER === 0.9);
check('values just outside either boundary -> out_of_frame',
  classifyFacePresence(face(0.099, 0.5)) === 'out_of_frame'
  && classifyFacePresence(face(0.5, 0.901)) === 'out_of_frame');
check('missing/malformed observation -> unavailable, never no_face',
  classifyFacePresence(null) === 'unavailable'
  && classifyFacePresence({}) === 'unavailable'
  && classifyFacePresence({ faceLandmarks: null }) === 'unavailable');

console.log('\n2. Speech-scoped sample counts and ratio');
const interval = new SpeechFacePresenceEpisode();
interval.startSpeech(100);
check('samples before speech start are not counted',
  sample(interval, 50, face()) === 'face_present');
sample(interval, 500, face());
sample(interval, 1_000, noFace);
sample(interval, 1_500, multipleFaces);
sample(interval, 2_000, face(0.05, 0.5));
sample(interval, 2_500, { faceLandmarks: [[{ x: Number.NaN, y: 0.5 }]] });
sample(interval, 3_000, null);
const intervalSummary = finish(interval, 3_500);
check('face, no-face, multiple, out-of-frame and invalid-position counts are distinct',
  intervalSummary?.validFaceSampleCountDuringSpeech === 5
  && intervalSummary.facePresentSampleCountDuringSpeech === 1
  && intervalSummary.noFaceSampleCountDuringSpeech === 1
  && intervalSummary.multipleFaceSampleCountDuringSpeech === 1
  && intervalSummary.outOfFrameSampleCountDuringSpeech === 1
  && intervalSummary.facePositionUnavailableSampleCountDuringSpeech === 1
  && intervalSummary.unavailableSampleCountDuringSpeech === 1);
check('ratio denominator excludes unavailable and non-classifiable position samples',
  intervalSummary?.facePresenceSampleRatioDuringSpeech === 1 / 4);
check('summary carries actual speech interval duration',
  intervalSummary?.speechActiveDurationMs === 3_400);

const startsBetween = new SpeechFacePresenceEpisode();
startsBetween.addObservation(500, noFace);
startsBetween.startSpeech(750);
startsBetween.addObservation(1_000, face());
startsBetween.addObservation(1_500, noFace);
const betweenSummary = finish(startsBetween, 1_750);
check('speech starting between face samples excludes pre-speech observations',
  betweenSummary?.validFaceSampleCountDuringSpeech === 2
  && betweenSummary.facePresentSampleCountDuringSpeech === 1
  && betweenSummary.noFaceSampleCountDuringSpeech === 1);

const endsBetween = new SpeechFacePresenceEpisode();
endsBetween.startSpeech(0);
endsBetween.addObservation(500, face());
endsBetween.addObservation(1_000, noFace);
const beforeEnd = finish(endsBetween, 1_250);
endsBetween.addObservation(1_500, face());
check('speech ending between face samples excludes later observations',
  beforeEnd?.validFaceSampleCountDuringSpeech === 2
  && beforeEnd.speechActiveDurationMs === 1_250);

const allUnavailable = new SpeechFacePresenceEpisode();
allUnavailable.startSpeech(0);
allUnavailable.addObservation(500, null);
allUnavailable.addObservation(1_000, {});
const unavailableSummary = finish(allUnavailable, 1_500);
check('zero classifiable observations produces a null ratio',
  unavailableSummary?.validFaceSampleCountDuringSpeech === 0
  && unavailableSummary.facePresenceSampleRatioDuringSpeech === null
  && unavailableSummary.noFaceSampleCountDuringSpeech === 0);

console.log('\n3. Sustained conditions require consecutive classified samples');
const runCondition = (
  observation: unknown,
  durationMs: number,
  interruptions: Array<{ at: number; result: unknown }> = [],
) => {
  const episode = new SpeechFacePresenceEpisode();
  episode.startSpeech(0);
  const points = new Map(interruptions.map((entry) => [entry.at, entry.result]));
  for (let t = 0; t <= durationMs; t += 500) {
    sample(episode, t, points.has(t) ? points.get(t) : observation);
  }
  return finish(episode, durationMs + 500);
};
const sustainedNoFace = runCondition(noFace, FACE_PRESENCE_NO_FACE_SUSTAINED_MS);
check('no-face threshold is recorded after 10 seconds of consecutive samples',
  sustainedNoFace?.sustainedNoFaceEpisodeCount === 1
  && FACE_PRESENCE_NO_FACE_SUSTAINED_MS === 10_000);
const sustainedMultiple = runCondition(multipleFaces, FACE_PRESENCE_MULTIPLE_FACES_SUSTAINED_MS);
check('multiple-face threshold is recorded after 5 seconds of consecutive samples',
  sustainedMultiple?.sustainedMultipleFacesEpisodeCount === 1
  && FACE_PRESENCE_MULTIPLE_FACES_SUSTAINED_MS === 5_000);
const sustainedOut = runCondition(face(0.95, 0.5), FACE_PRESENCE_OUT_OF_FRAME_SUSTAINED_MS);
check('out-of-frame threshold is recorded after 10 seconds of consecutive samples',
  sustainedOut?.sustainedOutOfFrameEpisodeCount === 1
  && FACE_PRESENCE_OUT_OF_FRAME_SUSTAINED_MS === 10_000);
const resetByPresent = runCondition(noFace, 12_000, [
  { at: 5_000, result: face() },
]);
check('face_present resets the current sustained no-face run',
  resetByPresent?.sustainedNoFaceEpisodeCount === 0);
const brokenByUnavailable = runCondition(noFace, 12_000, [
  { at: 5_000, result: null },
]);
check('unavailable breaks sustained continuity and does not count as absence',
  brokenByUnavailable?.sustainedNoFaceEpisodeCount === 0
  && brokenByUnavailable.unavailableSampleCountDuringSpeech === 1
  && brokenByUnavailable.noFaceSampleCountDuringSpeech === 24);
const gap = new SpeechFacePresenceEpisode();
gap.startSpeech(0);
for (let t = 0; t < 5_000; t += 500) gap.addObservation(t, noFace);
gap.addObservation(6_501, noFace);
for (let t = 7_001; t <= 11_001; t += 500) gap.addObservation(t, noFace);
const gapSummary = gap.endSpeech(11_501);
check('excessive observation gaps break sustained continuity',
  gapSummary?.sustainedNoFaceEpisodeCount === 0);

console.log('\n4. Long episodes and reset remain bounded');
const long = new SpeechFacePresenceEpisode();
long.startSpeech(0);
for (let t = 500; t <= 500_000; t += 500) {
  long.addObservation(t, t % 1_000 === 0 ? face() : noFace);
}
const longSummary = finish(long, 500_500);
check('long speech retains no per-sample history (O(1) accumulator state)',
  longSummary?.validFaceSampleCountDuringSpeech === 1_000
  && Object.values(long).every((value) => value === null || typeof value === 'number'
    || typeof value === 'boolean')
  && !Object.values(long).some(Array.isArray));
check('reset clears speech boundaries, counts and sustained state',
  long.endSpeech(501_000) === null
  && Object.values(long).every((value) => value === null || value === 0 || value === false));

console.log('\n5. Integration, lifecycle, and privacy');
check('existing sample callback feeds presence independently from mouth-motion',
  pageCode.includes('speechFacePresenceEpisodeRef.current.addObservation(timestampMs, result)')
  && pageCode.includes('speechMouthEpisodeRef.current.addFaceSample(timestampMs, mouthApertureFromResult(result))')
  && pageCode.includes('FACE_LANDMARKER_SAMPLE_INTERVAL_MS'));
check('speech boundaries use IsSpeakingChanged and performance.now()',
  pageCode.includes('ParticipantEvent.IsSpeakingChanged')
  && /const timestampMs = performance\.now\(\);[\s\S]{0,400}speechFacePresenceEpisodeRef\.current\.startSpeech\(timestampMs\)/.test(pageCode)
  && pageCode.includes('speechFacePresenceEpisodeRef.current.endSpeech(timestampMs)'));
check('start, completion, camera cleanup, interview cleanup and failed-start cleanup reset state',
  (pageCode.match(/speechFacePresenceEpisodeRef\.current\.reset\(\)/g) || []).length >= 4
  && pageCode.includes('speechFacePresenceSummaryRef.current = null;')
  && pageCode.includes('await stopCamera();')
  && pageCode.includes('cleanup();'));
check('presence result is assigned only to a local ref and is not rendered or sent',
  pageCode.split('\n').filter((line) => line.includes('speechFacePresenceSummaryRef.current'))
    .every((line) => /^\s*speechFacePresenceSummaryRef\.current\s*=/.test(line))
  && !/speechFacePresenceSummaryRef\.current[^;\n]*(?:SmartHRApi|fetch|publishData|console\.|JSON\.stringify)/.test(pageCode)
  && !/speechFacePresence|facePresenceSampleRatio|outOfFrameSampleCount/.test(
    pageCode.slice(pageCode.lastIndexOf('\n  return ('), pageCode.length),
  ));
check('feature helpers contain no LiveKit send, API/database persistence, GPT, report or logging path',
  !/\b(?:publishData|fetch|sendBeacon|XMLHttpRequest|WebSocket|SmartHRApi|ImageContent|logger\.|console\.|SessionLocal|record_audit|db\.)\b/.test(behavior));
check('Face presence never enters Stage 3 rules or camera proctoring payload contract',
  !/classifyFacePresence|SpeechFacePresence|facePresenceSampleRatio/.test(rules));
check('no face/frame/landmark arrays are stored in the speech presence accumulator',
  !/private\s+\w+\s*:\s*(?:unknown|Array|FaceLandmark|Point3)\s*\[?\s*[;=]/.test(
    behavior.slice(behavior.indexOf('export class SpeechFacePresenceEpisode'),
      behavior.indexOf('/** Scalar-only, episode-scoped mouth-motion')),
  ));

console.log(`\n  ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
