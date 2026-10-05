/** Stage 4A camera-track publishing checks (no browser, LiveKit room or quota). */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = new URL('../../', import.meta.url);
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, root)), 'utf8');
const page = read('frontend/src/pages/applicant/AiInterviewPage.tsx');
const code = page.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const svc = read('app/services/ai_interview_service.py');
const worker = read('app/ai/interview/worker.py');
const rules = read('frontend/src/pages/applicant/aiInterviewRules.ts');
const dictionary = read('frontend/src/i18n/dictionaries/aiInterview.ts');

let failed = 0;
const check = (name: string, ok: boolean) => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
};

console.log('Stage 4A: camera track → connected applicant LiveKit room');
check('token permits camera publishing', /can_publish_sources\s*=\s*PUBLISH_SOURCES/.test(svc)
  && /PUBLISH_SOURCES\s*=\s*\["microphone",\s*"camera"\]/.test(svc)
  && /can_publish\s*=\s*True/.test(svc));
check('token still forbids data publishing', /can_publish_data\s*=\s*False/.test(svc));
check('one existing createLocalVideoTrack call', (code.match(/createLocalVideoTrack\s*\(/g) || []).length === 1);
check('existing cameraTrackRef is the published track', /publishCameraTrack\(room,\s*cameraTrackRef\.current\)/.test(code)
  && /publishTrack\(track,\s*\{\s*name:\s*CAMERA_TRACK_NAME\s*\}\)/.test(code));
check('publication uses stable camera name', /CAMERA_TRACK_NAME\s*=\s*'ai-interview-camera'/.test(code));
check('publish is called after successful room.connect', code.indexOf('await room.connect(') >= 0
  && code.indexOf('await room.connect(') < code.indexOf('publishCameraTrack(room, cameraTrackRef.current)'));
check('publish helper refuses a non-connected room', /room\.state\s*!==\s*ConnectionState\.Connected/.test(code));
check('duplicate track and in-flight publishing are guarded', code.includes('getTrackPublication(Track.Source.Camera)')
  && code.includes('existing?.track === track') && code.includes('cameraPublishingRef.current'));
check('a later session reopens through the same camera path without overlapping an old open',
  code.includes('if (!cameraTrackRef.current) await startCamera()')
  && code.includes('if (openingCamera) await openingCamera')
  && code.includes('cameraOpeningRef.current === opening'));
check('cleanup unpublishes then detaches/stops and clears the ref', code.includes('unpublishTrack(track, false)')
  && code.includes('cameraTrackRef.current = null') && code.includes('track.detach()') && code.includes('track.stop()'));
check('camera publish is not awaited by microphone startup', /void publishCameraTrack\(room,\s*cameraTrackRef\.current\)/.test(code)
  && code.indexOf('publishCameraTrack(room, cameraTrackRef.current)') < code.indexOf('setMicrophoneEnabled(true)'));
check('no extra getUserMedia or camera capture loop', !/getUserMedia\s*\(/.test(code)
  && code.includes('FACE_SAMPLE_INTERVAL_MS') && !/setInterval\([^\n]*sampleFaces/.test(code));
check('FaceDetector remains and samples the existing preview video', code.includes('FaceDetector.createFromOptions')
  && code.includes('detectForVideo(video, performance.now())') && code.includes('updateProctorState(proctorTimersRef.current, count, Date.now())'));
check('Stage 4 face metadata contract remains intact', rules.includes("CAMERA_PROCTORING_TOPIC = 'smarthr.camera.proctoring'")
  && rules.includes("CAMERA_PROCTORING_TYPE = 'camera_proctoring'")
  && rules.includes("'type', 'timestamp', 'face_count', 'flag'"));
check('no publishData call or video-frame/image upload path', !/publishData\s*\(/.test(code)
  && !/createElement\(['"]canvas['"]\)|drawImage|toDataURL|toBlob|getImageData|ImageCapture|captureStream/i.test(code));
check('camera diagnostics contain no PII or credential fields', !/candidate|email|phone|token|secret|api.?key|transcript/i.test(
  code.slice(code.indexOf('const traceCameraPublish'), code.indexOf('const traceSession'))));
check('privacy notice says LiveKit transmission in English and Arabic',
  /Camera video is used during your AI interview and transmitted through the LiveKit interview session/.test(dictionary)
  && /يُستخدم فيديو الكاميرا أثناء مقابلتك الذكية ويُنقل عبر جلسة المقابلة في LiveKit/.test(dictionary));
check('worker video input remains disabled', /video_input\s*=\s*False/.test(worker));

console.log(`\n${failed === 0 ? 'All Stage 4A checks passed.' : `${failed} Stage 4A check(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
