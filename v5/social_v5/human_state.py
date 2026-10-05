"""Versioned social evidence contract. Missing is None, never a fabricated neutral."""
from pydantic import BaseModel, ConfigDict, Field

class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    source: str = 'unavailable'
    confidence: float = Field(default=0, ge=0, le=1)
    calibrated: bool = False
    observed_at: float | None = None

class Face(Evidence):
    emotion_distribution: dict[str, float] = Field(default_factory=dict)
    valence: float | None = None
    arousal: float | None = None
    action_units: dict = Field(default_factory=dict)
    gaze: dict = Field(default_factory=dict)
    head_pose: dict = Field(default_factory=dict)
    landmarks: list = Field(default_factory=list)
    facial_embedding: list[float] = Field(default_factory=list)
    facial_blendshapes: dict[str,float] = Field(default_factory=dict)
    face_mesh: list = Field(default_factory=list)
    detection_confidence: float | None = None
    identity_binding: str = 'unverified_single_person'
    expression_actions: dict[str,float] = Field(default_factory=dict)
    stable_actions: list[str] = Field(default_factory=list)
    action_sample_count: int = 0

class Voice(Evidence):
    emotion_distribution: dict[str, float] = Field(default_factory=dict)
    emotion_label: str | None = None
    emotion_embedding: list[float] = Field(default_factory=list)
    valence: float | None = None
    arousal: float | None = None
    pitch: dict = Field(default_factory=dict)
    energy: dict = Field(default_factory=dict)
    speech_rate: float | None = None
    pause: dict = Field(default_factory=dict)
    voice_activity: float | None = None
    audio_events: list[str] = Field(default_factory=list)
    duration_seconds: float = 0
    language: str | None = None

class Body(Evidence):
    pose: list = Field(default_factory=list)
    posture: str = 'unknown'
    body_orientation: dict = Field(default_factory=dict)
    gesture: dict = Field(default_factory=dict)
    movement_intensity: float | None = None
    hand_movement_intensity: float | None = None
    shoulder_openness: float | None = None
    torso_lean: float | None = None
    head_down_proxy: float | None = None
    approach_avoidance: float | None = None
    sudden_posture_change: bool = False
    prolonged_head_down_seconds: float = 0

class Language(Evidence):
    explicit_emotion: list[str] = Field(default_factory=list)
    sentiment: float | None = None
    intention: str | None = None
    semantic_emotion: dict = Field(default_factory=dict)
    contradiction: bool = False

class Interaction(Evidence):
    gaze_to_robot: float | None = None
    response_latency: float | None = None
    turn_taking: str = 'unknown'
    engagement: float | None = None
    interruption: bool = False
    distance_change: float | None = None
    action_reaction: dict = Field(default_factory=dict)

class Temporal(Evidence):
    baseline: dict = Field(default_factory=dict)
    current: dict = Field(default_factory=dict)
    delta: dict = Field(default_factory=dict)
    short_term_trend: dict = Field(default_factory=dict)
    medium_term_trend: dict = Field(default_factory=dict)
    stability: float | None = None
    sample_count: int = 0

class HumanState(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    schema_version: str = '1.0'
    face: Face = Field(default_factory=Face)
    voice: Voice = Field(default_factory=Voice)
    body: Body = Field(default_factory=Body)
    language: Language = Field(default_factory=Language)
    interaction: Interaction = Field(default_factory=Interaction)
    temporal: Temporal = Field(default_factory=Temporal)
    cross_modal_consistency: float | None = None
    uncertainty: list[str] = Field(default_factory=list)
    confidence: float = 0
    event: str = 'stable_or_insufficient_evidence'

    def compact(self):
        """Bounded Qwen input: no raw media, coordinates, or embedding arrays."""
        return {'face':{'valence':self.face.valence,'arousal':self.face.arousal,'confidence':self.face.confidence,
                       'stable_visible_actions':self.face.stable_actions,'action_samples':self.face.action_sample_count},
            'voice':{'emotion':self.voice.emotion_label,'events':self.voice.audio_events,'confidence':self.voice.confidence},
            'body':{'posture':self.body.posture,'movement':self.body.movement_intensity,'confidence':self.body.confidence},
            'temporal':{'delta':dict(list(self.temporal.delta.items())[:8]),'trend_30s':dict(list(self.temporal.medium_term_trend.items())[:8])},
            'consistency':self.cross_modal_consistency,'event':self.event,'uncertainty':self.uncertainty[:3]}
