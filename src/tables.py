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
    country = Column(String, default="")
    county = Column(String, default="")
    population = Column(String, default="")
    zip = Column(String, default="")
    gps_longitude = Column(String, default="")
    gps_latitude = Column(String, default="")
    #events: Mapped["Events"] = relationship(back_populates="town")

class TownsSchema(BaseModel):
    name: str
    state: str
    country: str
    county: str
    population: str
    zip: str 
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

class EventsSchema(BaseModel):
    event_name: str
    date: str
    time: str
    location_address: str
    description: str
    gps_longitude: str
    gps_latitude: str
    url: str
    url_facebook: str
    url_instagram: str


class EventList(BaseModel):
    events: list[EventsSchema] | None = []

class VideoSegments(Base):
    __tablename__ = "video_segments"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    script_text = Column(String, default="")
    Image_id = Column(Integer, ForeignKey('Image.id'))
    sound_file_path = Column(String, default="")
    timestamp = Column(Integer, default=0)
    
class VideoSegmentsSchema(BaseModel):

    event_id: int
    script_text: str
    Image_id: int
    timestamp: int


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
    image_url = Column(String, default="")
    file_path = Column(String, default="")
    description = Column(String, default="")
    title = Column(String, default="")

class ImageSchema(BaseModel):
    image_url: str
    description: str
    title: str
    
class ImageList(BaseModel):
    images: list[ImageSchema] 

class TownsList(BaseModel):

    towns: List[TownsSchema]  
    
class TownsList(BaseModel):

    towns: List[TownsSchema]  | None = []