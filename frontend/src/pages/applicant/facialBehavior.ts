export const FACE_LANDMARKER_SAMPLE_INTERVAL_MS = 500;
export const FACIAL_SAMPLE_WINDOW_MS = 5_000;
export const FACIAL_SAMPLE_CAPACITY = 10;
export const FACIAL_MAX_SAMPLE_GAP_MS = 1_500;
// Deadbands are changes in the dimensionless lip-separation / mouth-width ratio.
export const MOUTH_MOTION_ENTER_DEADBAND = 0.04;
export const MOUTH_MOTION_EXIT_DEADBAND = 0.02;
export const FACE_PRESENCE_MIN_CENTER = 0.1;
export const FACE_PRESENCE_MAX_CENTER = 0.9;
// Independent descriptive thresholds; at 2 Hz these elapsed spans are approximate.
export const FACE_PRESENCE_NO_FACE_SUSTAINED_MS = 10_000;
export const FACE_PRESENCE_MULTIPLE_FACES_SUSTAINED_MS = 5_000;
export const FACE_PRESENCE_OUT_OF_FRAME_SUSTAINED_MS = 10_000;

export interface FacialGeometrySample {
  timestampMs: number;
  centerX: number;
  centerY: number;
  yawDeg: number;
  pitchDeg: number;
  rollDeg: number;
}

export interface FacialMotionSummary {
  sampleCount: number;
  startTimestampMs: number;
  endTimestampMs: number;
  elapsedMs: number;
  centerNetDisplacement: number;
  centerPathLength: number;
  yawChangeDeg: number;
  pitchChangeDeg: number;
  rollChangeDeg: number;
  yawPathDeg: number;
  pitchPathDeg: number;
  rollPathDeg: number;
  centerRatePerSecond: number;
  yawRateDegPerSecond: number;
  pitchRateDegPerSecond: number;
  rollRateDegPerSecond: number;
  centerStepStdDev: number;
  yawStepStdDevDeg: number;
  pitchStepStdDevDeg: number;
  rollStepStdDevDeg: number;
}

interface Point3 {
  x: number;
  y: number;
  z: number;
}

interface TransformMatrix {
  rows: number;
  columns: number;
  data: number[];
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isPoint3 = (value: unknown): value is Point3 => {
  if (!isRecord(value)) return false;
  return Number.isFinite(value.x) && Number.isFinite(value.y) && Number.isFinite(value.z);
};

const isTransformMatrix = (value: unknown): value is TransformMatrix => {
  if (!isRecord(value) || value.rows !== 4 || value.columns !== 4 || !Array.isArray(value.data)) {
    return false;
  }
  return value.data.length === 16 && value.data.every(Number.isFinite);
};

const normalize = (x: number, y: number, z: number): Point3 | null => {
  const length = Math.hypot(x, y, z);
  if (!Number.isFinite(length) || length < 1e-8) return null;
  return { x: x / length, y: y / length, z: z / length };
};

const dot = (a: Point3, b: Point3): number => a.x * b.x + a.y * b.y + a.z * b.z;

const radiansToDegrees = (radians: number): number => radians * (180 / Math.PI);

const orientationFromMatrix = (matrix: TransformMatrix): Pick<
  FacialGeometrySample,
  'yawDeg' | 'pitchDeg' | 'rollDeg'
> | null => {
  const { data } = matrix;
  // MediaPipe's transformation matrix is exposed as a flattened column-major 4x4 matrix.
  const xAxis = normalize(data[0], data[1], data[2]);
  const yAxis = normalize(data[4], data[5], data[6]);
  const zAxis = normalize(data[8], data[9], data[10]);
  if (!xAxis || !yAxis || !zAxis) return null;
  if (Math.abs(dot(xAxis, yAxis)) > 0.2
    || Math.abs(dot(xAxis, zAxis)) > 0.2
    || Math.abs(dot(yAxis, zAxis)) > 0.2) return null;
  const handedness = dot({
    x: xAxis.y * yAxis.z - xAxis.z * yAxis.y,
    y: xAxis.z * yAxis.x - xAxis.x * yAxis.z,
    z: xAxis.x * yAxis.y - xAxis.y * yAxis.x,
  }, zAxis);
  if (!Number.isFinite(handedness) || handedness < 0.8) return null;

  const r00 = xAxis.x;
  const r10 = xAxis.y;
  const r20 = xAxis.z;
  const r01 = yAxis.x;
  const r11 = yAxis.y;
  const r21 = yAxis.z;
  const r22 = zAxis.z;
  const yaw = Math.asin(Math.max(-1, Math.min(1, -r20)));
  if (Math.abs(Math.cos(yaw)) < 1e-4) return null;
  const pitch = Math.atan2(r21, r22);
  const roll = Math.atan2(r10, r00);
  if (![yaw, pitch, roll].every(Number.isFinite)) return null;

  return {
    yawDeg: radiansToDegrees(yaw),
    pitchDeg: radiansToDegrees(pitch),
    rollDeg: radiansToDegrees(roll),
  };
};

export const geometrySampleFromResult = (result: unknown, timestampMs: number): FacialGeometrySample | null => {
  if (!Number.isFinite(timestampMs) || timestampMs < 0 || !isRecord(result)) return null;
  const faces = result.faceLandmarks;
  const matrices = result.facialTransformationMatrixes;
  if (!Array.isArray(faces) || faces.length !== 1 || !Array.isArray(matrices) || matrices.length !== 1) return null;

  const landmarks = faces[0];
  if (!Array.isArray(landmarks) || landmarks.length === 0 || !landmarks.every(isPoint3)) return null;
  const matrix = matrices[0];
  if (!isTransformMatrix(matrix)) return null;
  const orientation = orientationFromMatrix(matrix);
  if (!orientation) return null;

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const landmark of landmarks) {
    minX = Math.min(minX, landmark.x);
    maxX = Math.max(maxX, landmark.x);
    minY = Math.min(minY, landmark.y);
    maxY = Math.max(maxY, landmark.y);
  }
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  if (![centerX, centerY].every(Number.isFinite)) return null;

  return { timestampMs, centerX, centerY, ...orientation };
};

export const mouthApertureFromResult = (result: unknown): number | null => {
  if (!isRecord(result) || !Array.isArray(result.faceLandmarks) || result.faceLandmarks.length !== 1) {
    return null;
  }
  const landmarks = result.faceLandmarks[0];
  if (!Array.isArray(landmarks) || landmarks.length <= 291) return null;
  // MediaPipe FaceLandmarker uses the 468-point face mesh: 13/14 are inner
  // upper/lower lip points; 61/291 are the left/right mouth corners.
  const upperLip = landmarks[13];
  const lowerLip = landmarks[14];
  const leftMouthCorner = landmarks[61];
  const rightMouthCorner = landmarks[291];
  if (!isPoint3(upperLip)
    || !isPoint3(lowerLip)
    || !isPoint3(leftMouthCorner)
    || !isPoint3(rightMouthCorner)) return null;

  const mouthWidth = Math.hypot(
    rightMouthCorner.x - leftMouthCorner.x,
    rightMouthCorner.y - leftMouthCorner.y,
  );
  const verticalLipSeparation = Math.abs(lowerLip.y - upperLip.y);
  if (!Number.isFinite(mouthWidth) || mouthWidth < 1e-6
    || !Number.isFinite(verticalLipSeparation)) return null;
  const aperture = verticalLipSeparation / mouthWidth;
  return Number.isFinite(aperture) ? aperture : null;
};

export interface SpeechMouthEpisodeSummary {
  speechActiveDurationMs: number;
  validFaceSampleCountDuringSpeech: number;
  mouthMotionSampleCountDuringSpeech: number | null;
  /** A sampled-observation ratio, not a percentage of continuous speech duration. */
  mouthMotionSampleRatioDuringSpeech: number | null;
}

export type FacePresenceObservation =
  | 'face_present'
  | 'no_face'
  | 'multiple_faces'
  | 'face_position_unavailable'
  | 'out_of_frame'
  | 'unavailable';

export interface SpeechFacePresenceSummary {
  speechActiveDurationMs: number;
  validFaceSampleCountDuringSpeech: number;
  facePresentSampleCountDuringSpeech: number;
  noFaceSampleCountDuringSpeech: number;
  multipleFaceSampleCountDuringSpeech: number;
  outOfFrameSampleCountDuringSpeech: number;
  facePositionUnavailableSampleCountDuringSpeech: number;
  unavailableSampleCountDuringSpeech: number;
  /** Sample-based ratio; it is not continuous visible-speech duration. */
  facePresenceSampleRatioDuringSpeech: number | null;
  sustainedNoFaceEpisodeCount: number;
  sustainedMultipleFacesEpisodeCount: number;
  sustainedOutOfFrameEpisodeCount: number;
}

const centerFromFaceLandmarks = (landmarks: unknown): { x: number; y: number } | null => {
  if (!Array.isArray(landmarks) || landmarks.length === 0) return null;
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const point of landmarks) {
    if (!isRecord(point) || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
    minX = Math.min(minX, point.x as number);
    maxX = Math.max(maxX, point.x as number);
    minY = Math.min(minY, point.y as number);
    maxY = Math.max(maxY, point.y as number);
  }
  const x = (minX + maxX) / 2;
  const y = (minY + maxY) / 2;
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
};

/**
 * Classifies only face count and normalized mesh center. Center-in-frame is
 * approximate; it does not guarantee that the whole face is visible.
 */
export const classifyFacePresence = (result: unknown): FacePresenceObservation => {
  if (!isRecord(result) || !Array.isArray(result.faceLandmarks)) return 'unavailable';
  if (result.faceLandmarks.length === 0) return 'no_face';
  if (result.faceLandmarks.length > 1) return 'multiple_faces';
  const center = centerFromFaceLandmarks(result.faceLandmarks[0]);
  if (!center) return 'face_position_unavailable';
  return center.x >= FACE_PRESENCE_MIN_CENTER && center.x <= FACE_PRESENCE_MAX_CENTER
    && center.y >= FACE_PRESENCE_MIN_CENTER && center.y <= FACE_PRESENCE_MAX_CENTER
    ? 'face_present'
    : 'out_of_frame';
}

/** O(1), episode-local presence counters; no sample history is retained. */
export class SpeechFacePresenceEpisode {
  private speechStartedAtMs: number | null = null;
  private lastSampleTimestampMs: number | null = null;
  private validFaceSampleCount = 0;
  private facePresentSampleCount = 0;
  private noFaceSampleCount = 0;
  private multipleFaceSampleCount = 0;
  private outOfFrameSampleCount = 0;
  private facePositionUnavailableSampleCount = 0;
  private unavailableSampleCount = 0;
  private noFaceStartedAtMs: number | null = null;
  private multipleFacesStartedAtMs: number | null = null;
  private outOfFrameStartedAtMs: number | null = null;
  private sustainedNoFaceEpisodeCount = 0;
  private sustainedMultipleFacesEpisodeCount = 0;
  private sustainedOutOfFrameEpisodeCount = 0;
  private noFaceSustainedRecorded = false;
  private multipleFacesSustainedRecorded = false;
  private outOfFrameSustainedRecorded = false;

  startSpeech(timestampMs: number): void {
    if (!Number.isFinite(timestampMs) || timestampMs < 0) {
      this.reset();
      return;
    }
    if (this.speechStartedAtMs !== null) return;
    this.reset();
    this.speechStartedAtMs = timestampMs;
  }

  addObservation(timestampMs: number, result: unknown): FacePresenceObservation {
    const state = classifyFacePresence(result);
    if (this.speechStartedAtMs === null) return state;
    if (Number.isFinite(timestampMs) && timestampMs >= 0 && timestampMs < this.speechStartedAtMs) {
      return state;
    }
    if (!Number.isFinite(timestampMs) || timestampMs < 0
      || (this.lastSampleTimestampMs !== null && timestampMs <= this.lastSampleTimestampMs)) {
      this.unavailableSampleCount += 1;
      this.resetSustainedContinuity();
      return 'unavailable';
    }

    const gapMs = this.lastSampleTimestampMs === null ? null : timestampMs - this.lastSampleTimestampMs;
    if (gapMs !== null && gapMs > FACIAL_MAX_SAMPLE_GAP_MS) this.resetSustainedContinuity();
    this.lastSampleTimestampMs = timestampMs;

    if (state === 'unavailable') {
      this.unavailableSampleCount += 1;
      this.resetSustainedContinuity();
      return state;
    }

    this.validFaceSampleCount += 1;
    if (state === 'face_present') this.facePresentSampleCount += 1;
    else if (state === 'no_face') this.noFaceSampleCount += 1;
    else if (state === 'multiple_faces') this.multipleFaceSampleCount += 1;
    else if (state === 'out_of_frame') this.outOfFrameSampleCount += 1;
    else this.facePositionUnavailableSampleCount += 1;
    this.updateSustainedState(state, timestampMs);
    return state;
  }

  endSpeech(timestampMs: number): SpeechFacePresenceSummary | null {
    const startedAt = this.speechStartedAtMs;
    if (startedAt === null) return null;
    if (!Number.isFinite(timestampMs) || timestampMs <= startedAt
      || (this.lastSampleTimestampMs !== null && timestampMs < this.lastSampleTimestampMs)) {
      this.reset();
      return null;
    }

    const classifiableSampleCount = this.facePresentSampleCount + this.noFaceSampleCount
      + this.multipleFaceSampleCount + this.outOfFrameSampleCount;
    const summary: SpeechFacePresenceSummary = {
      speechActiveDurationMs: timestampMs - startedAt,
      validFaceSampleCountDuringSpeech: this.validFaceSampleCount,
      facePresentSampleCountDuringSpeech: this.facePresentSampleCount,
      noFaceSampleCountDuringSpeech: this.noFaceSampleCount,
      multipleFaceSampleCountDuringSpeech: this.multipleFaceSampleCount,
      outOfFrameSampleCountDuringSpeech: this.outOfFrameSampleCount,
      facePositionUnavailableSampleCountDuringSpeech: this.facePositionUnavailableSampleCount,
      unavailableSampleCountDuringSpeech: this.unavailableSampleCount,
      facePresenceSampleRatioDuringSpeech: classifiableSampleCount > 0
        ? this.facePresentSampleCount / classifiableSampleCount
        : null,
      sustainedNoFaceEpisodeCount: this.sustainedNoFaceEpisodeCount,
      sustainedMultipleFacesEpisodeCount: this.sustainedMultipleFacesEpisodeCount,
      sustainedOutOfFrameEpisodeCount: this.sustainedOutOfFrameEpisodeCount,
    };
    this.reset();
    return summary;
  }

  reset(): void {
    this.speechStartedAtMs = null;
    this.lastSampleTimestampMs = null;
    this.validFaceSampleCount = 0;
    this.facePresentSampleCount = 0;
    this.noFaceSampleCount = 0;
    this.multipleFaceSampleCount = 0;
    this.outOfFrameSampleCount = 0;
    this.facePositionUnavailableSampleCount = 0;
    this.unavailableSampleCount = 0;
    this.sustainedNoFaceEpisodeCount = 0;
    this.sustainedMultipleFacesEpisodeCount = 0;
    this.sustainedOutOfFrameEpisodeCount = 0;
    this.resetSustainedContinuity();
  }

  private updateSustainedState(state: FacePresenceObservation, timestampMs: number): void {
    if (state !== 'no_face') {
      this.noFaceStartedAtMs = null;
      this.noFaceSustainedRecorded = false;
    } else if (this.noFaceStartedAtMs === null) {
      this.noFaceStartedAtMs = timestampMs;
    } else if (!this.noFaceSustainedRecorded
      && timestampMs - this.noFaceStartedAtMs >= FACE_PRESENCE_NO_FACE_SUSTAINED_MS) {
      this.noFaceSustainedRecorded = true;
      this.sustainedNoFaceEpisodeCount += 1;
    }

    if (state !== 'multiple_faces') {
      this.multipleFacesStartedAtMs = null;
      this.multipleFacesSustainedRecorded = false;
    } else if (this.multipleFacesStartedAtMs === null) {
      this.multipleFacesStartedAtMs = timestampMs;
    } else if (!this.multipleFacesSustainedRecorded
      && timestampMs - this.multipleFacesStartedAtMs >= FACE_PRESENCE_MULTIPLE_FACES_SUSTAINED_MS) {
      this.multipleFacesSustainedRecorded = true;
      this.sustainedMultipleFacesEpisodeCount += 1;
    }

    if (state !== 'out_of_frame') {
      this.outOfFrameStartedAtMs = null;
      this.outOfFrameSustainedRecorded = false;
    } else if (this.outOfFrameStartedAtMs === null) {
      this.outOfFrameStartedAtMs = timestampMs;
    } else if (!this.outOfFrameSustainedRecorded
      && timestampMs - this.outOfFrameStartedAtMs >= FACE_PRESENCE_OUT_OF_FRAME_SUSTAINED_MS) {
      this.outOfFrameSustainedRecorded = true;
      this.sustainedOutOfFrameEpisodeCount += 1;
    }
  }

  private resetSustainedContinuity(): void {
    this.noFaceStartedAtMs = null;
    this.multipleFacesStartedAtMs = null;
    this.outOfFrameStartedAtMs = null;
    this.noFaceSustainedRecorded = false;
    this.multipleFacesSustainedRecorded = false;
    this.outOfFrameSustainedRecorded = false;
  }
}

/** Scalar-only, episode-scoped mouth-motion co-occurrence; no sample history is retained. */
export class SpeechMouthEpisode {
  private speechStartedAtMs: number | null = null;
  private previousSampleTimestampMs: number | null = null;
  private previousAperture: number | null = null;
  private motionActive = false;
  private validFaceSampleCount = 0;
  private mouthMotionSampleCount = 0;

  startSpeech(timestampMs: number): void {
    if (!Number.isFinite(timestampMs) || timestampMs < 0) {
      this.reset();
      return;
    }
    if (this.speechStartedAtMs !== null) return;
    this.reset();
    this.speechStartedAtMs = timestampMs;
  }

  addFaceSample(timestampMs: number, aperture: number | null): void {
    if (this.speechStartedAtMs === null) return;
    if (!Number.isFinite(timestampMs) || timestampMs < this.speechStartedAtMs
      || (this.previousSampleTimestampMs !== null
        && timestampMs <= this.previousSampleTimestampMs)) {
      this.resetContinuity();
      return;
    }
    if (aperture === null || !Number.isFinite(aperture) || aperture < 0) {
      this.resetContinuity();
      return;
    }

    const gapMs = this.previousSampleTimestampMs === null
      ? null
      : timestampMs - this.previousSampleTimestampMs;
    if (gapMs !== null && gapMs > FACIAL_MAX_SAMPLE_GAP_MS) this.resetContinuity();

    this.validFaceSampleCount += 1;
    if (this.previousAperture !== null) {
      const apertureChange = Math.abs(aperture - this.previousAperture);
      if (this.motionActive) {
        this.motionActive = apertureChange > MOUTH_MOTION_EXIT_DEADBAND;
      } else if (apertureChange >= MOUTH_MOTION_ENTER_DEADBAND) {
        this.motionActive = true;
      }
      if (this.motionActive) this.mouthMotionSampleCount += 1;
    }
    this.previousSampleTimestampMs = timestampMs;
    this.previousAperture = aperture;
  }

  endSpeech(timestampMs: number): SpeechMouthEpisodeSummary | null {
    const startedAt = this.speechStartedAtMs;
    if (startedAt === null) return null;
    if (!Number.isFinite(timestampMs) || timestampMs <= startedAt
      || (this.previousSampleTimestampMs !== null && timestampMs <= this.previousSampleTimestampMs)) {
      this.reset();
      return null;
    }

    const validFaceSampleCountDuringSpeech = this.validFaceSampleCount;
    const summary: SpeechMouthEpisodeSummary = {
      speechActiveDurationMs: timestampMs - startedAt,
      validFaceSampleCountDuringSpeech,
      mouthMotionSampleCountDuringSpeech: validFaceSampleCountDuringSpeech > 0
        ? this.mouthMotionSampleCount
        : null,
      mouthMotionSampleRatioDuringSpeech: validFaceSampleCountDuringSpeech > 0
        ? this.mouthMotionSampleCount / validFaceSampleCountDuringSpeech
        : null,
    };
    this.reset();
    return summary;
  }

  reset(): void {
    this.speechStartedAtMs = null;
    this.validFaceSampleCount = 0;
    this.mouthMotionSampleCount = 0;
    this.resetContinuity();
  }

  private resetContinuity(): void {
    this.previousSampleTimestampMs = null;
    this.previousAperture = null;
    this.motionActive = false;
  }
}

const angularDelta = (fromDeg: number, toDeg: number): number =>
  ((toDeg - fromDeg + 540) % 360) - 180;

const standardDeviation = (values: number[]): number => {
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
};

const latestContiguousRun = (samples: readonly unknown[]): FacialGeometrySample[] => {
  const run: FacialGeometrySample[] = [];
  let previousTimestamp: number | null = null;
  for (const candidate of samples) {
    if (!isValidFacialGeometrySample(candidate)
      || (previousTimestamp !== null
        && (candidate.timestampMs <= previousTimestamp
          || candidate.timestampMs - previousTimestamp > FACIAL_MAX_SAMPLE_GAP_MS))) {
      run.length = 0;
      previousTimestamp = null;
      if (!isValidFacialGeometrySample(candidate)) continue;
    }
    run.push(candidate);
    previousTimestamp = candidate.timestampMs;
  }
  return run;
};

/**
 * Summarizes only the newest contiguous run. Fewer than two usable samples
 * yields null rather than implying zero movement.
 */
export const summarizeFacialMotion = (samples: readonly unknown[]): FacialMotionSummary | null => {
  const run = latestContiguousRun(samples);
  if (run.length < 2) return null;

  const first = run[0];
  const last = run[run.length - 1];
  const elapsedMs = last.timestampMs - first.timestampMs;
  if (!Number.isFinite(elapsedMs) || elapsedMs <= 0) return null;

  const centerSteps: number[] = [];
  const yawSteps: number[] = [];
  const pitchSteps: number[] = [];
  const rollSteps: number[] = [];
  let centerPathLength = 0;
  let yawPathDeg = 0;
  let pitchPathDeg = 0;
  let rollPathDeg = 0;
  for (let index = 1; index < run.length; index += 1) {
    const previous = run[index - 1];
    const current = run[index];
    const centerStep = Math.hypot(current.centerX - previous.centerX, current.centerY - previous.centerY);
    const yawStep = angularDelta(previous.yawDeg, current.yawDeg);
    const pitchStep = angularDelta(previous.pitchDeg, current.pitchDeg);
    const rollStep = angularDelta(previous.rollDeg, current.rollDeg);
    centerSteps.push(centerStep);
    yawSteps.push(Math.abs(yawStep));
    pitchSteps.push(Math.abs(pitchStep));
    rollSteps.push(Math.abs(rollStep));
    centerPathLength += centerStep;
    yawPathDeg += Math.abs(yawStep);
    pitchPathDeg += Math.abs(pitchStep);
    rollPathDeg += Math.abs(rollStep);
  }

  const seconds = elapsedMs / 1_000;
  return {
    sampleCount: run.length,
    startTimestampMs: first.timestampMs,
    endTimestampMs: last.timestampMs,
    elapsedMs,
    centerNetDisplacement: Math.hypot(last.centerX - first.centerX, last.centerY - first.centerY),
    centerPathLength,
    yawChangeDeg: angularDelta(first.yawDeg, last.yawDeg),
    pitchChangeDeg: angularDelta(first.pitchDeg, last.pitchDeg),
    rollChangeDeg: angularDelta(first.rollDeg, last.rollDeg),
    yawPathDeg,
    pitchPathDeg,
    rollPathDeg,
    centerRatePerSecond: centerPathLength / seconds,
    yawRateDegPerSecond: yawPathDeg / seconds,
    pitchRateDegPerSecond: pitchPathDeg / seconds,
    rollRateDegPerSecond: rollPathDeg / seconds,
    centerStepStdDev: standardDeviation(centerSteps),
    yawStepStdDevDeg: standardDeviation(yawSteps),
    pitchStepStdDevDeg: standardDeviation(pitchSteps),
    rollStepStdDevDeg: standardDeviation(rollSteps),
  };
};

export class FacialSampleBuffer {
  private samples: FacialGeometrySample[] = [];

  add(sample: FacialGeometrySample): void {
    if (!isValidFacialGeometrySample(sample)) return;
    this.samples.push({ ...sample });
    this.prune(sample.timestampMs);
  }

  values(): FacialGeometrySample[] {
    return this.samples.map((sample) => ({ ...sample }));
  }

  clear(): void {
    this.samples = [];
  }

  private prune(nowMs: number): void {
    const oldestAllowed = nowMs - FACIAL_SAMPLE_WINDOW_MS;
    this.samples = this.samples.filter((sample) => sample.timestampMs >= oldestAllowed);
    if (this.samples.length > FACIAL_SAMPLE_CAPACITY) {
      this.samples.splice(0, this.samples.length - FACIAL_SAMPLE_CAPACITY);
    }
  }
}

export const isValidFacialGeometrySample = (value: unknown): value is FacialGeometrySample => {
  if (!isRecord(value)) return false;
  const expected = ['timestampMs', 'centerX', 'centerY', 'yawDeg', 'pitchDeg', 'rollDeg'];
  const keys = Object.keys(value);
  return keys.length === expected.length
    && expected.every((key) => Object.hasOwn(value, key) && Number.isFinite(value[key]));
};
