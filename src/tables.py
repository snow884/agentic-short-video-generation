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

class Towns(Base):
    __tablename__ = "towns"

    id = Column(Integer, primary_key=True)
    name = Column(String, default="")
    state = Column(String, default="")
    description = Column(String, default="")
    gps_longitude = Column(String, default="")
    gps_latitude = Column(String, default="")
    #events: Mapped["Events"] = relationship(back_populates="town")

@dataclass_json
@dataclass
class TownsSchema:
    name: str
    state: str
    description: str
    gps_longitude: str
    gps_latitude: str

class Weekends(Base):
    __tablename__ = "weekends"

    id = Column(Integer, primary_key=True)
    date = Column(String, default="")
    #events: Mapped["Events"] = relationship(back_populates="weekend")

class WeekendsSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    date: str


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

    id: int
    weekend_id: int
    town_id: int
    temperature: str
    rain: str
    clouds: str
    description: str

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

@dataclass_json
@dataclass
class EventsSchema:
    event_name: str = None
    date: str = None
    time: str = None
    location_address:str = None
    description:str = None
    gps_longitude: str = None
    gps_latitude: str = None
    url: str = None
    url_facebook: str = None
    url_instagram: str = None


@dataclass_json
@dataclass
class EventList:
    events: List[EventsSchema]

class VideoSegments(Base):
    __tablename__ = "video_segments"

    id = Column(Integer, primary_key=True)
    town_id = Column(Integer, ForeignKey('towns.id'))
    weekend_id = Column(Integer, ForeignKey('weekends.id'))
    event_id = Column(Integer, ForeignKey('events.id'))
    script_text = Column(String, default="")
    media_ids = Column(String, default="")

class MediaType(enum.Enum):
    RELATED_IMAGES = "related_images"
    MAP_IMAGE = "map_image"

class Media(Base):
    __tablename__ = "media"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    media_type = Column(String, default="")
    media_url = Column(String, default="")
    file_path = Column(String, default="")
    description = Column(String, default="")
    title = Column(String, default="")

class MediaSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    media_url: str
    file_path: str
    description: str
    title: str

@dataclass_json
@dataclass
class MediaList(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    media: list[MediaSchema] = field(default_factory=list)