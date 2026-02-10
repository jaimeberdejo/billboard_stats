"""Data models for Billboard statistics platform."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class Artist(BaseModel):
    id: int
    name: str
    image_url: Optional[str] = None


class Song(BaseModel):
    id: int
    title: str
    artist_credit: str
    image_url: Optional[str] = None


class Album(BaseModel):
    id: int
    title: str
    artist_credit: str
    image_url: Optional[str] = None


class SongStats(BaseModel):
    song_id: int
    total_weeks: int = 0
    peak_position: Optional[int] = None
    weeks_at_peak: int = 0
    weeks_at_number_one: int = 0
    debut_date: Optional[date] = None
    last_date: Optional[date] = None
    debut_position: Optional[int] = None


class AlbumStats(BaseModel):
    album_id: int
    total_weeks: int = 0
    peak_position: Optional[int] = None
    weeks_at_peak: int = 0
    weeks_at_number_one: int = 0
    debut_date: Optional[date] = None
    last_date: Optional[date] = None
    debut_position: Optional[int] = None


class ArtistStats(BaseModel):
    artist_id: int
    total_hot100_songs: int = 0
    total_b200_albums: int = 0
    total_hot100_weeks: int = 0
    total_b200_weeks: int = 0
    hot100_number_ones: int = 0
    b200_number_ones: int = 0
    best_hot100_peak: Optional[int] = None
    best_b200_peak: Optional[int] = None
    first_chart_date: Optional[date] = None
    latest_chart_date: Optional[date] = None
    max_simultaneous_hot100: int = 0


class ArtistProfile(BaseModel):
    artist: Artist
    stats: Optional[ArtistStats] = None


class SongWithStats(BaseModel):
    song: Song
    stats: Optional[SongStats] = None
    artists: List[Artist] = []


class AlbumWithStats(BaseModel):
    album: Album
    stats: Optional[AlbumStats] = None
    artists: List[Artist] = []


class ChartEntry(BaseModel):
    rank: int
    title: str
    artist_credit: str
    image_url: Optional[str] = None
    peak_pos: Optional[int] = None
    last_pos: Optional[int] = None
    weeks_on_chart: Optional[int] = None
    is_new: bool = False
    song_id: Optional[int] = None
    album_id: Optional[int] = None


class ChartRunEntry(BaseModel):
    chart_date: date
    rank: int
    last_pos: Optional[int] = None
    is_new: bool = False
    peak_pos: Optional[int] = None
    weeks_on_chart: Optional[int] = None


class RecordEntry(BaseModel):
    """Generic record/leaderboard entry."""
    rank: int
    title: str
    artist_credit: str
    value: int
    song_id: Optional[int] = None
    album_id: Optional[int] = None
    artist_id: Optional[int] = None
    chart_date: Optional[date] = None
