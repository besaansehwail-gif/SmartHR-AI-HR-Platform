/**
 * AI Interview page rules (Phase 10), kept free of React and of the browser so
 * `scripts/check-ai-interview-ux.ts` can run them in Node.
 *
 * The backend is the boundary - these only decide what the page SHOWS: whether
 * Start is offered, and which translated sentence explains a refusal.
 */
import type { AiInterviewListing } from '../../types';

/** Where "now" is relative to the interview's start window. */
export type StartWindow = 'open' | 'early' | 'late' | 'unknown';

/**
 * `opens_at` / `closes_at` come from the backend's own window rule and are
 * local wall-clock times (no zone), parsed as local time like `scheduled_at`.
 * Inclusive at both ends, as the backend is. Unknown (no times) leaves the
 * decision to the backend.
 */
export const startWindow = (listing: AiInterviewListing | null, nowMs: number): StartWindow => {
  if (!listing?.opens_at || !listing?.closes_at) return 'unknown';
  const opens = new Date(listing.opens_at).getTime();
  const closes = new Date(listing.closes_at).getTime();
  if (Number.isNaN(opens) || Number.isNaN(closes)) return 'unknown';
  if (nowMs < opens) return 'early';
  if (nowMs > closes) return 'late';
  return 'open';
};

/**
 * Backend refusal codes the page translates, as `aiInterview.errorCode.<code>`.
 * `session_active` is the concurrent-session refusal; `attempt_finished` comes
 * from the agent's side and is listed so a page that ever receives it can say
 * so. Anything else falls back to the backend's own `detail`.
 */
export const START_ERROR_CODES = [
  'too_early',
  'too_late',
  'attempts_exhausted',
  'attempt_finished',
  'session_active',
  'completed',
  'not_approved',
  'not_found',
  'not_configured',
] as const;

export type StartErrorCode = (typeof START_ERROR_CODES)[number];

export const startErrorKey = (code: string | null | undefined): string | null =>
  code && (START_ERROR_CODES as readonly string[]).includes(code) ? `aiInterview.errorCode.${code}` : null;

/**
 * Refusals after which pressing Start again cannot succeed - the backend has
 * said so (Phase 9/10). The page hides "Try again" for these rather than
 * offering a button the backend would refuse; it decides nothing itself.
 */
export const FINAL_START_ERRORS = ['attempts_exhausted', 'completed', 'too_late', 'not_approved', 'not_found'] as const;

export const startRetryAllowed = (code: string | null | undefined): boolean =>
  !code || !(FINAL_START_ERRORS as readonly string[]).includes(code);

// --- Phase 11.6.1: voice UX states, each from a real source ---------------------------

/** The page's own session phase (what `start()` / LiveKit events set). */
export type Phase = 'idle' | 'connecting' | 'connected' | 'ended' | 'error';
/** LiveKit's `lk.agent.state` attribute, published by livekit-agents. */
export type AgentState = 'initializing' | 'idle' | 'listening' | 'thinking' | 'speaking';
export const AGENT_STATES: AgentState[] = ['initializing', 'idle', 'listening', 'thinking', 'speaking'];
/** SmartHR's `smarthr.interview.state`, published by the interview controller
 *  (app/ai/interview/state.py) - the interview's own state machine. */
export const INTERVIEW_STATES = [
  'waiting', 'intro', 'asking', 'listening', 'processing', 'follow_up_decision', 'adaptive_selection', 'speaking',
  'ending', 'completed',
] as const;
export type InterviewState = (typeof INTERVIEW_STATES)[number];

/** LiveKit's room connection state (livekit-client `ConnectionState`), folded. */
export type Connection = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

export const connectionOf = (state: string): Connection => {
  switch (state) {
    case 'connecting':
      return 'connecting';
    case 'connected':
      return 'connected';
    case 'reconnecting':
    case 'signalReconnecting':
      return 'reconnecting';
    default:
      return 'disconnected';
  }
};

/** The microphone as `setMicrophoneEnabled` / LiveKit's MediaDevicesError left it. */
export type MicStatus = 'pending' | 'active' | 'denied' | 'unavailable' | 'error';
export type MicFailure = 'denied' | 'unavailable' | 'error';

/** A getUserMedia failure, by the DOMException name the browser gives it -
 *  never shown as text; only used to choose the right instruction. */
export const micFailureOf = (err: unknown): MicFailure => {
  const name = (err as { name?: string } | null)?.name ?? '';
  if (['NotAllowedError', 'PermissionDeniedError', 'SecurityError'].includes(name)) return 'denied';
  if (['NotFoundError', 'DevicesNotFoundError', 'OverconstrainedError'].includes(name)) return 'unavailable';
  return 'error';
};

/** The one state the applicant is shown. */
export type ViewState =
  | 'connecting' | 'waiting' | 'reconnecting' | 'speaking' | 'yourTurn' | 'thinking' | 'ending' | 'stopped' | 'failed';

/**
 * Folds the real sources into what the applicant needs to know, in order of
 * authority: the page's phase, LiveKit's connection state, whether the
 * interviewer is in the room, the interview controller's state (preferred),
 * and LiveKit's agent state (fallback). Nothing here is invented: an input
 * that says nothing leaves the applicant at "waiting".
 */
export const viewStateOf = (
  phase: Phase,
  connection: Connection | null,
  agentJoined: boolean,
  interviewState: InterviewState | null,
  agentState: AgentState | null,
): ViewState => {
  if (phase === 'error') return 'failed';
  if (phase === 'ended') return 'stopped';
  if (phase === 'connecting') return 'connecting';
  if (connection === 'reconnecting') return 'reconnecting';
  if (!agentJoined) return 'waiting';

  switch (interviewState) {
    case 'intro':
    case 'asking':
    case 'speaking':
      return 'speaking';
    case 'ending':
    case 'completed':
      return 'ending';
    case 'listening':
      return 'yourTurn';
    case 'processing':
    case 'follow_up_decision': // Phase 11.1: deciding whether to ask a follow-up
    case 'adaptive_selection': // Phase 11.2: choosing the next bank question
      return 'thinking';
    case 'waiting':
      return 'waiting';
    default:
      break;
  }
  switch (agentState) {
    case 'speaking':
      return 'speaking';
    case 'listening':
      return 'yourTurn';
    case 'thinking':
      return 'thinking';
    default:
      return 'waiting';
  }
};

/** Every value of each type above - for the checks, which translate them all. */
export const VIEW_STATES: ViewState[] = [
  'connecting', 'waiting', 'reconnecting', 'speaking', 'yourTurn', 'thinking', 'ending', 'stopped', 'failed',
];
export const CONNECTIONS: Connection[] = ['connecting', 'connected', 'reconnecting', 'disconnected'];
export const MIC_STATUSES: MicStatus[] = ['pending', 'active', 'denied', 'unavailable', 'error'];
export const TURN_STEPS = ['interviewer', 'you', 'thinking'] as const;

/** Which part of the turn indicator a view lights up - or none. */
export const turnOf = (view: ViewState): 'interviewer' | 'you' | 'thinking' | null =>
  view === 'speaking' || view === 'ending' ? 'interviewer' : view === 'yourTurn' ? 'you' : view === 'thinking' ? 'thinking' : null;

// --- Stage 2: local face count (camera only, never audio) ---------------------
//
// Pure helpers kept beside the other page rules so
// `scripts/check-ai-interview-face.ts` can run them in Node. The page shows
// and logs ONLY 0 | 1 | 2 (2 means "2+") - never boxes, landmarks, gaze,
// emotion or identity, and never any pixel/frame data.

/** The only face value the page ever shows or logs (2 means "2+"). */
export type FaceCount = 0 | 1 | 2;

/** Raw MediaPipe `detections.length` -> shown/logged face_count (2 means 2+). */
export const faceCountOf = (detections: number): FaceCount => {
  if (!Number.isFinite(detections) || detections <= 0) return 0;
  if (detections === 1) return 1;
  return 2;
};

/**
 * The only Stage 2 console record. `timestamp` is an ISO string supplied by
 * the caller so this stays pure; `face_count` is 0 | 1 | 2 (2 = "2+").
 */
export const formatFaceLog = (timestamp: string, faceCount: FaceCount): string =>
  JSON.stringify({ timestamp, face_count: faceCount });

/** Sampling cadence: ~1 sample every 1.5s (inside the required 1–2s band). */
export const FACE_SAMPLE_INTERVAL_MS = 1500;

// --- Stage 3: face-count proctoring aggregation (camera only, never audio) --
//
// A tiny state machine fed with the Stage 2 `face_count` values on the SAME
// ~1.5s sampling loop - no second timer, no detector change. A flag fires only
// when ONE condition holds CONTINUOUSLY for its whole duration; any normal
// sample resets that condition's timer immediately, and separate abnormal
// periods never accumulate. Flags are metadata only: `{ timestamp, face_count,
// flag }` - never pixels, never sent anywhere, never touching the interview.

/** The only Stage 3 flags. `null` (in state) means normal - no flag. */
export type ProctorFlag = 'no_face_sustained' | 'multiple_faces_sustained';

/** The sustained-condition state shown under the preview (metadata only). */
export type ProctorState = 'normal' | 'no_face' | 'multiple_faces' | ProctorFlag;

/** Conservative defaults: ~10s of "0", ~5s of "2+" (2 means "2+"). */
export const NO_FACE_SUSTAINED_MS = 10_000;
export const MULTIPLE_FACES_SUSTAINED_MS = 5_000;

/**
 * Mutable per-condition stopwatch. Kept in a plain object (not React state)
 * so samples update it without re-rendering; the page mirrors only the
 * display state. `startedAtMs` is `null` while the condition is not running.
 */
export interface ProctorTimers {
  noFaceStartedAtMs: number | null;
  multipleFacesStartedAtMs: number | null;
}

export const initialProctorTimers = (): ProctorTimers => ({
  noFaceStartedAtMs: null,
  multipleFacesStartedAtMs: null,
});

/**
 * Feed one Stage 2 `face_count` sample. Returns the display state:
 * - `1`                 -> `normal` (both timers reset immediately).
 * - `0` below 10s       -> `no_face`; at/after 10s continuous -> `no_face_sustained`.
 * - `2` below 5s        -> `multiple_faces`; at/after 5s continuous -> `multiple_faces_sustained`.
 * - the OTHER condition's timer always resets on the same sample.
 *
 * `nowMs` is injected so tests are deterministic; the page passes `Date.now()`.
 */
export const updateProctorState = (
  timers: ProctorTimers,
  faceCount: FaceCount,
  nowMs: number,
  noFaceMs: number = NO_FACE_SUSTAINED_MS,
  multipleFacesMs: number = MULTIPLE_FACES_SUSTAINED_MS,
): ProctorState => {
  if (faceCount === 1) {
    timers.noFaceStartedAtMs = null;
    timers.multipleFacesStartedAtMs = null;
    return 'normal';
  }
  if (faceCount === 0) {
    timers.multipleFacesStartedAtMs = null;
    if (timers.noFaceStartedAtMs === null) timers.noFaceStartedAtMs = nowMs;
    return nowMs - timers.noFaceStartedAtMs >= noFaceMs ? 'no_face_sustained' : 'no_face';
  }
  timers.noFaceStartedAtMs = null;
  if (timers.multipleFacesStartedAtMs === null) timers.multipleFacesStartedAtMs = nowMs;
  return nowMs - timers.multipleFacesStartedAtMs >= multipleFacesMs ? 'multiple_faces_sustained' : 'multiple_faces';
};

/** True only for the two sustained flags (the moments a flag record is logged). */
export const isProctorFlag = (state: ProctorState): state is ProctorFlag =>
  state === 'no_face_sustained' || state === 'multiple_faces_sustained';

/**
 * The only Stage 3 console record - metadata only: `{ timestamp, face_count,
 * flag }`. Never pixels, frames, canvas, base64, blobs or screenshots.
 */
export const formatProctorFlagLog = (timestamp: string, faceCount: FaceCount, flag: ProctorFlag): string =>
  JSON.stringify({ timestamp, face_count: faceCount, flag });

// --- Stage 4: metadata-only proctoring payload (camera only, never audio) ---
//
// Pure shape + validator for the future publish path. Stage 4 does NOT wire
// `publishData()` and does NOT change token permissions: the applicant token
// is minted with `can_publish_data=False`
// (`app/services/ai_interview_service.py:87`), asserted by
// `scripts/test_ai_interview_foundation.py:234`, so any `publishData()` call
// today would be refused by LiveKit itself. What Stage 4 adds is the exact
// payload the (gated, future) publisher may send - and nothing else - so it
// can be unit-tested independently from React, the room, and the backend.
//
// Approved schema (ONLY these four keys, all primitives):
//   { type: 'camera_proctoring', timestamp: ISO-string, face_count: 0|1|2,
//     flag: 'no_face_sustained' | 'multiple_faces_sustained' | null }
// `face_count: 2` means "2+". No detector objects, no video/track elements,
// no pixels, frames, canvas, blobs, ArrayBuffers, base64 or screenshots.

/** LiveKit data topic reserved for the future camera-proctoring publisher. */
export const CAMERA_PROCTORING_TOPIC = 'smarthr.camera.proctoring';

/** The topic tag carried inside the payload so a receiver can route it. */
export const CAMERA_PROCTORING_TYPE = 'camera_proctoring' as const;

/** The only payload Stage 4 may ever publish (metadata primitives only). */
export interface CameraProctoringPayload {
  type: typeof CAMERA_PROCTORING_TYPE;
  timestamp: string;
  face_count: FaceCount;
  flag: ProctorFlag | null;
}

/** The exact key set a payload may carry - nothing more. */
export const CAMERA_PROCTORING_KEYS = ['type', 'timestamp', 'face_count', 'flag'] as const;

/**
 * Build the publish payload from existing Stage 2/3 values. Pure: callers
 * pass the ISO timestamp (page uses `new Date().toISOString()`).
 */
export const buildCameraProctoringPayload = (
  timestamp: string,
  faceCount: FaceCount,
  flag: ProctorFlag | null,
): CameraProctoringPayload => ({
  type: CAMERA_PROCTORING_TYPE,
  timestamp,
  face_count: faceCount,
  flag,
});

/**
 * Strict gate the (future) publisher must pass BEFORE any send. Returns true
 * only when `value` is a plain object with EXACTLY the four approved keys,
 * `type === 'camera_proctoring'`, `timestamp` a non-empty string,
 * `face_count` one of 0|1|2, and `flag` null or one of the two sustained
 * flags. Anything else - wrong types, out-of-range counts, unknown flags,
 * extra keys, arrays, MediaPipe/detector objects, MediaStream/track/canvas/
 * ImageData/Blob/ArrayBuffer/base64 smuggling - is rejected.
 */
export const isValidCameraProctoringPayload = (value: unknown): value is CameraProctoringPayload => {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length !== CAMERA_PROCTORING_KEYS.length) return false;
  for (const key of CAMERA_PROCTORING_KEYS) {
    if (!(key in record)) return false;
  }
  if (record.type !== CAMERA_PROCTORING_TYPE) return false;
  if (typeof record.timestamp !== 'string' || record.timestamp.length === 0) return false;
  if (record.face_count !== 0 && record.face_count !== 1 && record.face_count !== 2) return false;
  const flag = record.flag;
  if (flag !== null && flag !== 'no_face_sustained' && flag !== 'multiple_faces_sustained') return false;
  return true;
};

/**
 * Serialize a payload for the future `publishData()` call. Returns the JSON
 * string only when the payload passes `isValidCameraProctoringPayload`;
 * otherwise returns null and nothing may be sent. Keeps logging/sending to
 * the validated metadata string - never the raw object graph.
 */
export const serializeCameraProctoringPayload = (payload: CameraProctoringPayload): string | null =>
  isValidCameraProctoringPayload(payload) ? JSON.stringify(payload) : null;
