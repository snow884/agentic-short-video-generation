from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Integer, String
try:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass
except ImportError:
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()

import enum 
from dataclasses import dataclass, field
from pydantic import BaseModel, ConfigDict
from dataclasses_json import dataclass_json
from pydantic import BaseModel


class Towns(Base):
    __tablename__ = "towns"

    id = Column(Integer, primary_key=True)
    name = Column(String, default="")
    state = Column(String, default="")
    description = Column(String, default="")
    gps_longitude = Column(String, default="")
    gps_latitude = Column(String, default="")
    #events: Mapped["Events"] = relationship(back_populates="town")

class TownsSchema(BaseModel):
    name: str | None = None
    state: str | None = None
    description: str | None = None
    gps_longitude: str | None = None
    gps_latitude: str | None = None

class Weekends(Base):
    __tablename__ = "weekends"

    id = Column(Integer, primary_key=True)
    date = Column(String, default="")
    #events: Mapped["Events"] = relationship(back_populates="weekend")

class WeekendsSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int | None = None
    date: str | None = None


class Weather(Base):
    __tablename__ = "weather"

    id = Column(Integer, primary_key=True)
    weekend_id = Column(Integer, ForeignKey('weekends.id'))
    town_id = Column(Integer, ForeignKey('towns.id'))
    temperature = Column(String)
    rain = Column(String)
    clouds = Column(String)
    description = Column(String)
    
class WeatherSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int | None = None
    weekend_id: int | None = None
    town_id: int | None = None
    temperature: str | None = None
    rain: str | None = None
    clouds: str | None = None
    description: str | None = None

class Events(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    town_id = Column(Integer, ForeignKey('towns.id'))
    weekend_id = Column(Integer, ForeignKey('weekends.id'))
    event_name = Column(String, default="")
    date = Column(String, default="")
    time = Column(String, default="")
    location_address = Column(String, default="")
    description = Column(String, default="")
    gps_longitude = Column(String, default="")
    gps_latitude = Column(String, default="")
    url = Column(String, default="")
    url_facebook = Column(String, default="")
    url_instagram = Column(String, default="")
    
    #weekend: Mapped["Weekends"] = relationship(back_populates="events")
    #town: Mapped["Towns"] = relationship(back_populates="events")

class EventsSchema(BaseModel):
    event_name: str | None = None
    date: str | None = None
    time: str | None = None
    location_address: str | None = None
    description: str | None = None
    gps_longitude: str | None = None
    gps_latitude: str | None = None
    url: str | None = None
    url_facebook: str | None = None
    url_instagram: str | None = None


class EventList(BaseModel):
    events: list[EventsSchema] | None = []

class VideoSegments(Base):
    __tablename__ = "video_segments"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    script_text = Column(String, default="")
    Image_id = Column(Integer, ForeignKey('Image.id'))

class VideoSegmentsSchema(BaseModel):

    event_id: int | None = None
    script_text: str | None = None
    Image_id: int | None = None


class VideoSegmentsList(BaseModel):

    video_segments: list[VideoSegmentsSchema] | None = []

class ImageType(enum.Enum):
    RELATED_IMAGES = "related_images"
    MAP_IMAGE = "map_image"

class Image(Base):
    __tablename__ = "Image"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    Image_type = Column(String, default="")
    Image_url = Column(String, default="")
    file_path = Column(String, default="")
    description = Column(String, default="")
    title = Column(String, default="")

class ImageSchema(BaseModel):
    Image_url: str | None = None
    file_path: str | None = None
    description: str | None = None
    title: str | None = None

class ImageList(BaseModel):

    images: list[ImageSchema]  | None = []