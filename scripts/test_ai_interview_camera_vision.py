"""Offline Stage 5 tests: sampled LiveKit camera frame -> GPT-4o context.

No room is connected and no model is called.  The VideoStream is replaced with
an in-memory fake, so this test exercises only selection, bounded retention,
attachment construction, and cleanup.
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from livekit import rtc

from app.ai.interview import diagnostics as diag
from app.ai.interview import agent as interview_agent


class Checks:
    def __init__(self):
        self.failed = 0

    def check(self, label, ok):
        print(("PASS" if ok else "FAIL") + ": " + label)
        self.failed += not ok


class Emitter:
    def __init__(self, participants=None):
        self.handlers = {}
        self.remote_participants = participants or {}

    def on(self, event, callback):
        self.handlers.setdefault(event, []).append(callback)

    def off(self, event, callback):
        self.handlers.get(event, []).remove(callback)

    def fire(self, event, *args):
        for callback in list(self.handlers.get(event, [])):
            callback(*args)


class FakeVideoStream:
    created = []

    def __init__(self, track):
        self.track = track
        self.frames = []
        self.closed = False
        FakeVideoStream.created.append(self)

    def __aiter__(self):
        return self._frames()

    async def _frames(self):
        for frame in self.frames:
            yield SimpleNamespace(frame=frame)

    async def aclose(self):
        self.closed = True


def camera_track(sid="camera-1"):
    track = SimpleNamespace(kind=rtc.TrackKind.KIND_VIDEO)
    publication = SimpleNamespace(
        track=track, sid=sid, source=rtc.TrackSource.SOURCE_CAMERA,
        name="ai-interview-camera",
    )
    applicant = SimpleNamespace(identity="applicant-safe-id", track_publications={sid: publication})
    return track, publication, applicant


async def run(check):
    original_stream = interview_agent.rtc.VideoStream
    interview_agent.rtc.VideoStream = FakeVideoStream
    try:
        # Default-off path never subscribes, retains a frame, or constructs ImageContent.
        initial_stream_count = len(FakeVideoStream.created)
        track, publication, applicant = camera_track("camera-default-off")
        disabled_room = Emitter({applicant.identity: applicant})
        disabled_reader = interview_agent.CameraFrameInput("smarthr-ai-interview-camera-disabled")
        disabled_reader.start(disabled_room, applicant.identity)
        disabled_room.fire("track_subscribed", track, publication, applicant)
        check("Stage 5 reader is disabled by default", disabled_reader.enabled is False)
        check("default-off reader does not subscribe or create a VideoStream",
              len(FakeVideoStream.created) == initial_stream_count
              and not disabled_room.handlers)
        disabled_reader._latest_frame = rtc.VideoFrame(
            width=1, height=1, type=rtc.VideoBufferType.RGBA, data=bytearray(4))
        check("disabled path discards any frame and constructs no ImageContent",
              disabled_reader.take_latest_image() is None and disabled_reader._latest_frame is None)
        await disabled_reader.aclose()

        # An already-present named camera track is selected when the reader starts.
        track, publication, applicant = camera_track()
        room = Emitter({applicant.identity: applicant})
        reader = interview_agent.CameraFrameInput("smarthr-ai-interview-camera-test", enabled=True)
        reader.start(room, applicant.identity)
        check("already-present linked applicant camera is selected", len(FakeVideoStream.created) == 1)

        # Later events for an unrelated participant, wrong source, or wrong name are ignored.
        unrelated = SimpleNamespace(identity="applicant-other")
        room.fire("track_subscribed", track, publication, unrelated)
        wrong_name = SimpleNamespace(track=track, sid="camera-2", source=rtc.TrackSource.SOURCE_CAMERA,
                                     name="other-camera")
        room.fire("track_subscribed", track, wrong_name, applicant)
        screen = SimpleNamespace(track=track, sid="camera-3", source=rtc.TrackSource.SOURCE_SCREENSHARE,
                                 name="ai-interview-camera")
        room.fire("track_subscribed", track, screen, applicant)
        check("unrelated, non-camera, and wrong-name video tracks are ignored", len(FakeVideoStream.created) == 1)

        # Repeated notification for the same publication cannot create a second reader.
        room.fire("track_subscribed", track, publication, applicant)
        check("duplicate subscription does not create duplicate VideoStream", len(FakeVideoStream.created) == 1)

        # The one slot replaces older frames and consumes only one image.
        old = rtc.VideoFrame(width=1, height=1, type=rtc.VideoBufferType.RGBA, data=bytearray(4))
        latest = rtc.VideoFrame(width=1, height=1, type=rtc.VideoBufferType.RGBA, data=bytearray(4))
        reader._latest_frame = old
        reader._latest_frame = latest
        image = reader.take_latest_image()
        check("latest-frame storage is one bounded replacement slot", image is not None and image.image is latest)
        check("taking one image clears the retained frame", reader.take_latest_image() is None)
        check("ImageContent uses bounded inference dimensions", image is not None and image.inference_width == 512
              and image.inference_height == 288 and image.inference_detail == "low")
        reader._latest_frame = object()
        check("image construction failure falls back without retaining a frame", reader.take_latest_image() is None
              and reader._latest_frame is None)

        # A later camera publication is handled after startup.
        await reader.aclose()
        late_room = Emitter()
        late_reader = interview_agent.CameraFrameInput("smarthr-ai-interview-camera-late", enabled=True)
        late_reader.start(late_room, applicant.identity)
        late_room.fire("track_subscribed", track, publication, applicant)
        check("later track_subscribed camera is selected", len(FakeVideoStream.created) == 2)
        stream = FakeVideoStream.created[-1]
        late_room.fire("track_unsubscribed", track, publication, applicant)
        await asyncio.sleep(0)
        check("track disconnect clears stream and retained frame", late_reader._latest_frame is None and stream.closed)
        await late_reader.aclose()
        check("cleanup unregisters video handlers", all(not handlers for handlers in late_room.handlers.values()))
    finally:
        interview_agent.rtc.VideoStream = original_stream


def static_contract(check):
    root = Path(__file__).resolve().parents[1]
    worker = (root / "app/ai/interview/worker.py").read_text(encoding="utf-8")
    frontend = (root / "frontend/src/pages/applicant/AiInterviewPage.tsx").read_text(encoding="utf-8")
    tokens = (root / "app/services/ai_interview_service.py").read_text(encoding="utf-8")
    source = (root / "app/ai/interview/agent.py").read_text(encoding="utf-8")
    config = (root / "app/ai/interview/config.py").read_text(encoding="utf-8")
    check("RoomOptions automatic video input remains disabled", "video_input=False" in worker)
    check("explicit Stage 5 environment gate defaults off", "camera_vision_enabled()" in worker
          and '"SMARTHR_INTERVIEW_CAMERA_VISION"' in config
          and "enabled: bool = False" in source)
    check("worker starts Stage 5 reader only when explicitly enabled",
          "if _is_applicant(linked) and camera_vision_enabled():" in worker
          and "enabled=True" in worker)
    check("worker uses manual rtc.VideoStream and gated ImageContent", "rtc.VideoStream(track)" in source
          and "ImageContent(image=frame" in source)
    check("image attachment is gated to both opt-in and accepted answer turn",
          "if eligible_for_camera and self.camera_frames.enabled:" in source
          and "eligible_for_camera = self._last_decision_was_answer" in source)
    check("disabled reader registers no listeners or retains no frames",
          "if not self.enabled or self._room is not None:" in source
          and "if not self.enabled:" in source and "self._latest_frame = None" in source)
    check("frontend Stage 4A publication remains named ai-interview-camera", "publishTrack(track, { name: CAMERA_TRACK_NAME })" in frontend)
    check("no publishData call exists in camera frontend", ".publishData(" not in frontend)
    check("applicant token retains disabled data publishing", "can_publish_data=False" in tokens)
    check("camera implementation does not add frame/base64 logging", "base64" not in source
          and "pixels" not in source and "data_url" not in source)
    check("Stage 7 summaries remain absent from worker and Stage 5",
          "facialMotionSummaryRef" not in source and "summarizeFacialMotion" not in source)


def test_config(check):
    from app.ai.interview import config

    with patch.object(config, "interview_setting", return_value=None):
        check("camera vision configuration defaults off", config.camera_vision_enabled() is False)
    original = os.environ.get("SMARTHR_INTERVIEW_CAMERA_VISION")
    try:
        for value, expected in (("true", True), ("1", True), ("yes", True), ("on", True),
                                ("false", False), ("0", False), ("", False), ("enabled", False)):
            os.environ["SMARTHR_INTERVIEW_CAMERA_VISION"] = value
            check(f"camera vision setting {value!r} -> {expected}",
                  config.camera_vision_enabled() is expected)
    finally:
        if original is None:
            os.environ.pop("SMARTHR_INTERVIEW_CAMERA_VISION", None)
        else:
            os.environ["SMARTHR_INTERVIEW_CAMERA_VISION"] = original


if __name__ == "__main__":
    diag.reset()
    checks = Checks()
    static_contract(checks.check)
    test_config(checks.check)
    asyncio.run(run(checks.check))
    raise SystemExit(1 if checks.failed else 0)
