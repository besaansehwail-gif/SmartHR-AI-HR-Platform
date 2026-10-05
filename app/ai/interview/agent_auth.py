"""How the agent worker proves to the backend that it is the agent.

The worker must not read the database, so it asks the backend for what it
needs (Phase 3: the interview's question plan). That request needs a
credential, and the worker already holds one secret the backend also holds:
the LiveKit API secret. So the worker signs a **LiveKit-format access token**
with it, and the backend verifies that token with LiveKit's own
`TokenVerifier` - no new secret, no new signing code.

The token is deliberately narrow, and the backend checks every part of it:

* signed with the project's key and secret (an applicant cannot mint one);
* `video.agent = True` and identity `AGENT_IDENTITY` - an applicant's room
  token has neither, so replaying the applicant's own token is refused;
* `metadata = PURPOSE` - it is only good for this one kind of request;
* `video.room` names exactly one SmartHR interview room;
* 2 minutes to live.

Imports nothing from the database - the worker uses this module too.
"""

from datetime import timedelta

from livekit import api

AGENT_IDENTITY = "smarthr-interview-agent"
PURPOSE = "smarthr.interview.plan"
ROOM_PREFIX = "smarthr-ai-interview-"
TTL = timedelta(minutes=2)


class AgentAuthError(Exception):
    pass


def mint_agent_token(api_key: str, api_secret: str, room_name: str) -> str:
    grants = api.VideoGrants(room=room_name, agent=True, room_join=False,
                             can_publish=False, can_subscribe=False, can_publish_data=False)
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(AGENT_IDENTITY)
        .with_metadata(PURPOSE)
        .with_grants(grants)
        .with_ttl(TTL)
        .to_jwt()
    )


def verify_agent_token(token: str, api_key: str, api_secret: str) -> str:
    """Return the room the token is for, or raise AgentAuthError."""
    try:
        claims = api.TokenVerifier(api_key, api_secret).verify(token)
    except Exception as exc:  # expired, wrong signature, malformed
        raise AgentAuthError(f"invalid agent token ({type(exc).__name__})") from None

    video = claims.video
    if claims.identity != AGENT_IDENTITY or not video or not video.agent:
        raise AgentAuthError("not an agent token")
    if claims.metadata != PURPOSE:
        raise AgentAuthError("token not issued for this purpose")
    room = video.room or ""
    if not room.startswith(ROOM_PREFIX):
        raise AgentAuthError("token does not name a SmartHR interview room")
    return room
