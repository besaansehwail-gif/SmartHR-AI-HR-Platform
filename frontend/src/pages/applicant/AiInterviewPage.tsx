import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Briefcase,
  Calendar,
  CheckCircle2,
  Info,
  Loader2,
  Mic,
  PhoneOff,
  MicOff,
  Radio,
  RefreshCw,
  Send,
  Video,
  VideoOff,
  Volume2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import {
  ConnectionState,
  DisconnectReason,
  LocalTrackPublication,
  LocalVideoTrack,
  Participant,
  ParticipantEvent,
  RemoteParticipant,
  RemoteTrack,
  Room,
  RoomEvent,
  Track,
  TextStreamReader,
  createLocalVideoTrack,
} from 'livekit-client';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { PageHeader } from '../../components/ui/PageHeader';
import { InfoPanel, Spinner } from '../../components/ui/States';
import { PageId } from '../../components/layout/Sidebar';
import { ApiError, SmartHRApi } from '../../services/api';
import { AiInterviewListing, AiInterviewStatus } from '../../types';
import { formatDateTime, useT } from '../../i18n';
import {
  AGENT_STATES,
  AgentState,
  CAMERA_PROCTORING_TYPE,
  Connection,
  FACE_SAMPLE_INTERVAL_MS,
  FaceCount,
  ProctorFlag,
  ProctorState,
  ProctorTimers,
  faceCountOf,
  formatFaceLog,
  formatProctorFlagLog,
  initialProctorTimers,
  isProctorFlag,
  updateProctorState,
  INTERVIEW_STATES,
  InterviewState,
  MicStatus,
  Phase,
  ViewState,
  connectionOf,
  micFailureOf,
  startErrorKey,
  startRetryAllowed,
  startWindow,
  turnOf,
  viewStateOf,
} from './aiInterviewRules';
import {
  FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
  FacialMotionSummary,
  FacialSampleBuffer,
  geometrySampleFromResult,
  mouthApertureFromResult,
  SpeechMouthEpisode,
  SpeechMouthEpisodeSummary,
  SpeechFacePresenceEpisode,
  SpeechFacePresenceSummary,
  summarizeFacialMotion,
} from './facialBehavior';

/**
 * AI Interview - a real-time spoken interview for one of the applicant's jobs.
 *
 *   Load  -> GET /ai-interview/interviews the applicant's own scheduled
 *                                         interviews: id, job title, time
 *   Start -> POST /ai-interview/session   {interview_id} only. SmartHR checks the
 *                                         interview is theirs, resolves its job
 *                                         and returns a short-lived LiveKit
 *                                         token for one room
 *         -> room.connect()               LiveKit Cloud
 *         -> microphone and camera published to the room
 *         -> the interviewer agent joins  LiveKit dispatches it from the token
 *         -> its audio track is attached  the applicant hears it
 *
 * The page never sees a LiveKit secret. It publishes the existing camera track
 * after connecting, and never sends a job id - the title shown is the one the
 * backend resolved.
 *
 * Camera (Stage 1): `createLocalVideoTrack()` opens one track used for local
 * preview, FaceDetector and LiveKit publication. Video is transmitted through
 * the LiveKit interview session.
 * Camera failures have their own status and never touch the microphone, and it is
 * stopped on cleanup, on a failed start, at the end of the interview and when
 * the page unmounts.
 *
 * Camera (Stage 2): a LOCAL face count (0 / 1 / 2+) on top of the same preview.
 * MediaPipe Face Detector runs on-device against the preview <video> element
 * about once every 1.5s (never every frame); only the count is shown and
 * logged as `{ timestamp, face_count }`. Detection never captures or sends
 * frames as metadata; `publishData()` is never called,
 * and the detector/timer are stopped with the camera. A detector failure shows
 * its own message and never touches the microphone/audio paths.
 *
 * Camera (Stage 6): a separate local Face Landmarker samples the same preview
 * at 2 Hz. Only face-center coordinates and matrix-derived orientation angles
 * enter a 10-sample / 5-second in-memory buffer; no measurements are displayed,
 * logged, or sent, and task failures do not affect the interview.
 *
 * Camera (Stage 4 metadata): a gated metadata-only publish shape for the Stage 2/3
 * values (`{ type, timestamp, face_count, flag }`, primitives only). The shape
 * and its strict validator live in `aiInterviewRules.ts` so they can be unit
 * tested without React, the room, or the backend. It remains unused: the
 * applicant token is minted with `can_publish_data=False`
 * (`app/services/ai_interview_service.py`), so LiveKit itself would refuse any
 * `publishData()` call. Wiring a publisher (token grant + backend receiver)
 * needs explicit approval and is NOT part of Stage 4.
 *
 * Three views, one per question the applicant has at that moment:
 *
 *   ready    - what job, when, am I ready?          (before starting)
 *   session  - whose turn is it, which question?     (while it runs)
 *   complete - is it finished?                       (after the closing line)
 *
 * The session view reads the agent's published attributes
 * (`smarthr.interview.state`, `smarthr.interview.question`, `lk.agent.state`)
 * and folds them into ONE applicant-facing state. The raw values are still
 * available under a collapsed "Technical details" for support; they are not
 * part of the normal view.
 *
 * The transcript is what LiveKit streams on `lk.transcription`; it is
 * displayed, never stored. Consecutive segments from one speaker are merged
 * into one bubble at render time only - the segments themselves are kept
 * exactly as they arrived, because a segment may still be refined.
 */

/** Topic and attribute names published by livekit-agents (livekit/agents/types.py). */
const TRANSCRIPTION_TOPIC = 'lk.transcription';
const ATTR_SEGMENT_ID = 'lk.segment_id';
const ATTR_FINAL = 'lk.transcription_final';
const ATTR_AGENT_STATE = 'lk.agent.state';
/** Published by SmartHR's interview controller (app/ai/interview/controller.py). */
const ATTR_INTERVIEW_STATE = 'smarthr.interview.state';
/** {number, total} - which Question Bank question is current. No ids, no text. */
const ATTR_QUESTION = 'smarthr.interview.question';

/**
 * The notice shown before Start (Phase 10), one `aiInterview.notice.*` key
 * each: an AI interviewer; the answers' TEXT is stored (no audio); each answer
 * is analysed by AI; HR can read both; no hiring decision is made by the AI.
 * Checked by frontend/scripts/check-ai-interview-notice.ts.
 */
const NOTICE_POINTS = ['ai', 'stored', 'analysed', 'hrReview', 'noDecision'] as const;

type Line = { id: string; speaker: 'interviewer' | 'you'; text: string; final: boolean };
type LineGroup = { key: string; speaker: Line['speaker']; lines: Line[] };

/*
 * Phase 11.6.1: the applicant-facing state comes from `viewStateOf` in
 * aiInterviewRules.ts - the page's phase, LiveKit's connection state, whether
 * the interviewer is in the room, the interview controller's published state
 * and LiveKit's agent state. Every indicator on this page reads one of those
 * (or the microphone's real result / LiveKit's speaking flag) - none is
 * simulated.
 */

const VIEW_STYLE: Record<ViewState, { panel: string; icon: string }> = {
  connecting: { panel: 'bg-sand-50 border-sand-200', icon: 'bg-sand-100 text-stone-500' },
  waiting: { panel: 'bg-sand-50 border-sand-200', icon: 'bg-sand-100 text-stone-500' },
  reconnecting: { panel: 'bg-amber-50 border-amber-200', icon: 'bg-amber-100 text-amber-700' },
  speaking: { panel: 'bg-sand-50 border-sand-300', icon: 'bg-sand-200 text-stone-700' },
  ending: { panel: 'bg-sand-50 border-sand-300', icon: 'bg-sand-200 text-stone-700' },
  yourTurn: { panel: 'bg-brand-50 border-brand-300 ring-2 ring-brand-100', icon: 'bg-brand-600 text-white' },
  thinking: { panel: 'bg-stone-50 border-stone-200', icon: 'bg-stone-100 text-stone-500' },
  stopped: { panel: 'bg-stone-50 border-stone-200', icon: 'bg-stone-100 text-stone-500' },
  failed: { panel: 'bg-red-50 border-red-200', icon: 'bg-red-100 text-red-600' },
};

/** The local camera preview - independent of the microphone's status. */
type CameraStatus = 'pending' | 'active' | 'off' | 'denied' | 'unavailable' | 'error';

/** Stage 2 face detection, kept separate from the camera-open status so a
 *  detector failure never changes what the preview shows. `null` = not yet
 *  attempted or camera off; `false` = detector unavailable (preview still
 *  works); `true` = detector running. */
type FaceDetectionStatus = 'pending' | 'active' | 'unavailable' | null;

/** Stage 2: MediaPipe Face Detector model (short-range, ~230KB) + wasm runtime. */
const FACE_MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite';
const FACE_WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm';
const FACE_LANDMARKER_MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

/** Stage 2: the only console record - `{ timestamp, face_count }`, no pixels. */
const traceFaces = (faceCount: FaceCount) => {
  console.info('[AI Interview] faces', formatFaceLog(new Date().toISOString(), faceCount));
};

/** Stage 3: a sustained flag fired - metadata only, never sent anywhere. */
const traceProctorFlag = (faceCount: FaceCount, flag: ProctorFlag) => {
  console.info('[AI Interview] proctor', formatProctorFlagLog(new Date().toISOString(), faceCount, flag));
};

/**
 * Stage 4: reference to the gated payload shape, so the page - and the
 * static checks - fail if the approved `{ type, timestamp, face_count, flag }`
 * contract in `aiInterviewRules.ts` ever drifts. No data publisher is wired:
 * `can_publish_data=False` on the applicant token forbids `publishData()`,
 * so this constant is documentation-by-import, not a send path.
 */
void CAMERA_PROCTORING_TYPE;

/** How long Start waits for a camera preview that is still opening before it
 *  asks for the microphone anyway. */
const CAMERA_WAIT_MS = 2000;

/** LiveKit track name for the applicant's Stage 4A camera video. */
const CAMERA_TRACK_NAME = 'ai-interview-camera';

/** Stage 4A: safe camera-publish diagnostics - names, SIDs and states only. */
const traceCameraPublish = (event: string, detail: Record<string, string> = {}) => {
  console.info('[AI Interview] camera', event, detail);
};

/** One console line per way a session ends or fails to start, so a support
 *  report can say WHICH path closed the room. Closed vocabulary only: event
 *  and stage names and an error's class name - never a message, a token or
 *  anything the applicant said. */
const traceSession = (event: string, detail: Record<string, string> = {}) => {
  console.info('[AI Interview]', event, detail);
};
const errorName = (e: unknown): string =>
  (e as { name?: string } | null)?.name ?? typeof e;

/** A start failure whose message is already our own translated sentence. */
class StageError extends Error {}

export const AiInterviewPage: React.FC<{
  /** Pre-selects this interview when the page is opened from another page. */
  initialInterviewId?: number | null;
  onNavigate?: (page: PageId) => void;
}> = ({ initialInterviewId = null, onNavigate }) => {
  const { t, locale } = useT();

  const [status, setStatus] = useState<AiInterviewStatus | null>(null);
  const [interviews, setInterviews] = useState<AiInterviewListing[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  /** The job title the backend bound the live session to. */
  const [sessionJob, setSessionJob] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [agentJoined, setAgentJoined] = useState(false);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [interviewState, setInterviewState] = useState<InterviewState | null>(null);
  const [question, setQuestion] = useState<{ number: number; total: number } | null>(null);
  /** The interviewer spoke its closing line: the interview is finished. */
  const [completed, setCompleted] = useState(false);
  /** A Question Bank question was presented in this session - the interviewer
   *  reached ASKING. Without it, "completed" means the interview could not go
   *  ahead (e.g. its questions could not be loaded), not that it finished. */
  const [questionPresented, setQuestionPresented] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [languageModalOpen, setLanguageModalOpen] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState<'en' | 'ar' | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [lines, setLines] = useState<Line[]>([]);
  const [needsAudioStart, setNeedsAudioStart] = useState(false);
  /** Phase 11.6.1 - each from a real source: LiveKit's room connection state,
   *  the microphone's actual result, LiveKit's speaking flag for the applicant,
   *  and the backend's refusal code (which decides whether "Try again" can work). */
  const [connection, setConnection] = useState<Connection | null>(null);
  const [micStatus, setMicStatus] = useState<MicStatus | null>(null);
  const [localSpeaking, setLocalSpeaking] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>('pending');
  /** Stage 2: the current local face count (2 means "2+") - shown under the
   *  preview, never sent anywhere. `null` until the first sample runs. */
  const [faceCount, setFaceCount] = useState<FaceCount | null>(null);
  /** Stage 2: whether the on-device detector is running - a failure shows its
   *  own message and never touches the preview status or the microphone. */
  const [faceDetection, setFaceDetection] = useState<FaceDetectionStatus>(null);
  /** Stage 3: sustained-condition display fed by the SAME Stage 2 samples -
   *  metadata only, never stops/mutes/disconnects anything. `null` until the
   *  first sample (the line is hidden). */
  const [proctorState, setProctorState] = useState<ProctorState | null>(null);
  /** The clock the start window is judged against - ticks so Start becomes
   *  available by itself when the window opens (Phase 10). */
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  const roomRef = useRef<Room | null>(null);
  const audioHostRef = useRef<HTMLDivElement | null>(null);
  const meterRef = useRef<{ ctx: AudioContext; frame: number } | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  /** Read inside LiveKit handlers, which close over the first render. */
  const interviewStateRef = useRef<InterviewState | null>(null);
  const completedRef = useRef(false);
  /** The local camera preview track - Stage 4A publishes this SAME track to
   *  the room after connect; the local preview stays attached throughout. */
  const cameraTrackRef = useRef<LocalVideoTrack | null>(null);
  /** Stage 4A: the camera publication once the existing track is published to
   *  the room (null until published). Used to avoid duplicates and to
   *  unpublish on cleanup. */
  const cameraPublicationRef = useRef<{
    room: Room;
    track: LocalVideoTrack;
    publication: LocalTrackPublication;
  } | null>(null);
  /** A single in-flight publish per exact track/room pair. */
  const cameraPublishingRef = useRef<{
    room: Room;
    track: LocalVideoTrack;
    promise: Promise<void>;
  } | null>(null);
  /** The preview element (it re-mounts between the ready and session views). */
  const cameraVideoRef = useRef<HTMLVideoElement | null>(null);
  /** Bumped on every start/stop, so a camera that finishes opening after it
   *  was stopped (or after the page unmounted) is released at once. */
  const cameraRunRef = useRef(0);
  /** The camera open in progress, if any (see startCamera). */
  const cameraOpeningRef = useRef<Promise<void> | null>(null);
  /** Stage 2: the on-device Face Detector (closed on every camera stop). */
  const faceDetectorRef = useRef<{ detectForVideo: (video: HTMLVideoElement, nowMs: number) => { detections?: unknown[] }; close: () => void } | null>(null);
  /** Stage 2: the detector load in progress, if any (never twice at once). */
  const faceDetectorOpeningRef = useRef<Promise<void> | null>(null);
  /** Stage 2: the sampling timer id (`window.setTimeout` chain, ~1.5s). */
  const faceTimerRef = useRef<number | null>(null);
  /** Stage 2: bumped on every stop, so a sample scheduled before a stop or
   *  unmount never runs against a released detector. */
  const faceRunRef = useRef(0);
  /** Stage 6: local geometry task, independent of FaceDetector and proctoring. */
  const faceLandmarkerRef = useRef<{
    detectForVideo: (video: HTMLVideoElement, nowMs: number) => unknown;
    close: () => void;
  } | null>(null);
  const faceLandmarkerOpeningRef = useRef<Promise<void> | null>(null);
  const faceLandmarkerTimerRef = useRef<number | null>(null);
  const faceLandmarkerRunRef = useRef(0);
  const facialSamplesRef = useRef(new FacialSampleBuffer());
  const facialMotionSummaryRef = useRef<FacialMotionSummary | null>(null);
  const speechMouthEpisodeRef = useRef(new SpeechMouthEpisode());
  const speechMouthSummaryRef = useRef<SpeechMouthEpisodeSummary | null>(null);
  const speechFacePresenceEpisodeRef = useRef(new SpeechFacePresenceEpisode());
  const speechFacePresenceSummaryRef = useRef<SpeechFacePresenceSummary | null>(null);
  /** Stage 3: per-condition stopwatches fed by the same samples (plain object,
   *  not state - samples update it without re-rendering). Reset with the camera. */
  const proctorTimersRef = useRef<ProctorTimers>(initialProctorTimers());
  /** Stage 3: the last emitted flag, so a sustained condition logs its flag
   *  record once per continuous episode - not on every sample. */
  const proctorFlagRef = useRef<ProctorFlag | null>(null);

  useEffect(() => {
    SmartHRApi.getAiInterviewStatus()
      .then(setStatus)
      .catch((e: Error) => setStatusError(e.message));
    SmartHRApi.getMyAiInterviews()
      .then(({ interviews: list }) => {
        setInterviews(list);
        const preferred = list.find((i) => i.interview_id === initialInterviewId);
        const testInterview = list.find((interview) => interview.is_test);
        setSelectedId(preferred?.interview_id
          ?? testInterview?.interview_id
          ?? list[0]?.interview_id
          ?? null);
      })
      .catch((e: Error) => {
        setInterviews([]);
        setStatusError(e.message);
      });
  }, [initialInterviewId]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ block: 'nearest' });
  }, [lines]);

  const stopMeter = useCallback(() => {
    if (meterRef.current) {
      cancelAnimationFrame(meterRef.current.frame);
      meterRef.current.ctx.close().catch(() => undefined);
      meterRef.current = null;
    }
    setMicLevel(0);
  }, []);

  /** The microphone level, read from the very track LiveKit is publishing. */
  const startMeter = useCallback((mediaStreamTrack: MediaStreamTrack) => {
    stopMeter();
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(new MediaStream([mediaStreamTrack])).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);

    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) {
        const v = (s - 128) / 128;
        sum += v * v;
      }
      // RMS, scaled so ordinary speech fills most of the bar.
      setMicLevel(Math.min(1, Math.sqrt(sum / samples.length) * 4));
      if (meterRef.current) meterRef.current.frame = requestAnimationFrame(tick);
    };

    meterRef.current = { ctx, frame: requestAnimationFrame(tick) };
  }, [stopMeter]);

  /** Stage 2: stops face sampling and releases the detector. Never throws into
   *  the camera/microphone paths; safe to call when nothing is running. */
  const stopFaceSampling = useCallback(() => {
    faceRunRef.current += 1;
    if (faceTimerRef.current !== null) {
      window.clearTimeout(faceTimerRef.current);
      faceTimerRef.current = null;
    }
    faceDetectorOpeningRef.current = null;
    const detector = faceDetectorRef.current;
    faceDetectorRef.current = null;
    if (detector) {
      try {
        detector.close();
      } catch {
        // already released
      }
    }
    setFaceDetection((s) => (s === 'pending' || s === 'active' ? null : s));
    setFaceCount(null);
    // Stage 3: sustained timers belong to the camera run - a restart starts clean.
    proctorTimersRef.current = initialProctorTimers();
    proctorFlagRef.current = null;
    setProctorState(null);
  }, []);

  /** Stage 6: only derived, single-face geometry enters this bounded local window. */
  const sampleFaceGeometry = useCallback((run: number) => {
    const landmarker = faceLandmarkerRef.current;
    const video = cameraVideoRef.current;
    if (run !== faceLandmarkerRunRef.current || !landmarker) return;
    if (!video) {
      facialSamplesRef.current.clear();
      facialMotionSummaryRef.current = null;
      speechFacePresenceEpisodeRef.current.addObservation(performance.now(), null);
      speechMouthEpisodeRef.current.addFaceSample(performance.now(), null);
      faceLandmarkerTimerRef.current = window.setTimeout(
        () => sampleFaceGeometry(run), FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
      );
      return;
    }
    if (video.readyState < 2 || video.videoWidth === 0) {
      facialSamplesRef.current.clear();
      facialMotionSummaryRef.current = null;
      speechFacePresenceEpisodeRef.current.addObservation(performance.now(), null);
      speechMouthEpisodeRef.current.addFaceSample(performance.now(), null);
      if (run === faceLandmarkerRunRef.current) {
        faceLandmarkerTimerRef.current = window.setTimeout(
          () => sampleFaceGeometry(run), FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
        );
      }
      return;
    }
    try {
      const timestampMs = performance.now();
      const result = landmarker.detectForVideo(video, timestampMs);
      const sample = geometrySampleFromResult(result, timestampMs);
      if (run === faceLandmarkerRunRef.current) {
        speechFacePresenceEpisodeRef.current.addObservation(timestampMs, result);
        speechMouthEpisodeRef.current.addFaceSample(timestampMs, mouthApertureFromResult(result));
        if (sample) {
          facialSamplesRef.current.add(sample);
          facialMotionSummaryRef.current = summarizeFacialMotion(facialSamplesRef.current.values());
        } else {
          facialSamplesRef.current.clear();
          facialMotionSummaryRef.current = null;
        }
      }
    } catch {
      if (run === faceLandmarkerRunRef.current) {
        speechFacePresenceEpisodeRef.current.addObservation(performance.now(), null);
        speechMouthEpisodeRef.current.addFaceSample(performance.now(), null);
        facialSamplesRef.current.clear();
        facialMotionSummaryRef.current = null;
      }
    } finally {
      if (run === faceLandmarkerRunRef.current) {
        faceLandmarkerTimerRef.current = window.setTimeout(
          () => sampleFaceGeometry(run), FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
        );
      }
    }
  }, []);

  /** Stage 6: lazily initializes against the existing preview; failure is optional. */
  const startFaceLandmarkerSampling = useCallback(() => {
    if (faceLandmarkerRef.current || faceLandmarkerOpeningRef.current) return;
    const run = faceLandmarkerRunRef.current;
    const opening = (async () => {
      let landmarker: {
        detectForVideo: (video: HTMLVideoElement, nowMs: number) => unknown;
        close: () => void;
      } | null = null;
      try {
        const vision = await import('@mediapipe/tasks-vision');
        if (run !== faceLandmarkerRunRef.current) return;
        const fileset = await vision.FilesetResolver.forVisionTasks(FACE_WASM_URL);
        if (run !== faceLandmarkerRunRef.current) return;
        landmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: FACE_LANDMARKER_MODEL_URL, delegate: 'GPU' },
          runningMode: 'VIDEO',
          numFaces: 2,
          outputFaceBlendshapes: false,
          outputFacialTransformationMatrixes: true,
        });
        if (run !== faceLandmarkerRunRef.current) {
          landmarker.close();
          return;
        }
        faceLandmarkerRef.current = landmarker;
        faceLandmarkerTimerRef.current = window.setTimeout(
          () => sampleFaceGeometry(run), FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
        );
      } catch {
        if (run === faceLandmarkerRunRef.current) {
          facialSamplesRef.current.clear();
          facialMotionSummaryRef.current = null;
          speechMouthEpisodeRef.current.reset();
          speechMouthSummaryRef.current = null;
          speechFacePresenceEpisodeRef.current.reset();
          speechFacePresenceSummaryRef.current = null;
        }
        if (landmarker) {
          try {
            landmarker.close();
          } catch {
            // The optional geometry task must not affect the camera or interview.
          }
        }
      } finally {
        if (run === faceLandmarkerRunRef.current) faceLandmarkerOpeningRef.current = null;
      }
    })();
    faceLandmarkerOpeningRef.current = opening;
    void opening;
  }, [sampleFaceGeometry]);

  /** Stops Stage 6 without changing Stage 2/3 state or camera behavior. */
  const stopFaceLandmarkerSampling = useCallback(() => {
    faceLandmarkerRunRef.current += 1;
    if (faceLandmarkerTimerRef.current !== null) {
      window.clearTimeout(faceLandmarkerTimerRef.current);
      faceLandmarkerTimerRef.current = null;
    }
    faceLandmarkerOpeningRef.current = null;
    const landmarker = faceLandmarkerRef.current;
    faceLandmarkerRef.current = null;
    facialSamplesRef.current.clear();
    facialMotionSummaryRef.current = null;
    speechFacePresenceEpisodeRef.current.reset();
    speechFacePresenceSummaryRef.current = null;
    if (landmarker) {
      try {
        landmarker.close();
      } catch {
        // The optional geometry task must not affect the camera or interview.
      }
    }
  }, []);

  /** Stage 2: one sample against the existing preview <video> element - only
   *  `detections.length` is read, folded to 0 | 1 | 2 ("2+"). No canvas,
   *  snapshot or pixel extraction; the count is shown and logged, never sent.
   *  Stage 3 feeds the SAME count into the sustained-condition aggregation
   *  (no second timer, no detector change) - flags are metadata only. */
  const sampleFaces = useCallback((run: number) => {
    const detector = faceDetectorRef.current;
    const video = cameraVideoRef.current;
    if (run !== faceRunRef.current || !detector || !video) return;
    if (video.readyState < 2 || video.videoWidth === 0) {
      if (run === faceRunRef.current) {
        faceTimerRef.current = window.setTimeout(() => sampleFaces(run), FACE_SAMPLE_INTERVAL_MS);
      }
      return;
    }
    try {
      const result = detector.detectForVideo(video, performance.now());
      const count = faceCountOf(Array.isArray(result?.detections) ? result.detections.length : 0);
      if (run === faceRunRef.current) {
        setFaceCount(count);
        traceFaces(count);
        // Stage 3: sustained aggregation on the same sample. Any return to
        // normal resets that condition's timer inside updateProctorState.
        const state = updateProctorState(proctorTimersRef.current, count, Date.now());
        setProctorState(state);
        if (isProctorFlag(state)) {
          if (proctorFlagRef.current !== state) {
            proctorFlagRef.current = state;
            traceProctorFlag(count, state);
          }
        } else {
          proctorFlagRef.current = null;
        }
      }
    } catch {
      // A single bad frame must not stop sampling or touch audio/preview.
    } finally {
      if (run === faceRunRef.current) {
        faceTimerRef.current = window.setTimeout(() => sampleFaces(run), FACE_SAMPLE_INTERVAL_MS);
      }
    }
  }, []);

  /** Stage 2: loads the on-device Face Detector lazily (kept out of the
   *  initial bundle) and starts the ~1.5s sampling chain. A load or init
   *  failure shows its own message; the preview and the interview continue. */
  const startFaceSampling = useCallback(() => {
    if (faceDetectorRef.current || faceDetectorOpeningRef.current) return;
    const run = faceRunRef.current;
    setFaceDetection('pending');
    const opening = (async () => {
      try {
        const vision = await import('@mediapipe/tasks-vision');
        if (run !== faceRunRef.current) return;
        const fileset = await vision.FilesetResolver.forVisionTasks(FACE_WASM_URL);
        if (run !== faceRunRef.current) return;
        const detector = await vision.FaceDetector.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: FACE_MODEL_URL, delegate: 'GPU' },
          runningMode: 'VIDEO',
        });
        if (run !== faceRunRef.current) {
          try {
            detector.close();
          } catch {
            // already released
          }
          return;
        }
        faceDetectorRef.current = detector;
        setFaceDetection('active');
        sampleFaces(run);
      } catch {
        if (run === faceRunRef.current) {
          faceDetectorRef.current = null;
          setFaceDetection('unavailable');
          setFaceCount(null);
          // Stage 3: without samples there is no sustained state to show.
          proctorTimersRef.current = initialProctorTimers();
          proctorFlagRef.current = null;
          setProctorState(null);
        }
      } finally {
        if (run === faceRunRef.current) faceDetectorOpeningRef.current = null;
      }
    })();
    faceDetectorOpeningRef.current = opening;
    void opening;
  }, [sampleFaces]);

  /** Publish the one preview/detector track, only after this room is connected. */
  const publishCameraTrack = useCallback((room: Room, track: LocalVideoTrack): Promise<void> => {
    if (cameraTrackRef.current !== track || room.state !== ConnectionState.Connected) {
      return Promise.resolve();
    }
    const participant = room.localParticipant;
    const existing = participant.getTrackPublication(Track.Source.Camera);
    if (existing?.track === track) {
      cameraPublicationRef.current = { room, track, publication: existing as LocalTrackPublication };
      return Promise.resolve();
    }
    const published = cameraPublicationRef.current;
    if (published?.room === room && published.track === track) return Promise.resolve();
    const pending = cameraPublishingRef.current;
    if (pending?.room === room && pending.track === track) return pending.promise;

    const promise = (async () => {
      traceCameraPublish('publication started', { source: 'camera', name: CAMERA_TRACK_NAME });
      try {
        // livekit-client 2.22.3: publishTrack(LocalTrack, TrackPublishOptions).
        const publication = await participant.publishTrack(track, { name: CAMERA_TRACK_NAME });
        if (cameraTrackRef.current !== track || roomRef.current !== room ||
            room.state !== ConnectionState.Connected) {
          await participant.unpublishTrack(track, false).catch(() => undefined);
          traceCameraPublish('publication removed', {
            source: String(publication.source), name: publication.trackName || CAMERA_TRACK_NAME,
            sid: publication.trackSid || 'unavailable', reason: 'stale-session',
          });
          return;
        }
        cameraPublicationRef.current = { room, track, publication };
        traceCameraPublish('publication succeeded', {
          source: String(publication.source), name: publication.trackName || CAMERA_TRACK_NAME,
          sid: publication.trackSid || 'unavailable',
        });
      } catch (e) {
        traceCameraPublish('publication failed', {
          source: 'camera', name: CAMERA_TRACK_NAME, error: errorName(e),
        });
        // Camera transport failure is isolated; microphone startup continues.
      }
    })();
    cameraPublishingRef.current = { room, track, promise };
    void promise.finally(() => {
      if (cameraPublishingRef.current?.promise === promise) cameraPublishingRef.current = null;
    });
    return promise;
  }, []);

  /** Releases the camera publication, preview and detector. A failure message stays. */
  const stopCamera = useCallback(async () => {
    stopFaceLandmarkerSampling();
    stopFaceSampling();
    cameraRunRef.current += 1;
    // Keep an in-flight device-open promise visible until it settles. A quick
    // restart waits for that stale open to release before requesting a track.
    const track = cameraTrackRef.current;
    cameraTrackRef.current = null;
    const pending = cameraPublishingRef.current;
    if (pending?.track === track) await pending.promise;
    const current = cameraPublicationRef.current;
    if (current?.track === track) {
      cameraPublicationRef.current = null;
      if (current.room.state === ConnectionState.Connected) {
        try {
          await current.room.localParticipant.unpublishTrack(track, false);
          traceCameraPublish('publication removed', {
            source: String(current.publication.source), name: current.publication.trackName || CAMERA_TRACK_NAME,
            sid: current.publication.trackSid || 'unavailable', reason: 'camera-stopped',
          });
        } catch (e) {
          traceCameraPublish('publication removal failed', {
            source: 'camera', name: CAMERA_TRACK_NAME, error: errorName(e),
          });
        }
      } else {
        traceCameraPublish('publication removed', {
          source: String(current.publication.source), name: current.publication.trackName || CAMERA_TRACK_NAME,
          sid: current.publication.trackSid || 'unavailable', reason: 'room-disconnected',
        });
      }
    }
    if (track) {
      // Called from cleanup() and the room's Disconnected handler: releasing
      // the camera must never throw into the room/microphone paths.
      try {
        track.detach();
        track.stop();
      } catch {
        // already released
      }
    }
    setCameraStatus((s) => (s === 'active' || s === 'pending' ? 'off' : s));
  }, [stopFaceSampling, stopFaceLandmarkerSampling]);

  /** One preview track is also published to the connected interview room.
   *  A failure is shown on the camera panel and nowhere else - the interview
   *  does not depend on the camera. */
  const startCamera = useCallback((): Promise<void> => {
    if (cameraTrackRef.current) return Promise.resolve();
    if (cameraOpeningRef.current) return cameraOpeningRef.current;
    const run = ++cameraRunRef.current;
    setCameraStatus('pending');
    // Kept so start() can let an in-flight camera open finish before it asks
    // for the microphone - the two device opens never overlap. The whole body
    // is inside try/catch, so this promise never rejects.
    let opening!: Promise<void>;
    opening = (async () => {
      try {
        const track = await createLocalVideoTrack({ resolution: { width: 640, height: 360 } });
        if (run !== cameraRunRef.current) {
          track.stop();   // stopped, or the page unmounted, while it was opening
          return;
        }
        cameraTrackRef.current = track;
        traceCameraPublish('track created', { source: 'camera', name: CAMERA_TRACK_NAME });
        if (cameraVideoRef.current) track.attach(cameraVideoRef.current);
        // The camera stopped by itself (unplugged, taken by another app).
        track.mediaStreamTrack.addEventListener('ended', () => {
          if (cameraTrackRef.current !== track) return;
          stopCamera();
          setCameraStatus('error');
        });
        setCameraStatus('active');
        const room = roomRef.current;
        if (room?.state === ConnectionState.Connected) void publishCameraTrack(room, track);
        // Stage 2: the same preview feeds the on-device face count. A detector
        // failure keeps this preview and never touches the microphone.
        startFaceSampling();
        startFaceLandmarkerSampling();
      } catch (e) {
        // The same getUserMedia error names as the microphone, classified into
        // the CAMERA's own status - never the microphone's, never `error`.
        if (run === cameraRunRef.current) setCameraStatus(micFailureOf(e));
      } finally {
        if (cameraOpeningRef.current === opening) cameraOpeningRef.current = null;
      }
    })();
    cameraOpeningRef.current = opening;
    return opening;
  }, [stopCamera, startFaceSampling, startFaceLandmarkerSampling, publishCameraTrack]);

  /** Each (re-)mounted preview element is attached to the running track. */
  const setCameraVideo = useCallback((element: HTMLVideoElement | null) => {
    cameraVideoRef.current = element;
    if (element && cameraTrackRef.current) cameraTrackRef.current.attach(element);
    if (element && faceLandmarkerRef.current && faceLandmarkerTimerRef.current === null) {
      const run = faceLandmarkerRunRef.current;
      faceLandmarkerTimerRef.current = window.setTimeout(
        () => sampleFaceGeometry(run), FACE_LANDMARKER_SAMPLE_INTERVAL_MS,
      );
    }
  }, [sampleFaceGeometry]);

  const markCompleted = () => {
    speechMouthEpisodeRef.current.reset();
    speechMouthSummaryRef.current = null;
    speechFacePresenceEpisodeRef.current.reset();
    speechFacePresenceSummaryRef.current = null;
    completedRef.current = true;
    setCompleted(true);
  };

  const readAgentState = (participant: Participant) => {
    const value = participant.attributes[ATTR_AGENT_STATE] as AgentState | undefined;
    if (value && AGENT_STATES.includes(value)) setAgentState(value);
    const phase = participant.attributes[ATTR_INTERVIEW_STATE] as InterviewState | undefined;
    if (phase && INTERVIEW_STATES.includes(phase)) {
      interviewStateRef.current = phase;
      setInterviewState(phase);
      // The controller enters ASKING only while speaking a bank question
      // (Q1 in the opening, later ones after an answer); LISTENING and
      // PROCESSING can only follow one.
      if (phase === 'asking' || phase === 'listening' || phase === 'processing') {
        setQuestionPresented(true);
      }
      if (phase === 'completed') markCompleted();
    }
    const raw = participant.attributes[ATTR_QUESTION];
    if (raw) {
      try {
        const q = JSON.parse(raw) as { number?: unknown; total?: unknown };
        if (typeof q.number === 'number' && typeof q.total === 'number') {
          setQuestion({ number: q.number, total: q.total });
        }
      } catch {
        // A malformed attribute is ignored rather than shown.
      }
    }
  };

  const cleanup = useCallback(() => {
    stopMeter();
    speechMouthEpisodeRef.current.reset();
    speechMouthSummaryRef.current = null;
    speechFacePresenceEpisodeRef.current.reset();
    speechFacePresenceSummaryRef.current = null;
    void stopCamera();
    if (audioHostRef.current) audioHostRef.current.innerHTML = '';
    roomRef.current = null;
  }, [stopMeter, stopCamera]);

  const startWithLanguage = useCallback(async (language: 'en' | 'ar') => {
    speechMouthEpisodeRef.current.reset();
    speechMouthSummaryRef.current = null;
    speechFacePresenceEpisodeRef.current.reset();
    speechFacePresenceSummaryRef.current = null;
    setError(null);
    setLines([]);
    setAgentJoined(false);
    setAgentState(null);
    setInterviewState(null);
    interviewStateRef.current = null;
    completedRef.current = false;
    setCompleted(false);
    setQuestionPresented(false);
    setConfirmRestart(false);
    setQuestion(null);
    setSessionJob(null);
    setErrorCode(null);
    setMicStatus(null);
    setLocalSpeaking(false);
    setConnection(null);
    if (selectedId === null) return;
    setPhase('connecting');

    let room: Room | null = null;
    /** Which step was running, for the trace if the start fails. */
    let stage = 'room_setup';

    // 1. SmartHR: may this interview start now? A refusal carries a code.
    let session: Awaited<ReturnType<typeof SmartHRApi.startAiInterviewSession>>;
    try {
      session = await SmartHRApi.startAiInterviewSession(selectedId, language);
    } catch (e) {
      setErrorCode(e instanceof ApiError ? e.code : null);
      setError(refusalMessage(e));
      setPhase('error');
      return;
    }

    try {
      setSessionJob(session.interview.job_title);
      if (!cameraTrackRef.current) {
        const openingCamera = cameraOpeningRef.current;
        // A previous room cleanup may have invalidated a still-opening camera
        // request. Let it release, then reopen through the same camera path.
        void (async () => {
          if (openingCamera) await openingCamera;
          if (!cameraTrackRef.current) await startCamera();
        })();
      }
      setConnection('connecting');
      room = new Room();
      roomRef.current = room;

      room
        .on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
          if (p.isAgent) {
            setAgentJoined(true);
            readAgentState(p);
          }
        })
        .on(RoomEvent.ParticipantAttributesChanged, (_changed, p: Participant) => {
          if (p.isAgent) readAgentState(p);
        })
        .on(RoomEvent.ParticipantDisconnected, (p: RemoteParticipant) => {
          if (!p.isAgent) return;
          setAgentJoined(false);
          // The interviewer leaves once it has spoken its closing line. If it
          // leaves at any other point the applicant is told, rather than
          // left looking at a "Your turn" nobody is listening to.
          const last = interviewStateRef.current;
          traceSession('interviewer left', { state: last ?? 'none' });
          if (last === 'ending' || last === 'completed') {
            markCompleted();
          } else if (!completedRef.current) {
            setError(t('aiInterview.error.agentLeft'));
            setPhase('error');
          }
          void roomRef.current?.disconnect();
        })
        .on(RoomEvent.TrackSubscribed, (track: RemoteTrack, _pub, p: RemoteParticipant) => {
          if (track.kind === Track.Kind.Audio && p.isAgent) {
            const element = track.attach();
            audioHostRef.current?.appendChild(element);
          }
        })
        .on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
          track.detach().forEach((el) => el.remove());
        })
        .on(RoomEvent.AudioPlaybackStatusChanged, (playing: boolean) => {
          setNeedsAudioStart(!playing);
        })
        .on(RoomEvent.MediaDevicesError, (e: Error) => {
          // The browser's own reason chooses the instruction; it is never shown.
          const failure = micFailureOf(e);
          setMicStatus(failure);
          setError(t(`aiInterview.mic.help.${failure}`));
        })
        .on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
          setConnection(connectionOf(state));
        })
        .on(RoomEvent.Disconnected, (reason?: DisconnectReason) => {
          traceSession('room disconnected', {
            reason: reason === undefined ? 'none' : DisconnectReason[reason] ?? String(reason),
          });
          cleanup();
          setConnection('disconnected');
          setLocalSpeaking(false);
          setAgentJoined(false);
          setAgentState(null);
          setNeedsAudioStart(false);
          setPhase((current) => (current === 'error' ? current : 'ended'));
          // A room closed after the closing line is the normal end, not a
          // lost connection.
          if (
            !completedRef.current &&
            reason !== undefined &&
            reason !== DisconnectReason.CLIENT_INITIATED
          ) {
            setError(t('aiInterview.error.disconnected'));
          }
        });

      // Both sides of the conversation arrive on one topic; the sender
      // identity says whose words they are. A segment may be re-sent as it is
      // refined, so lines are keyed by segment id and replaced, not appended.
      room.registerTextStreamHandler(
        TRANSCRIPTION_TOPIC,
        async (reader: TextStreamReader, info: { identity: string }) => {
          const attributes = reader.info.attributes ?? {};
          const id = attributes[ATTR_SEGMENT_ID] ?? reader.info.id;
          const speaker: Line['speaker'] =
            info.identity === session.participant_identity ? 'you' : 'interviewer';
          let text = '';

          const upsert = (final: boolean) => {
            const snapshot = text;
            setLines((prev) => {
              const index = prev.findIndex((line) => line.id === id);
              const line: Line = { id, speaker, text: snapshot, final };
              if (index === -1) return [...prev, line];
              const next = prev.slice();
              next[index] = line;
              return next;
            });
          };

          for await (const chunk of reader) {
            text += chunk;
            upsert(attributes[ATTR_FINAL] === 'true');
          }
          // The final flag can arrive with the end of the stream, so it is
          // read again once the stream has closed.
          upsert((reader.info.attributes ?? {})[ATTR_FINAL] === 'true');
        }
      );

      // 2. LiveKit: join the room.
      stage = 'connect';
      try {
        await room.connect(session.server_url, session.participant_token);
      } catch {
        setConnection('disconnected');
        throw new StageError(t('aiInterview.error.connection'));
      }
      // Publish only after connect. This promise is deliberately not awaited:
      // camera negotiation must never delay or fail the voice path.
      if (cameraTrackRef.current) void publishCameraTrack(room, cameraTrackRef.current);
      // Called inside the click that started the session, so the browser's
      // autoplay policy allows the interviewer's audio to play.
      stage = 'audio';
      await room.startAudio();

      // A camera preview still opening is allowed to finish first, so the
      // camera and the microphone are never being opened at the same moment.
      // Bounded, and its outcome is ignored - the interview does not depend
      // on the camera (and this promise never rejects).
      stage = 'camera_wait';
      const cameraOpening = cameraOpeningRef.current;
      if (cameraOpening) {
        await Promise.race([
          cameraOpening,
          new Promise<void>((resolve) => window.setTimeout(resolve, CAMERA_WAIT_MS)),
        ]);
      }

      // 3. The microphone - its real outcome, classified for the instruction.
      stage = 'microphone';
      setMicStatus('pending');
      try {
        await room.localParticipant.setMicrophoneEnabled(true);
      } catch (e) {
        const failure = micFailureOf(e);
        setMicStatus(failure);
        throw new StageError(t(`aiInterview.mic.help.${failure}`));
      }
      setMicStatus('active');

      // The room is connected and the microphone is published. From here on
      // nothing may take the session down: the speaking flag, the level meter
      // and reading the agent are indicators, so a failure in one is traced
      // and the interview continues.
      try {
        // LiveKit's own "is speaking" flag for the applicant's microphone.
        room.localParticipant.on(ParticipantEvent.IsSpeakingChanged, (speaking: boolean) => {
          const timestampMs = performance.now();
          if (speaking) {
            speechMouthSummaryRef.current = null;
            speechMouthEpisodeRef.current.startSpeech(timestampMs);
            speechFacePresenceSummaryRef.current = null;
            speechFacePresenceEpisodeRef.current.startSpeech(timestampMs);
          } else {
            speechMouthSummaryRef.current = speechMouthEpisodeRef.current.endSpeech(timestampMs);
            speechFacePresenceSummaryRef.current =
              speechFacePresenceEpisodeRef.current.endSpeech(timestampMs);
          }
          setLocalSpeaking(speaking);
        });

        const micTrack = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
        if (micTrack?.mediaStreamTrack) {
          startMeter(micTrack.mediaStreamTrack);
          // Phase 11.6.3: the microphone stopped DURING the interview (unplugged,
          // taken by the system). The browser's own "ended" event - nothing is
          // sent to the interviewer, no answer or turn is created; the applicant
          // is told how to recover.
          micTrack.mediaStreamTrack.addEventListener('ended', () => {
            stopMeter();
            setMicStatus('error');
            setError(t('aiInterview.mic.help.error'));
          });
        }

        room.remoteParticipants.forEach((p) => {
          if (p.isAgent) {
            setAgentJoined(true);
            readAgentState(p);
          }
        });
      } catch (e) {
        traceSession('indicator setup failed (session continues)', { error: errorName(e) });
      }

      setPhase('connected');
    } catch (e) {
      traceSession('start failed', { stage, error: errorName(e) });
      // Only our own sentences reach the screen - never an exception's text.
      setError(e instanceof StageError ? e.message : t('aiInterview.error.startFailed'));
      setPhase('error');
      await stopCamera();
      await room?.disconnect();
      cleanup();
    }
    // `t` is stable per locale; cleanup/startMeter are memoised.
  }, [cleanup, selectedId, startMeter, stopCamera, publishCameraTrack, startCamera, t, interviews, locale]);

  const start = useCallback(() => {
    if (selectedId === null) return;
    setConfirmRestart(false);
    setSelectedLanguage(null);
    setLanguageModalOpen(true);
  }, [selectedId]);

  const confirmLanguageAndStart = useCallback(() => {
    if (selectedLanguage === null) return;
    setLanguageModalOpen(false);
    void startWithLanguage(selectedLanguage);
  }, [selectedLanguage, startWithLanguage]);

  /** A refused Start, in the applicant's language when the backend sent a
   *  known `code` (Phase 10); otherwise the backend's own `detail`. */
  function refusalMessage(e: unknown): string {
    // A backend refusal's own `detail` is written for the applicant; anything
    // else (a network failure, a browser exception) is replaced by our sentence.
    const fallback = e instanceof ApiError ? e.message : t('aiInterview.error.startFailed');
    const key = e instanceof ApiError ? startErrorKey(e.code) : null;
    if (!key) return fallback;
    const listing = interviews?.find((i) => i.interview_id === selectedId) ?? null;
    const when = e instanceof ApiError && e.code === 'too_early' ? listing?.opens_at : listing?.closes_at;
    if (key.endsWith('too_early') || key.endsWith('too_late')) {
      return when ? t(key, { time: formatDateTime(when, locale) }) : fallback;
    }
    return t(key);
  }

  const end = useCallback(async () => {
    if (roomRef.current) traceSession('ended by applicant');
    await stopCamera();
    await roomRef.current?.disconnect();
  }, [stopCamera]);

  // Phase 11.6.4: when a session ends (or fails), re-read the interview list
  // from the backend - an attempt may now be used up or the interview
  // completed - so what is offered next is the backend's truth, not what the
  // page loaded with. An event, not a timer; nothing is created by it.
  useEffect(() => {
    if (phase !== 'ended' && phase !== 'error') return;
    SmartHRApi.getMyAiInterviews()
      .then(({ interviews: list }) => setInterviews(list))
      .catch(() => undefined);   // keep what is shown; Start is still checked by the backend
  }, [phase]);

  // Once the closing line has been heard there is nothing left to say: the
  // microphone is released rather than left open in an empty room.
  useEffect(() => {
    if (completed && roomRef.current) {
      traceSession('interview completed');
      void (async () => {
        await stopCamera();
        await roomRef.current?.disconnect();
      })();
    }
  }, [completed, stopCamera]);

  // The camera preview opens with the page, so its permission prompt comes
  // before Start and the microphone prompt stays inside the Start click.
  useEffect(() => {
    void startCamera();
  }, [startCamera]);

  // Leaving the page ends the session - the room must not outlive the screen,
  // and neither may the camera.
  useEffect(() => () => {
    if (roomRef.current) traceSession('page closed');
    roomRef.current?.disconnect();
    stopMeter();
    void stopCamera();
  }, [stopMeter, stopCamera]);

  /** Consecutive segments from one speaker, shown as one bubble. */
  const groups = useMemo(
    () =>
      lines.reduce<LineGroup[]>((acc, line) => {
        const last = acc[acc.length - 1];
        if (last && last.speaker === line.speaker) {
          acc[acc.length - 1] = { ...last, lines: [...last.lines, line] };
        } else {
          acc.push({ key: line.id, speaker: line.speaker, lines: [line] });
        }
        return acc;
      }, []),
    [lines]
  );

  const configured = status?.configured ?? false;
  const live = phase === 'connected';
  const selected = interviews?.find((i) => i.interview_id === selectedId) ?? null;
  // Phase 10: Start is offered only inside the start window. The backend
  // enforces it regardless; 'unknown' (no window sent) leaves it to the backend.
  const windowNow = startWindow(selected, now);
  const insideWindow = windowNow === 'open' || windowNow === 'unknown';
  // Phase 11.6.4: from the backend's own attempt count (the interview list),
  // so a refreshed page never offers a Start the backend would refuse.
  const attemptsExhausted = selected?.attempts_exhausted === true;
  // Finished properly (closing line heard after questions): nothing to restart.
  const finishedInterview = completed && questionPresented;
  // While a session exists, show the job the backend bound it to.
  const jobTitle = (phase !== 'idle' && sessionJob) || selected?.job_title || null;
  const noInterview = interviews !== null && interviews.length === 0;
  // A start that failed before anything was said goes back to the ready view,
  // with the error and a way to try again.
  const view: 'ready' | 'session' | 'complete' = completed
    ? 'complete'
    : phase === 'idle' || (phase === 'error' && lines.length === 0)
      ? 'ready'
      : 'session';
  const viewState = viewStateOf(phase, connection, agentJoined, interviewState, agentState);
  const turn = turnOf(viewState);
  // After these refusals Start cannot succeed again (the backend said so).
  const retryAllowed = startRetryAllowed(errorCode);
  // The controller publishes "question 1" from the welcome onwards; it is
  // shown only once the interviewer has actually moved on to asking it.
  const questionShown =
    question !== null &&
    question.number > 0 &&
    question.total > 0 &&
    interviewState !== null &&
    interviewState !== 'waiting' &&
    interviewState !== 'intro';
  const questionNumber = question ? Math.min(question.number, question.total) : 0;

  const scheduledLabel = (listing: AiInterviewListing | null) =>
    listing?.is_test
      ? t('aiInterview.test.alwaysAvailable')
      : listing?.scheduled_at
      ? t('aiInterview.job.scheduled', { date: formatDateTime(listing.scheduled_at, locale) })
      : t('aiInterview.job.noDate');

  if (noInterview && !statusError) {
    return (
      <div className="space-y-6">
        <PageHeader title={t('aiInterview.title')} subtitle={t('aiInterview.subtitle')} icon={<Radio className="w-5 h-5" />} />
        <Card padding="lg" className="flex flex-col items-center text-center py-12">
          <span className="w-12 h-12 rounded-xl bg-sand-100 border border-sand-200 text-brand-600 flex items-center justify-center mb-4">
            <Calendar className="w-6 h-6" aria-hidden="true" />
          </span>
          <h2 className="text-base font-extrabold text-stone-900">{t('aiInterview.noInterview.title')}</h2>
          <p className="text-sm text-stone-500 mt-1.5 max-w-md leading-relaxed">{t('aiInterview.noInterview.body')}</p>
          {onNavigate && (
            <Button
              className="mt-5"
              variant="outline"
              leftIcon={<Send className="w-4 h-4" />}
              onClick={() => onNavigate('app-applications')}
            >
              {t('aiInterview.noInterview.viewApplications')}
            </Button>
          )}
        </Card>
      </div>
    );
  }

  const picker =
    interviews && interviews.length > 1 && view === 'ready' ? (
      <label className="block text-sm">
        <span className="text-stone-500">{t('aiInterview.job.choose')}</span>
        <select
          className="mt-1 w-full rounded-lg border border-sand-300 bg-white px-3 py-2 text-stone-800"
          value={selectedId ?? ''}
          onChange={(e) => setSelectedId(Number(e.target.value))}
        >
          {interviews.map((i) => (
            // Title and time together: two interviews for one job must not
            // look identical. The title is a database value, not translated.
            <option key={i.interview_id} value={i.interview_id}>
              {i.is_test
                ? t('aiInterview.test.label')
                : `${i.job_title} — ${i.scheduled_at
                  ? formatDateTime(i.scheduled_at, locale)
                  : t('aiInterview.job.noDate')}`}
            </option>
          ))}
        </select>
      </label>
    ) : null;

  const jobHeader = (
    <div className="flex items-start gap-3 min-w-0">
      <span className="w-11 h-11 rounded-xl bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center shrink-0">
        <Briefcase className="w-5 h-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-3xs font-bold uppercase tracking-wider text-stone-400">{t('aiInterview.job.label')}</p>
        {/* A database value - shown as stored, never translated. */}
        <p className="text-lg font-extrabold text-stone-900 break-words leading-snug" dir="auto">
          {jobTitle ?? '—'}
        </p>
        {selected?.is_test && (
          <span
            className="mt-1 inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-3xs font-bold text-amber-800"
            data-testid="ai-interview-development-test"
          >
            {t('aiInterview.test.badge')}
          </span>
        )}
        <p className="mt-0.5 text-xs text-stone-500 inline-flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
          {scheduledLabel(selected)}
        </p>
      </div>
    </div>
  );

  /** Stage 1: local camera preview; the video track is sent through LiveKit.
   *  Stage 2 adds the local face count (0 / 1 / 2+) under the preview. */
  const cameraPanel = (
    <div data-testid="ai-interview-camera">
      <p className="text-xs text-stone-600 inline-flex items-start gap-1.5" data-testid="ai-interview-camera-notice">
        <Info className="w-3.5 h-3.5 shrink-0 mt-px text-brand-600" aria-hidden="true" />
        <span>{t('aiInterview.camera.notice')}</span>
      </p>
      <div className="mt-2 relative aspect-video w-full max-w-sm rounded-xl overflow-hidden border border-sand-300 bg-stone-100">
        <video
          ref={setCameraVideo}
          autoPlay
          muted
          playsInline
          aria-label={t('aiInterview.camera.label')}
          className={`w-full h-full object-cover -scale-x-100 ${cameraStatus === 'active' ? '' : 'hidden'}`}
        />
        {cameraStatus !== 'active' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center">
            {cameraStatus === 'pending' ? (
              <Loader2 className="w-5 h-5 animate-spin text-stone-400" aria-hidden="true" />
            ) : (
              <VideoOff className="w-5 h-5 text-stone-400" aria-hidden="true" />
            )}
            <p className="text-xs text-stone-600 leading-relaxed" role="status">
              {t(`aiInterview.camera.status.${cameraStatus}`)}
            </p>
            {cameraStatus !== 'pending' && (
              <Button size="sm" variant="outline" leftIcon={<Video className="w-4 h-4" />} onClick={() => void startCamera()}>
                {cameraStatus === 'off' ? t('aiInterview.camera.turnOn') : t('aiInterview.camera.retry')}
              </Button>
            )}
          </div>
        )}
      </div>
      {cameraStatus === 'active' && (
        <p className="mt-2 text-xs text-stone-600" role="status" data-testid="ai-interview-face-count">
          {faceDetection === 'unavailable'
            ? t('aiInterview.camera.faces.unavailable')
            : faceCount === null
              ? t('aiInterview.camera.status.pending')
              : faceCount === 0
                ? t('aiInterview.camera.faces.zero')
                : faceCount === 1
                  ? t('aiInterview.camera.faces.one')
                  : t('aiInterview.camera.faces.two')}
        </p>
      )}
      {cameraStatus === 'active' && faceDetection === 'active' && proctorState !== null && (
        <p className="mt-1 text-xs text-stone-500" role="status" data-testid="ai-interview-proctor">
          {t(`aiInterview.camera.proctor.${proctorState}`)}
        </p>
      )}
    </div>
  );

  const restartControl = (
    <div className="mt-4 pt-4 border-t border-stone-100">
      {confirmRestart ? (
        <div className="space-y-2">
          <p className="text-xs text-stone-600">{t('aiInterview.restart.confirm')}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={!configured || !insideWindow} onClick={start}>
              {t('aiInterview.restart.yes')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirmRestart(false)}>
              {t('aiInterview.restart.cancel')}
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirmRestart(true)}
          className="text-xs font-semibold text-stone-500 hover:text-brand-700 underline underline-offset-2"
        >
          {t('aiInterview.restart.link')}
        </button>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('aiInterview.title')}
        subtitle={t('aiInterview.subtitle')}
        icon={<Radio className="w-5 h-5" />}
        badge={
          status && !configured ? <Badge variant="warning">{t('aiInterview.badge.notConfigured')}</Badge> : undefined
        }
      />

      {statusError && (
        <InfoPanel title={t('aiInterview.error.statusTitle')} tone="warning" icon={<AlertTriangle className="w-5 h-5" />}>
          <p>{statusError}</p>
        </InfoPanel>
      )}

      {status && !configured && (
        <InfoPanel title={t('aiInterview.notConfigured.title')} tone="warning">
          <p>{t('aiInterview.notConfigured.body')}</p>
        </InfoPanel>
      )}

      {view === 'ready' ? (
        /* ---------------------------------------------------- ready -- */
        <Card padding="lg">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-10">
            <div className="space-y-4">
              {jobHeader}
              {picker}
              {cameraPanel}
            </div>

            <div>
              <h2 className="text-base font-extrabold text-stone-900">{t('aiInterview.ready.title')}</h2>
              <p className="mt-1.5 text-sm text-stone-600 leading-relaxed">{t('aiInterview.ready.body')}</p>
              {selected?.is_test && (
                <p className="mt-2 text-sm font-semibold text-amber-800" role="note">
                  {t('aiInterview.test.notice')}
                </p>
              )}
              <ul className="mt-3 space-y-1.5 text-xs text-stone-600">
                {(['tipOneAtATime', 'tipPause', 'tipMicOnly'] as const).map((tip) => (
                  <li key={tip} className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-brand-600 shrink-0 mt-px" aria-hidden="true" />
                    <span>{t(`aiInterview.ready.${tip}`)}</span>
                  </li>
                ))}
              </ul>

              {/* Phase 10: what happens to the answers - shown before Start. */}
              <InfoPanel
                className="mt-4"
                tone="info"
                title={t('aiInterview.notice.title')}
                icon={<Info className="w-5 h-5" />}
              >
                <ul className="space-y-1.5 text-xs leading-relaxed" data-testid="ai-interview-notice">
                  {NOTICE_POINTS.map((point) => (
                    <li key={point} className="flex items-start gap-2">
                      <span className="mt-1.5 w-1 h-1 rounded-full bg-current shrink-0" aria-hidden="true" />
                      <span>{t(`aiInterview.notice.${point}`)}</span>
                    </li>
                  ))}
                </ul>
              </InfoPanel>

              {/* Phase 10: when Start is available, from the backend's window. */}
              {windowNow !== 'unknown' && selected && (
                <p
                  className={`mt-4 text-sm inline-flex items-start gap-2 ${
                    windowNow === 'open' ? 'text-emerald-700' : windowNow === 'early' ? 'text-amber-700' : 'text-red-700'
                  }`}
                  data-testid="ai-interview-window"
                >
                  <Calendar className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                  <span>
                    {t(`aiInterview.window.${windowNow}`, {
                      time: formatDateTime(windowNow === 'early' ? selected.opens_at : selected.closes_at, locale),
                    })}
                  </span>
                </p>
              )}

              {error && <p className="mt-4 text-sm text-red-700" role="alert">{error}</p>}

              {attemptsExhausted && (
                <p className="mt-4 text-sm text-stone-700" role="status" data-testid="ai-interview-attempts-exhausted">
                  {t('aiInterview.errorCode.attempts_exhausted')}
                </p>
              )}

              {(phase !== 'error' || retryAllowed) && !attemptsExhausted && (
                <Button
                  className="mt-5"
                  variant="primary"
                  size="lg"
                  leftIcon={<Mic className="w-4 h-4" />}
                  disabled={!configured || selectedId === null || !insideWindow}
                  onClick={start}
                >
                  {phase === 'error' ? t('aiInterview.action.retry') : t('aiInterview.action.start')}
                </Button>
              )}
            </div>
          </div>
        </Card>
      ) : (
        /* ------------------------------------------ session / complete -- */
        <>
          <Card padding="md">{jobHeader}</Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card padding="md" className="lg:col-span-1">
              {view === 'complete' && !questionPresented ? (
                /* Reported "completed" before any question was presented: the
                   interview could not go ahead. Neutral - nothing is claimed. */
                <div className="text-center py-4">
                  <span className="mx-auto w-12 h-12 rounded-full bg-stone-100 border border-stone-200 text-stone-500 flex items-center justify-center">
                    <PhoneOff className="w-6 h-6" aria-hidden="true" />
                  </span>
                  <h2 className="mt-3 text-base font-extrabold text-stone-900">{t('aiInterview.ended.title')}</h2>
                  <p className="mt-1.5 text-sm text-stone-600 leading-relaxed">{t('aiInterview.ended.body')}</p>
                </div>
              ) : view === 'complete' ? (
                <div className="text-center py-4">
                  <span className="mx-auto w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center">
                    <CheckCircle2 className="w-6 h-6" aria-hidden="true" />
                  </span>
                  <h2 className="mt-3 text-base font-extrabold text-stone-900">{t('aiInterview.complete.title')}</h2>
                  <p className="mt-1.5 text-sm text-stone-600 leading-relaxed">{t('aiInterview.complete.review')}</p>
                  <p className="mt-1 text-sm text-stone-600 leading-relaxed">{t('aiInterview.complete.body')}</p>
                  {question && question.total > 0 && (
                    <p className="mt-3 text-xs text-stone-500">
                      {t('aiInterview.progress.question', { number: question.total, total: question.total })}
                    </p>
                  )}
                </div>
              ) : (
                <>
                  {/* Whose turn is it? - one panel, one answer. */}
                  <div
                    className={`rounded-xl border p-4 flex items-center gap-3 ${VIEW_STYLE[viewState].panel}`}
                    aria-live="polite"
                  >
                    <span
                      className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${VIEW_STYLE[viewState].icon}`}
                    >
                      {viewState === 'yourTurn' ? (
                        <Mic className="w-5 h-5" aria-hidden="true" />
                      ) : viewState === 'speaking' || viewState === 'ending' ? (
                        <Volume2 className="w-5 h-5" aria-hidden="true" />
                      ) : viewState === 'failed' ? (
                        <AlertTriangle className="w-5 h-5" aria-hidden="true" />
                      ) : viewState === 'stopped' ? (
                        <PhoneOff className="w-5 h-5" aria-hidden="true" />
                      ) : viewState === 'reconnecting' ? (
                        <RefreshCw className="w-5 h-5 animate-spin" aria-hidden="true" />
                      ) : (
                        <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
                      )}
                    </span>
                    <div className="min-w-0">
                      <p className="text-base font-extrabold text-stone-900">{t(`aiInterview.state.${viewState}`)}</p>
                      {viewState === 'failed' ? (
                        error && <p className="text-xs text-red-700 mt-0.5" role="alert">{error}</p>
                      ) : (
                        <p className="text-xs text-stone-500 mt-0.5">{t(`aiInterview.state.${viewState}Hint`)}</p>
                      )}
                    </div>
                  </div>

                  {/* Whose turn? - text marks the current step, not colour alone. */}
                  <ol className="mt-3 grid grid-cols-3 gap-1.5" aria-label={t('aiInterview.turn.label')} data-testid="ai-interview-turn">
                    {(['interviewer', 'you', 'thinking'] as const).map((step) => {
                      const current = turn === step;
                      return (
                        <li
                          key={step}
                          aria-current={current ? 'step' : undefined}
                          className={`rounded-lg border px-2 py-1.5 text-center text-3xs leading-tight ${
                            current ? 'border-brand-400 bg-brand-50 text-stone-900 font-bold' : 'border-stone-200 text-stone-400'
                          }`}
                        >
                          <span className="block">{t(`aiInterview.turn.${step}`)}</span>
                          {current && <span className="block text-brand-700">{t('aiInterview.turn.now')}</span>}
                        </li>
                      );
                    })}
                  </ol>

                  {/* Connection and microphone - from LiveKit and the microphone's real result. */}
                  <div className="mt-3 flex flex-wrap gap-1.5" data-testid="ai-interview-status-pills">
                    {connection && (
                      <Badge variant={connection === 'connected' ? 'neutral' : 'warning'}>
                        <span className="inline-flex items-center gap-1">
                          {connection === 'connected' ? (
                            <Wifi className="w-3 h-3" aria-hidden="true" />
                          ) : (
                            <WifiOff className="w-3 h-3" aria-hidden="true" />
                          )}
                          {t('aiInterview.connection.label')}: {t(`aiInterview.connection.${connection}`)}
                        </span>
                      </Badge>
                    )}
                    {micStatus && (
                      <Badge variant={micStatus === 'active' || micStatus === 'pending' ? 'neutral' : 'warning'}>
                        <span className="inline-flex items-center gap-1">
                          {micStatus === 'active' || micStatus === 'pending' ? (
                            <Mic className="w-3 h-3" aria-hidden="true" />
                          ) : (
                            <MicOff className="w-3 h-3" aria-hidden="true" />
                          )}
                          {t(`aiInterview.mic.status.${micStatus}`)}
                        </span>
                      </Badge>
                    )}
                  </div>

                  {/* Which question? */}
                  {questionShown && (
                    <div className="mt-4">
                      <p className="text-sm font-bold text-stone-800">
                        {t('aiInterview.progress.question', { number: questionNumber, total: question!.total })}
                      </p>
                      <div
                        className="mt-1.5 h-2 rounded-full bg-sand-200 overflow-hidden"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={question!.total}
                        aria-valuenow={questionNumber}
                      >
                        <div
                          className="h-full bg-brand-600 rounded-full transition-[width] duration-300"
                          style={{ width: `${Math.round((questionNumber / question!.total) * 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Is my microphone working? */}
                  {phase !== 'ended' && phase !== 'error' && (
                    <div className="mt-4">
                      <p className="text-xs text-stone-500 mb-1">{t('aiInterview.mic.label')}</p>
                      {/* The level of the track LiveKit is actually publishing
                          (AnalyserNode in startMeter) - not a simulation. */}
                      <div
                        className="h-2 rounded-full bg-sand-200 overflow-hidden"
                        role="meter"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={Math.round(micLevel * 100)}
                        aria-label={t('aiInterview.mic.label')}
                      >
                        <div
                          className="h-full bg-brand-500 transition-[width] duration-75"
                          style={{ width: `${Math.round(micLevel * 100)}%` }}
                        />
                      </div>
                      {live && (
                        <p className="mt-1 text-xs text-stone-500" aria-live="polite">
                          {viewState === 'yourTurn'
                            ? t(localSpeaking ? 'aiInterview.mic.speaking' : 'aiInterview.mic.notSpeaking')
                            : t('aiInterview.mic.hint')}
                        </p>
                      )}
                    </div>
                  )}

                  {/* The local preview of the same video track published to LiveKit. */}
                  {(live || phase === 'connecting') && <div className="mt-4">{cameraPanel}</div>}

                  {error && viewState !== 'failed' && (
                    <p className="mt-4 text-sm text-red-700" role="alert">{error}</p>
                  )}

                  {needsAudioStart && live && (
                    <Button className="mt-4" variant="soft" fullWidth onClick={() => roomRef.current?.startAudio()}>
                      {t('aiInterview.action.enableAudio')}
                    </Button>
                  )}

                  {(live || phase === 'connecting') && (
                    <Button
                      className="mt-5"
                      variant="danger"
                      fullWidth
                      disabled={phase === 'connecting'}
                      leftIcon={<PhoneOff className="w-4 h-4" />}
                      onClick={end}
                    >
                      {t('aiInterview.action.end')}
                    </Button>
                  )}
                </>
              )}

              {/* Starting over is possible, but never the obvious next click -
                  and not at all once the interview is finished (Phase 10: a
                  completed interview cannot be started again). */}
              {(phase === 'ended' || phase === 'error') && !finishedInterview && retryAllowed && !attemptsExhausted && restartControl}
            </Card>

            <Card padding="md" className="lg:col-span-2 flex flex-col min-h-[16rem] lg:min-h-[24rem]">
              <CardHeader title={t('aiInterview.transcript.title')} subtitle={t('aiInterview.transcript.subtitle')} />
              <div className="flex-1 overflow-y-auto space-y-3 max-h-[50vh] lg:max-h-[28rem]">
                {groups.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center text-sm text-stone-500 gap-2 py-10">
                    {phase === 'connecting' && <Spinner />}
                    <p>
                      {phase === 'connecting'
                        ? t('aiInterview.transcript.connecting')
                        : live
                          ? t('aiInterview.transcript.waiting')
                          : t('aiInterview.transcript.none')}
                    </p>
                  </div>
                ) : (
                  groups.map((group) => (
                    <div key={group.key} className={group.speaker === 'you' ? 'flex justify-end' : 'flex justify-start'}>
                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                          group.speaker === 'you' ? 'bg-brand-600 text-white' : 'bg-sand-100 text-stone-800'
                        }`}
                      >
                        <p className="text-[11px] font-semibold opacity-80 mb-0.5">
                          {group.speaker === 'you' ? t('aiInterview.transcript.you') : t('aiInterview.transcript.interviewer')}
                        </p>
                        {/* Spoken words, shown exactly as transcribed - never translated.
                            A segment still being transcribed is dimmed. */}
                        <p dir="auto">
                          {group.lines.map((line, index) => (
                            <span key={line.id} className={line.final ? '' : 'opacity-70'}>
                              {index > 0 ? ' ' : ''}
                              {line.text.trim()}
                            </span>
                          ))}
                        </p>
                      </div>
                    </div>
                  ))
                )}
                <div ref={transcriptEndRef} />
              </div>
            </Card>
          </div>
        </>
      )}

      {/* For support: what the page is actually connected to. Collapsed, and
          not part of the applicant's normal view. */}
      <Modal
        isOpen={languageModalOpen}
        onClose={() => setLanguageModalOpen(false)}
        title={t('aiInterview.language.title')}
        subtitle={t('aiInterview.language.subtitle')}
        footer={
          <>
            <Button variant="ghost" onClick={() => setLanguageModalOpen(false)}>
              {t('aiInterview.language.cancel')}
            </Button>
            <Button
              variant="primary"
              disabled={selectedLanguage === null}
              onClick={confirmLanguageAndStart}
            >
              {t('aiInterview.language.continue')}
            </Button>
          </>
        }
      >
        <label className="block text-sm">
          <span className="text-stone-600">{t('aiInterview.language.label')}</span>
          <select
            className="mt-1 w-full rounded-lg border border-sand-300 bg-white px-3 py-2 text-stone-800"
            value={selectedLanguage ?? ''}
            lang={selectedLanguage ?? undefined}
            dir={selectedLanguage === 'ar' ? 'rtl' : 'ltr'}
            onChange={(event) => {
              const language = event.target.value;
              setSelectedLanguage(language === 'en' || language === 'ar' ? language : null);
            }}
            data-testid="ai-interview-language"
          >
            <option value="">{t('aiInterview.language.choose')}</option>
            <option value="en">{t('aiInterview.language.english')}</option>
            <option value="ar">{t('aiInterview.language.arabic')}</option>
          </select>
        </label>
      </Modal>

      {status && (
        <details className="text-xs text-stone-500">
          <summary className="cursor-pointer select-none w-fit">{t('aiInterview.tech.title')}</summary>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt>{t('aiInterview.tech.connection')}</dt>
            <dd>{t(`aiInterview.phase.${phase}`)}</dd>
            <dt>{t('aiInterview.tech.interviewer')}</dt>
            <dd>
              {agentJoined ? t(`aiInterview.agentState.${agentState ?? 'initializing'}`) : t('aiInterview.agent.absent')}
            </dd>
            <dt>{t('aiInterview.tech.interviewState')}</dt>
            <dd>{interviewState ? t(`aiInterview.interviewState.${interviewState}`) : '—'}</dd>
          </dl>
          <p className="mt-1">{t('aiInterview.tech.models', { ...status.models })}</p>
        </details>
      )}

      {/* The interviewer's audio elements are attached here, invisibly. */}
      <div ref={audioHostRef} className="hidden" aria-hidden="true" />
    </div>
  );
};
