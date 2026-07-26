from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String

try:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass

except ImportError:
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()


from pydantic import BaseModel, ConfigDict, Field, model_validator


class Videos(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)
    name = Column(String, default="")
    file_path = Column(String, default="")
    prompt = Column(String, default="")


class VideosSchema(BaseModel):
    name: str
    prompt: str


class PeopleAndProps(Base):
    __tablename__ = "people_and_props"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    name = Column(String, default="")
    image_path = Column(String, default="")
    prompt = Column(String, default="")


class PeopleAndPropsSchema(BaseModel):
    name: str
    prompt: str


class VideoSegments(Base):
    __tablename__ = "video_segments"

    id = Column(Integer, primary_key=True)

    video_id = Column(Integer, ForeignKey("videos.id"))

    new_scene = Column(Boolean, default=False)

    start_image_prompt = Column(String, default="")
    start_image_people_and_props_names = Column(String, default="")
    start_image_path = Column(String, default="")

    stop_image_prompt = Column(String, default="")
    stop_image_people_and_props_names = Column(String, default="")
    stop_image_path = Column(String, default="")

    video_prompt = Column(String, default="")

    narrator_script = Column(String, default="")

    audio_file_path = Column(String, default="")
    video_path = Column(String, default="")

    timestamp = Column(Integer, default=0)


class VideoSegmentsSchema(BaseModel):
    video_prompt: str

    # new_scene: bool

    start_image_prompt: str
    start_image_people_and_props_names: str

    timestamp: int

    # stop_image_prompt: str
    # stop_image_people_and_props_names: str

    narrator_script: str


class VideoSegmentsList(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    video_segments: Optional[list[VideoSegmentsSchema]] = Field(default_factory=list)

    people_and_props: Optional[list[PeopleAndPropsSchema]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_segment_input(cls, data):
        if isinstance(data, dict):
            normalized = dict(data)
            if "video_segments" not in normalized and "segments" in normalized:
                normalized["video_segments"] = normalized.pop("segments")

            if "people_and_props" not in normalized and "people" in normalized:
                normalized["people_and_props"] = normalized.pop("people")

            return normalized
        return data
