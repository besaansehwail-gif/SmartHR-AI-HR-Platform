/**
 * Stage 2 — local face-count helpers (no React, no browser, no audio).
 *
 * Legacy barrel: the pure helpers live in `aiInterviewRules.ts` beside the
 * other page rules so checks and the page share one implementation. This
 * module re-exports them for the older import path.
 */

export type { FaceCount } from './aiInterviewRules';
export {
  CAMERA_PROCTORING_KEYS,
  CAMERA_PROCTORING_TOPIC,
  CAMERA_PROCTORING_TYPE,
  FACE_SAMPLE_INTERVAL_MS,
  MULTIPLE_FACES_SUSTAINED_MS,
  NO_FACE_SUSTAINED_MS,
  buildCameraProctoringPayload,
  faceCountOf,
  formatFaceLog,
  formatProctorFlagLog,
  initialProctorTimers,
  isProctorFlag,
  isValidCameraProctoringPayload,
  serializeCameraProctoringPayload,
  updateProctorState,
} from './aiInterviewRules';
export type { CameraProctoringPayload, ProctorFlag, ProctorState, ProctorTimers } from './aiInterviewRules';

