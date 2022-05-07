import base64
import os, plexapi, requests, embyapi
from datetime import datetime
from embyapi import ApiClient
from embyapi import Configuration
from modules import builder, util
from modules.library import Library
from modules.util import Failed, ImageData
from PIL import Image
from plexapi import utils
from plexapi.audio import Artist, Track, Album
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.collection import Collection
from plexapi.playlist import Playlist
from plexapi.server import PlexServer
from plexapi.video import Movie, Show, Season, Episode
from retrying import retry
from urllib import parse
from xml.etree.ElementTree import ParseError

logger = util.logger

builders = ["plex_all", "plex_pilots", "plex_collectionless", "plex_search"]
search_translation = {
    "episode_title": "episode.title",
    "network": "show.network",
    "critic_rating": "rating",
    "audience_rating": "audienceRating",
    "user_rating": "userRating",
    "episode_user_rating": "episode.userRating",
    "content_rating": "contentRating",
    "episode_year": "episode.year",
    "release": "originallyAvailableAt",
    "show_unmatched": "show.unmatched",
    "episode_unmatched": "episode.unmatched",
    "episode_duplicate": "episode.duplicate",
    "added": "addedAt",
    "episode_added": "episode.addedAt",
    "episode_air_date": "episode.originallyAvailableAt",
    "plays": "viewCount",
    "episode_plays": "episode.viewCount",
    "last_played": "lastViewedAt",
    "episode_last_played": "episode.lastViewedAt",
    "unplayed": "unwatched",
    "episode_unplayed": "episode.unwatched",
    "subtitle_language": "subtitleLanguage",
    "audio_language": "audioLanguage",
    "progress": "inProgress",
    "episode_progress": "episode.inProgress",
    "unplayed_episodes": "show.unwatchedLeaves",
    "season_collection": "season.collection",
    "episode_collection": "episode.collection",
    "artist_title": "artist.title",
    "artist_user_rating": "artist.userRating",
    "artist_genre": "artist.genre",
    "artist_collection": "artist.collection",
    "artist_country": "artist.country",
    "artist_mood": "artist.mood",
    "artist_style": "artist.style",
    "artist_added": "artist.addedAt",
    "artist_last_played": "artist.lastViewedAt",
    "artist_unmatched": "artist.unmatched",
    "album_title": "album.title",
    "album_year": "album.year",
    "album_decade": "album.decade",
    "album_genre": "album.genre",
    "album_plays": "album.viewCount",
    "album_last_played": "album.lastViewedAt",
    "album_user_rating": "album.userRating",
    "album_critic_rating": "album.rating",
    "album_record_label": "album.studio",
    "album_mood": "album.mood",
    "album_style": "album.style",
    "album_format": "album.format",
    "album_type": "album.subformat",
    "album_collection": "album.collection",
    "album_added": "album.addedAt",
    "album_released": "album.originallyAvailableAt",
    "album_unmatched": "album.unmatched",
    "album_source": "album.source",
    "album_label": "album.label",
    "track_mood": "track.mood",
    "track_title": "track.title",
    "track_plays": "track.viewCount",
    "track_last_played": "track.lastViewedAt",
    "track_skips": "track.skipCount",
    "track_last_skipped": "track.lastSkippedAt",
    "track_user_rating": "track.userRating",
    "track_last_rated": "track.lastRatedAt",
    "track_added": "track.addedAt",
    "track_trash": "track.trash",
    "track_source": "track.source"
}
show_translation = {
    "title": "show.title",
    "studio": "show.studio",
    "rating": "show.rating",
    "audienceRating": "show.audienceRating",
    "userRating": "show.userRating",
    "contentRating": "show.contentRating",
    "year": "show.year",
    "originallyAvailableAt": "show.originallyAvailableAt",
    "unmatched": "show.unmatched",
    "genre": "show.genre",
    "collection": "show.collection",
    "actor": "show.actor",
    "addedAt": "show.addedAt",
    "viewCount": "show.viewCount",
    "lastViewedAt": "show.lastViewedAt",
    "resolution": "episode.resolution",
    "hdr": "episode.hdr",
    "subtitleLanguage": "episode.subtitleLanguage",
    "audioLanguage": "episode.audioLanguage",
    "trash": "episode.trash",
    "label": "show.label",
}
modifier_translation = {
    "": "", ".not": "!", ".is": "%3D", ".isnot": "!%3D", ".gt": "%3E%3E", ".gte": "%3E", ".lt": "%3C%3C", ".lte": "%3C",
    ".before": "%3C%3C", ".after": "%3E%3E", ".begins": "%3C", ".ends": "%3E"
}
album_sorting_options = {"default": -1, "newest": 0, "oldest": 1, "name": 2}
episode_sorting_options = {"default": -1, "oldest": 0, "newest": 1}
keep_episodes_options = {"all": 0, "5_latest": 5, "3_latest": 3, "latest": 1, "past_3": -3, "past_7": -7, "past_30": -30}
delete_episodes_options = {"never": 0, "day": 1, "week": 7, "refresh": 100}
season_display_options = {"default": -1, "show": 0, "hide": 1}
episode_ordering_options = {"default": None, "tmdb_aired": "tmdbAiring", "tvdb_aired": "aired", "tvdb_dvd": "dvd", "tvdb_absolute": "absolute"}
plex_languages = ["default", "ar-SA", "ca-ES", "cs-CZ", "da-DK", "de-DE", "el-GR", "en-AU", "en-CA", "en-GB", "en-US",
                  "es-ES", "es-MX", "et-EE", "fa-IR", "fi-FI", "fr-CA", "fr-FR", "he-IL", "hi-IN", "hu-HU", "id-ID",
                  "it-IT", "ja-JP", "ko-KR", "lt-LT", "lv-LV", "nb-NO", "nl-NL", "pl-PL", "pt-BR", "pt-PT", "ro-RO",
                  "ru-RU", "sk-SK", "sv-SE", "th-TH", "tr-TR", "uk-UA", "vi-VN", "zh-CN", "zh-HK", "zh-TW"]
metadata_language_options = {lang.lower(): lang for lang in plex_languages}
metadata_language_options["default"] = None
use_original_title_options = {"default": -1, "no": 0, "yes": 1}
collection_order_options = ["release", "alpha", "custom"]
collection_level_show_options = ["episode", "season"]
collection_level_music_options = ["album", "track"]
collection_level_options = collection_level_show_options + collection_level_music_options
collection_mode_keys = {-1: "default", 0: "hide", 1: "hideItems", 2: "showItems"}
collection_order_keys = {0: "release", 1: "alpha", 2: "custom"}
item_advance_keys = {
    "item_album_sorting": ("albumSort", album_sorting_options),
    "item_episode_sorting": ("episodeSort", episode_sorting_options),
    "item_keep_episodes": ("autoDeletionItemPolicyUnwatchedLibrary", keep_episodes_options),
    "item_delete_episodes": ("autoDeletionItemPolicyWatchedLibrary", delete_episodes_options),
    "item_season_display": ("flattenSeasons", season_display_options),
    "item_episode_ordering": ("showOrdering", episode_ordering_options),
    "item_metadata_language": ("languageOverride", metadata_language_options),
    "item_use_original_title": ("useOriginalTitle", use_original_title_options)
}
new_plex_agents = ["tv.plex.agents.movie", "tv.plex.agents.series"]
music_searches = [
    "artist_title", "artist_title.not", "artist_title.is", "artist_title.isnot", "artist_title.begins", "artist_title.ends",
    "artist_user_rating.gt", "artist_user_rating.gte", "artist_user_rating.lt", "artist_user_rating.lte",
    "artist_genre", "artist_genre.not",
    "artist_collection", "artist_collection.not",
    "artist_country", "artist_country.not",
    "artist_mood", "artist_mood.not",
    "artist_style", "artist_style.not",
    "artist_added", "artist_added.not", "artist_added.before", "artist_added.after",
    "artist_last_played", "artist_last_played.not", "artist_last_played.before", "artist_last_played.after",
    "artist_unmatched",
    "album_title", "album_title.not", "album_title.is", "album_title.isnot", "album_title.begins", "album_title.ends",
    "album_year.gt", "album_year.gte", "album_year.lt", "album_year.lte",
    "album_decade",
    "album_genre", "album_genre.not",
    "album_plays.gt", "album_plays.gte", "album_plays.lt", "album_plays.lte",
    "album_last_played", "album_last_played.not", "album_last_played.before", "album_last_played.after",
    "album_user_rating.gt", "album_user_rating.gte", "album_user_rating.lt", "album_user_rating.lte",
    "album_critic_rating.gt", "album_critic_rating.gte", "album_critic_rating.lt", "album_critic_rating.lte",
    "album_record_label", "album_record_label.not", "album_record_label.is", "album_record_label.isnot", "album_record_label.begins", "album_record_label.ends",
    "album_mood", "album_mood.not",
    "album_style", "album_style.not",
    "album_format", "album_format.not",
    "album_type", "album_type.not",
    "album_collection", "album_collection.not",
    "album_added", "album_added.not", "album_added.before", "album_added.after",
    "album_released", "album_released.not", "album_released.before", "album_released.after",
    "album_unmatched",
    "album_source", "album_source.not",
    "album_label", "album_label.not",
    "track_mood", "track_mood.not",
    "track_title", "track_title.not", "track_title.is", "track_title.isnot", "track_title.begins", "track_title.ends",
    "track_plays.gt", "track_plays.gte", "track_plays.lt", "track_plays.lte",
    "track_last_played", "track_last_played.not", "track_last_played.before", "track_last_played.after",
    "track_skips.gt", "track_skips.gte", "track_skips.lt", "track_skips.lte",
    "track_last_skipped", "track_last_skipped.not", "track_last_skipped.before", "track_last_skipped.after",
    "track_user_rating.gt", "track_user_rating.gte", "track_user_rating.lt", "track_user_rating.lte",
    "track_last_rated", "track_last_rated.not", "track_last_rated.before", "track_last_rated.after",
    "track_added", "track_added.not", "track_added.before", "track_added.after",
    "track_trash",
    "track_source", "track_source.not"
]
searches = [
    "title", "title.not", "title.is", "title.isnot", "title.begins", "title.ends",
    "studio", "studio.not", "studio.is", "studio.isnot", "studio.begins", "studio.ends",
    "actor", "actor.not",
    "audio_language", "audio_language.not",
    "collection", "collection.not",
    "season_collection", "season_collection.not",
    "episode_collection", "episode_collection.not",
    "content_rating", "content_rating.not",
    "country", "country.not",
    "director", "director.not",
    "genre", "genre.not",
    "label", "label.not",
    "network", "network.not",
    "producer", "producer.not",
    "subtitle_language", "subtitle_language.not",
    "writer", "writer.not",
    "decade", "resolution", "hdr", "unmatched", "duplicate", "unplayed", "progress", "trash",
    "last_played", "last_played.not", "last_played.before", "last_played.after",
    "added", "added.not", "added.before", "added.after",
    "release", "release.not", "release.before", "release.after",
    "duration.gt", "duration.gte", "duration.lt", "duration.lte",
    "plays.gt", "plays.gte", "plays.lt", "plays.lte",
    "user_rating.gt", "user_rating.gte", "user_rating.lt", "user_rating.lte",
    "critic_rating.gt", "critic_rating.gte", "critic_rating.lt", "critic_rating.lte",
    "audience_rating.gt", "audience_rating.gte", "audience_rating.lt", "audience_rating.lte",
    "year", "year.not", "year.gt", "year.gte", "year.lt", "year.lte",
    "unplayed_episodes", "episode_unplayed", "episode_duplicate", "episode_progress", "episode_unmatched", "show_unmatched",
    "episode_title", "episode_title.not", "episode_title.is", "episode_title.isnot", "episode_title.begins", "episode_title.ends",
    "episode_added", "episode_added.not", "episode_added.before", "episode_added.after",
    "episode_air_date", "episode_air_date.not", "episode_air_date.before", "episode_air_date.after",
    "episode_last_played", "episode_last_played.not", "episode_last_played.before", "episode_last_played.after",
    "episode_plays.gt", "episode_plays.gte", "episode_plays.lt", "episode_plays.lte",
    "episode_user_rating.gt", "episode_user_rating.gte", "episode_user_rating.lt", "episode_user_rating.lte",
    "episode_year", "episode_year.not", "episode_year.gt", "episode_year.gte", "episode_year.lt", "episode_year.lte"
] + music_searches
and_searches = [
    "title.and", "studio.and", "actor.and", "audio_language.and", "collection.and",
    "content_rating.and", "country.and",  "director.and", "genre.and", "label.and",
    "network.and", "producer.and", "subtitle_language.and", "writer.and"
]
or_searches = [
    "title", "studio", "actor", "audio_language", "collection", "content_rating",
    "country", "director", "genre", "label", "network", "producer", "subtitle_language",
    "writer", "decade", "resolution", "year", "episode_title", "episode_year"
]
movie_only_searches = [
    "country", "country.not", "director", "director.not", "producer", "producer.not", "writer", "writer.not",
    "decade", "duplicate", "unplayed", "progress",
    "duration.gt", "duration.gte", "duration.lt", "duration.lte"
]
show_only_searches = [
    "network", "network.not",
    "season_collection", "season_collection.not",
    "episode_collection", "episode_collection.not",
    "episode_title", "episode_title.not", "episode_title.is", "episode_title.isnot", "episode_title.begins", "episode_title.ends",
    "episode_added", "episode_added.not", "episode_added.before", "episode_added.after",
    "episode_air_date", "episode_air_date.not",
    "episode_air_date.before", "episode_air_date.after",
    "episode_last_played", "episode_last_played.not", "episode_last_played.before", "episode_last_played.after",
    "episode_plays.gt", "episode_plays.gte", "episode_plays.lt", "episode_plays.lte",
    "episode_user_rating.gt", "episode_user_rating.gte", "episode_user_rating.lt", "episode_user_rating.lte",
    "episode_year", "episode_year.not", "episode_year.gt", "episode_year.gte", "episode_year.lt", "episode_year.lte",
    "unplayed_episodes", "episode_unplayed", "episode_duplicate", "episode_progress", "episode_unmatched", "show_unmatched",
]
string_attributes = ["title", "studio", "episode_title", "artist_title", "album_title", "album_record_label", "track_title"]
float_attributes = [
    "user_rating", "episode_user_rating", "critic_rating", "audience_rating", "duration",
    "artist_user_rating", "album_user_rating", "album_critic_rating", "track_user_rating"
]
boolean_attributes = [
    "hdr", "unmatched", "duplicate", "unplayed", "progress", "trash", "unplayed_episodes", "episode_unplayed",
    "episode_duplicate", "episode_progress", "episode_unmatched", "show_unmatched", "artist_unmatched", "album_unmatched", "track_trash"
]
tmdb_attributes = ["actor", "director", "producer", "writer"]
date_attributes = [
    "added", "episode_added", "release", "episode_air_date", "last_played", "episode_last_played",
    "first_episode_aired", "last_episode_aired", "artist_added", "artist_last_played", "album_last_played",
    "album_added", "album_released", "track_last_played", "track_last_skipped", "track_last_rated", "track_added"
]
year_attributes = ["decade", "year", "episode_year", "album_year", "album_decade"]
number_attributes = ["plays", "episode_plays", "tmdb_vote_count", "album_plays", "track_plays", "track_skips"] + year_attributes
search_display = {"added": "Date Added", "release": "Release Date", "hdr": "HDR", "progress": "In Progress", "episode_progress": "Episode In Progress"}
tag_attributes = [
    "actor", "audio_language", "collection", "content_rating", "country", "director", "genre", "label", "network",
    "producer", "resolution", "studio", "subtitle_language", "writer", "season_collection", "episode_collection",
    "artist_genre", "artist_collection", "artist_country", "artist_mood", "artist_style", "album_genre", "album_mood",
    "album_style", "album_format", "album_type", "album_collection", "album_source", "album_label", "track_mood", "track_source"
]
movie_sorts = {
    "title.asc": "titleSort", "title.desc": "titleSort%3Adesc",
    "year.asc": "year", "year.desc": "year%3Adesc",
    "originally_available.asc": "originallyAvailableAt", "originally_available.desc": "originallyAvailableAt%3Adesc",
    "release.asc": "originallyAvailableAt", "release.desc": "originallyAvailableAt%3Adesc",
    "critic_rating.asc": "rating", "critic_rating.desc": "rating%3Adesc",
    "audience_rating.asc": "audienceRating", "audience_rating.desc": "audienceRating%3Adesc",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "content_rating.asc": "contentRating", "content_rating.desc": "contentRating%3Adesc",
    "duration.asc": "duration", "duration.desc": "duration%3Adesc",
    "progress.asc": "viewOffset", "progress.desc": "viewOffset%3Adesc",
    "plays.asc": "viewCount", "plays.desc": "viewCount%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "viewed.asc": "lastViewedAt", "viewed.desc": "lastViewedAt%3Adesc",
    "resolution.asc": "mediaHeight", "resolution.desc": "mediaHeight%3Adesc",
    "bitrate.asc": "mediaBitrate", "bitrate.desc": "mediaBitrate%3Adesc",
    "random": "random"
}
show_sorts = {
    "title.asc": "titleSort", "title.desc": "titleSort%3Adesc",
    "year.asc": "year", "year.desc": "year%3Adesc",
    "originally_available.asc": "originallyAvailableAt", "originally_available.desc": "originallyAvailableAt%3Adesc",
    "release.asc": "originallyAvailableAt", "release.desc": "originallyAvailableAt%3Adesc",
    "critic_rating.asc": "rating", "critic_rating.desc": "rating%3Adesc",
    "audience_rating.asc": "audienceRating", "audience_rating.desc": "audienceRating%3Adesc",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "content_rating.asc": "contentRating", "content_rating.desc": "contentRating%3Adesc",
    "unplayed.asc": "unviewedLeafCount", "unplayed.desc": "unviewedLeafCount%3Adesc",
    "episode_added.asc": "episode.addedAt", "episode_added.desc": "episode.addedAt%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "viewed.asc": "lastViewedAt", "viewed.desc": "lastViewedAt%3Adesc",
    "random": "random"
}
season_sorts = {
    "season.asc": "season.index%2Cseason.titleSort", "season.desc": "season.index%3Adesc%2Cseason.titleSort",
    "show.asc": "show.titleSort%2Cindex", "show.desc": "show.titleSort%3Adesc%2Cindex",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "random": "random"
}
episode_sorts = {
    "title.asc": "titleSort", "title.desc": "titleSort%3Adesc",
    "show.asc": "show.titleSort%2Cseason.index%3AnullsLast%2Cepisode.index%3AnullsLast%2Cepisode.originallyAvailableAt%3AnullsLast%2Cepisode.titleSort%2Cepisode.id",
    "show.desc": "show.titleSort%3Adesc%2Cseason.index%3AnullsLast%2Cepisode.index%3AnullsLast%2Cepisode.originallyAvailableAt%3AnullsLast%2Cepisode.titleSort%2Cepisode.id",
    "year.asc": "year", "year.desc": "year%3Adesc",
    "originally_available.asc": "originallyAvailableAt", "originally_available.desc": "originallyAvailableAt%3Adesc",
    "release.asc": "originallyAvailableAt", "release.desc": "originallyAvailableAt%3Adesc",
    "critic_rating.asc": "rating", "critic_rating.desc": "rating%3Adesc",
    "audience_rating.asc": "audienceRating", "audience_rating.desc": "audienceRating%3Adesc",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "duration.asc": "duration", "duration.desc": "duration%3Adesc",
    "progress.asc": "viewOffset", "progress.desc": "viewOffset%3Adesc",
    "plays.asc": "viewCount", "plays.desc": "viewCount%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "viewed.asc": "lastViewedAt", "viewed.desc": "lastViewedAt%3Adesc",
    "resolution.asc": "mediaHeight", "resolution.desc": "mediaHeight%3Adesc",
    "bitrate.asc": "mediaBitrate", "bitrate.desc": "mediaBitrate%3Adesc",
    "random": "random"
}
artist_sorts = {
    "title.asc": "titleSort", "title.desc": "titleSort%3Adesc",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "played.asc": "lastViewedAt", "played.desc": "lastViewedAt%3Adesc",
    "plays.asc": "viewCount", "plays.desc": "viewCount%3Adesc",
    "random": "random"
}
album_sorts = {
    "title.asc": "titleSort", "title.desc": "titleSort%3Adesc",
    "album_artist.asc": "artist.titleSort%2Calbum.titleSort%2Calbum.index%2Calbum.id%2Calbum.originallyAvailableAt",
    "album_artist.desc": "artist.titleSort%3Adesc%2Calbum.titleSort%2Calbum.index%2Calbum.id%2Calbum.originallyAvailableAt",
    "year.asc": "year", "year.desc": "year%3Adesc",
    "originally_available.asc": "originallyAvailableAt", "originally_available.desc": "originallyAvailableAt%3Adesc",
    "release.asc": "originallyAvailableAt", "release.desc": "originallyAvailableAt%3Adesc",
    "critic_rating.asc": "rating", "critic_rating.desc": "rating%3Adesc",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "played.asc": "lastViewedAt", "played.desc": "lastViewedAt%3Adesc",
    "plays.asc": "viewCount", "plays.desc": "viewCount%3Adesc",
    "random": "random"
}
track_sorts = {
    "title.asc": "titleSort", "title.desc": "titleSort%3Adesc",
    "album_artist.asc": "artist.titleSort%2Calbum.titleSort%2Calbum.year%2Ctrack.absoluteIndex%2Ctrack.index%2Ctrack.titleSort%2Ctrack.id",
    "album_artist.desc": "artist.titleSort%3Adesc%2Calbum.titleSort%2Calbum.year%2Ctrack.absoluteIndex%2Ctrack.index%2Ctrack.titleSort%2Ctrack.id",
    "artist.asc": "originalTitle", "artist.desc": "originalTitle%3Adesc",
    "album.asc": "album.titleSort", "album.desc": "album.titleSort%3Adesc",
    "user_rating.asc": "userRating",  "user_rating.desc": "userRating%3Adesc",
    "duration.asc": "duration", "duration.desc": "duration%3Adesc",
    "plays.asc": "viewCount", "plays.desc": "viewCount%3Adesc",
    "added.asc": "addedAt", "added.desc": "addedAt%3Adesc",
    "played.asc": "lastViewedAt", "played.desc": "lastViewedAt%3Adesc",
    "rated.asc": "lastRatedAt", "rated.desc": "lastRatedAt%3Adesc",
    "popularity.asc": "ratingCount", "popularity.desc": "ratingCount%3Adesc",
    "bitrate.asc": "mediaBitrate", "bitrate.desc": "mediaBitrate%3Adesc",
    "random": "random"
}
sort_types = {
    "movies": (1, movie_sorts),
    "shows": (2, show_sorts),
    "seasons": (3, season_sorts),
    "episodes": (4, episode_sorts),
    "artists": (8, artist_sorts),
    "albums": (9, album_sorts),
    "tracks": (10, track_sorts)
}

LOG_DIR = "logs"
DEBUG_LOG = "debug.log"

class Emby(Library):
    def __init__(self, config, params):
        super().__init__(config, params)
        self.configuration = embyapi.Configuration()
        self.configuration.host = params["emby"]["url"]
        self.configuration.api_key['api_key'] = params["emby"]["api_key"]
        self.configuration.user_name = params["emby"]["user_name"]
        self.configuration.password = None
        self.configuration.access_token = None
        if params["emby"]["password"] != None:
            self.configuration.password = params["emby"]["password"]
        #self.configuration.debug = True
        self.log_dir = os.path.join('/workspace/config', LOG_DIR)
        self.configuration.logger_file = os.path.join(self.log_dir, DEBUG_LOG)
        logger.secret(self.configuration.host)
        logger.secret(self.configuration.api_key['api_key'])
        try:
            self.EmbyServer = ApiClient(self.configuration)
        except Unauthorized:
            raise Failed("Emby Error: Emby API Key is invalid")
        except ValueError as e:
            raise Failed(f"Emby Error: {e}")
        except (requests.exceptions.ConnectionError, ParseError):
            logger.stacktrace()
            raise Failed("Emby Error: Emby url is invalid")
        self.Emby = None
        library_names = []
        library_results = embyapi.LibraryServiceApi(self.EmbyServer).get_library_mediafolders()
        #print(library_results)
        for s in library_results.items:
            library_names.append(s.name)
            #print("DEBUG:: s.name ==", s.name)
            if s.name == params["name"]:
                self.Emby = s
                break
        if not self.Emby:
            raise Failed(f"Emby Error: Emby Library '{params['name']}' not found. Options: {library_names}")
        if self.Emby.collection_type in ["movies", "tvshows"]:
            self.type = self.Emby.collection_type.capitalize()
        else:
            raise Failed(f"Emby Error: Emby Library must be a Movies or TV Shows library")

        self.user_id = None
        users = embyapi.UserServiceApi(self.EmbyServer).get_users_public()
        for user in users:
            if user.name == self.configuration.user_name: 
                self.user_id = user.id
        
        if self.configuration.password:
            self.adminConfiguration = embyapi.Configuration()
            body = {
                 "Username": f"{self.configuration.user_name}",
                 "Pw": f"{self.configuration.password}"
            }
            x_emby_authorization = f"Emby UserId={self.user_id},Client=Emby-Meta-Manager,Device=Swagger-Codegen,DeviceId=123456,Version=1.1.0"
            userAuth = embyapi.UserServiceApi(self.EmbyServer).post_users_authenticatebyname(body, x_emby_authorization)
            self.adminConfiguration.access_token = userAuth.access_token

            self.adminConfiguration.host = params["emby"]["url"]
            self.adminConfiguration.api_key['api_key'] = self.adminConfiguration.access_token
            try:
                self.EmbyAdminServer = ApiClient(self.adminConfiguration)
            except Unauthorized:
                raise Failed("Emby Error: Emby API Key is invalid")
            except ValueError as e:
                raise Failed(f"Emby Error: {e}")
            except (requests.exceptions.ConnectionError, ParseError):
                logger.stacktrace()
                raise Failed("Emby Error: Emby url is invalid")

        self._users = users
        self._all_items = []
        self.is_movie = self.type == "Movies"
        self.is_show = self.type == "Series"
        self.is_music = self.type == "music"
        self.is_other = self.type == "other"
        #if self.is_other and self.type == "Movie":
        #    self.type = "Video"
        #if not self.is_music and self.update_blank_track_titles:
        #    self.update_blank_track_titles = False
        #    logger.error(f"update_blank_track_titles library operation only works with music libraries")
        self.fields = 'Budget,CanDelete,Chapters,ChildCount,DateCreated,DisplayOrder,ExternalUrls,ForcedSortName,Genres,HomePageUrl,IndexOptions,MediaStreams,OfficialRating,Overview,ParentId,Path,People,ProviderIds,PrimaryImageAspectRatio,Revenue,SortName,Studios,Taglines'

        if self.tmdb_collections and self.is_show:
            self.tmdb_collections = None
            logger.error("Config Error: tmdb_collections only work with Movie Libraries.")

    #TODO: Adopt for Emby
    def notify(self, text, collection=None, critical=True):
        self.config.notify(text, server=self.PlexServer.friendlyName, library=self.name, collection=collection, critical=critical)

    def set_server_preroll(self, preroll):
        self.PlexServer.settings.get('cinemaTrailersPrerollID').set(preroll)
        self.PlexServer.settings.save()

    def get_all_collections(self):
        #fields  = self.fields
        #fields = 'Overview,ProviderIds,ChildCount,Studios'
        collections = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id,
                    recursive=True, include_item_types='boxset')
        collections = collections.items
        return collections

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def search(self, title=None, libtype=None, sort=None, maxresults=None, **kwargs):
        results = []
        if libtype == 'collection':
            if title:
                results = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id,
                    recursive=True, search_term=title, include_item_types='boxset')
        else:
            print("How did we get here?")
        return results

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def exact_search(self, title, libtype=None, year=None):
        if year:
            terms = {"title=": title, "year": year}
        else:
            terms = {"title=": title}
        return self.Emby.search(libtype=libtype, **terms)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def get_labeled_items(self, label):
        return self.Emby.search(label=label)


    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def fetchItem(self, data):
        results = []
        results = embyapi.UserLibraryServiceApi(self.EmbyServer).get_users_by_userid_items_by_id(user_id=self.user_id,
            id=data)
        return results

    def update_item(self, body, id):
        itemResults = embyapi.UserLibraryServiceApi(self.EmbyServer).get_users_by_userid_items_by_id(self.user_id, id)
        # Need to grab results for the specific item so that we include all current values in the POST request.
        # Convert both itemResults and body to dicts, then update itemDict with values from bodyDict, if the value is not null.
        # Build a new BaseItemDTO object and insert itemDict values into said object if values are not null.
        # Post newItem object with all existing data + new data.
        itemDict = itemResults.to_dict()
        bodyDict = body.to_dict()
        itemDict.update( (k,v) for k,v in bodyDict.items() if v is not None)
        newItem = embyapi.BaseItemDto()
        for item in itemDict:
            if itemDict[item] is not None:
                setattr(newItem, item, itemDict[item])
        embyapi.ItemUpdateServiceApi(self.EmbyServer).post_items_by_itemid(newItem, id)

    def get_all(self, collection_level=None, load=False, mapping=False):
        results = []
        if load and collection_level in [None, "show", "artist", "movie"]:
            self._all_items = []
        if self._all_items and collection_level in [None, "show", "artist", "movie"]:
            return self._all_items
        collection_type = collection_level if collection_level else self.Emby.type
        if not collection_level:
            collection_level = self.type
        logger.info(f"Loading All {collection_level.capitalize()} from Library: {self.name}")
        library_id = None
        library_results = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id)
        for s in library_results.items:
            if s.name == self.name:
                library_id = s.id
        #Only grab necessary fields when grabbing all items to map_guids
        if mapping:
            fields = 'ProviderIds'
        else:
            fields = 'ProviderIds'
            #fields = 'CriticRating,CustomRating,CommunityRating,Genres,\
            #LockedFields,OfficialRating,ProviderIds,SortName,Studios'
        results = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id,
                parent_id=library_id, fields=fields)
        logger.info(f"Loaded {len(results.items)} {collection_level.capitalize()}")
        #print(results)
        self._all_items = results
        return results

    def upload_theme(self, collection, url=None, filepath=None):
        key = f"/library/metadata/{collection.ratingKey}/themes"
        if url:
            self.PlexServer.query(f"{key}?url={parse.quote_plus(url)}", method=self.PlexServer._session.post)
        elif filepath:
            self.PlexServer.query(key, method=self.PlexServer._session.post, data=open(filepath, 'rb').read())

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def create_playlist(self, name, items):
        return self.PlexServer.createPlaylist(name, items=items)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def fetchItems(self, key, container_start, container_size):
        return self.Plex.fetchItems(key, container_start=container_start, container_size=container_size)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def moveItem(self, obj, item, after):
        obj.moveItem(item, after=after)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def query(self, method):
        return method()

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def query_data(self, method, data):
        return method(data)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_failed)
    def query_collection(self, item, collection, locked=True, add=True):
        if add:
            item.addCollection(collection, locked=locked)
        else:
            item.removeCollection(collection, locked=locked)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def collection_mode_query(self, collection, data):
        if int(collection.collectionMode) not in collection_mode_keys or collection_mode_keys[int(collection.collectionMode)] != data:
            collection.modeUpdate(mode=data)
            logger.info(f"Collection Mode | data")

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def collection_order_query(self, collection, data):
        collection.sortUpdate(sort=data)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def reload(self, item):
        try:
            results = embyapi.UserLibraryServiceApi(self.EmbyServer).get_users_by_userid_items_by_id(self.user_id, item.id)
            return results
        except (BadRequest, NotFound) as e:
            logger.stacktrace()
            raise Failed(f"Item Failed to Load: {e}")

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def edit_query(self, item, edits, advanced=False):
        if advanced:
            item.editAdvanced(**edits)
        else:
            item.edit(**edits)
        self.reload(item)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def _upload_image(self, item, image):
        try:
            if image.is_poster and image.is_url:
                type_ = 'Primary'
                embyapi.RemoteImageServiceApi(self.EmbyServer).post_items_by_id_remoteimages_download(
                    id=item.id, type=type_, image_url=image.location
                )
            elif image.is_poster:
                type_ = 'Primary'
                with open(image.location, "rb") as image_:
                    b64string = str(base64.b64encode(image_.read())).strip("b'").rstrip("'")
                embyapi.ImageServiceApi(self.EmbyServer).post_items_by_id_images_by_type(b64string, item.id, type_)
            elif image.is_url:
                type_ = 'Backdrop'
                embyapi.RemoteImageServiceApi(self.EmbyServer).post_items_by_id_remoteimages_download(
                    id=item.id, type=type_, image_url=image.location
                )
            else:
                type_ = 'Backdrop'
                with open(image.location, "rb") as image_:
                    b64string = str(base64.b64encode(image_.read())).strip("b'").rstrip("'")
                embyapi.ImageServiceApi(self.EmbyServer).post_items_by_id_images_by_type(b64string, item.id, type_)
        except BadRequest as e:
            item.refresh()
            raise Failed(e)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def upload_file_poster(self, item, image):
        item.uploadPoster(filepath=image)
        self.reload(item)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_failed)
    def get_search_choices(self, search_name, title=True):
        final_search = search_translation[search_name] if search_name in search_translation else search_name
        final_search = show_translation[final_search] if self.is_show and final_search in show_translation else final_search
        try:
            names = []
            choices = {}
            use_title = title and final_search not in ["contentRating", "audioLanguage", "subtitleLanguage", "resolution"]
            for choice in self.Plex.listFilterChoices(final_search):
                if choice.title not in names:
                    names.append(choice.title)
                if choice.key not in names:
                    names.append(choice.key)
                choices[choice.title] = choice.title if use_title else choice.key
                choices[choice.key] = choice.title if use_title else choice.key
                choices[choice.title.lower()] = choice.title if use_title else choice.key
                choices[choice.key.lower()] = choice.title if use_title else choice.key
            return choices, names
        except NotFound:
            logger.debug(f"Search Attribute: {final_search}")
            raise Failed(f"Plex Error: plex_search attribute: {search_name} not supported")

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def get_tags(self, tag):
        return self.Plex.listFilterChoices(field=tag)

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_plex)
    def _query(self, key, post=False, put=False):
        if post:                method = self.Plex._server._session.post
        elif put:               method = self.Plex._server._session.put
        else:                   method = None
        return self.Plex._server.query(key, method=method)

    @property
    def users(self):
        if not self._users:
            users = []
            for user in self.PlexServer.myPlexAccount().users():
                if self.PlexServer.machineIdentifier in [s.machineIdentifier for s in user.servers]:
                    users.append(user.title)
            self._users = users
        return self._users

    def create_collection(self, collection, item):
        if isinstance(item, list):
            id_string = ''
            for i in item:
                id_string += i.id + ','
            embyapi.CollectionServiceApi(self.EmbyServer).post_collections(name=collection, ids=id_string)
        if isinstance(item, int):
            embyapi.CollectionServiceApi(self.EmbyServer).post_collections(name=collection, ids=item)

    def delete_collection(self, collection):
        embyapi.LibraryServiceApi(self.EmbyAdminServer).delete_items_by_id(collection.id)

    def alter_collection(self, collection_id, item, smart_label_collection=False, add=True):
        #TODO: Wrap in try/catch/except
        if isinstance(item, list):
            id_string = ''
            for i in item:
                id_string += i.id + ','
            embyapi.CollectionServiceApi(self.EmbyServer).post_collections_by_id_items(id=collection_id, ids=id_string)
        if isinstance(item, int):
            print("How did we get here?")

    def move_item(self, collection, item, after=None):
        key = f"{collection.key}/items/{item}/move"
        if after:
            key += f"?after={after}"
        self._query(key, put=True)

    def smart_label_check(self, label):
        return label in [la.title for la in self.get_tags("label")]

    def test_smart_filter(self, uri_args):
        logger.debug(f"Smart Collection Test: {uri_args}")
        test_items = self.get_filter_items(uri_args)
        if len(test_items) < 1:
            raise Failed(f"Plex Error: No items for smart filter: {uri_args}")

    def create_smart_collection(self, title, smart_type, uri_args):
        self.test_smart_filter(uri_args)
        args = {
            "type": smart_type,
            "title": title,
            "smart": 1,
            "sectionId": self.Plex.key,
            "uri": self.build_smart_filter(uri_args)
        }
        self._query(f"/library/collections{utils.joinArgs(args)}", post=True)

    def create_blank_collection(self, title):
        args = {
            "type": 1 if self.is_movie else 2 if self.is_show else 8,
            "title": title,
            "smart": 0,
            "sectionId": self.Plex.key,
            "uri": f"{self.PlexServer._uriRoot()}/library/metadata"
        }
        self._query(f"/library/collections{utils.joinArgs(args)}", post=True)

    def get_smart_filter_from_uri(self, uri):
        smart_filter = parse.parse_qs(parse.urlparse(uri.replace("/#!/", "/")).query)["key"][0]
        args = smart_filter[smart_filter.index("?"):]
        return self.build_smart_filter(args), int(args[args.index("type=") + 5:args.index("type=") + 6])

    def build_smart_filter(self, uri_args):
        return f"{self.PlexServer._uriRoot()}/library/sections/{self.Plex.key}/all{uri_args}"

    def update_smart_collection(self, collection, uri_args):
        self.test_smart_filter(uri_args)
        self._query(f"/library/collections/{collection.ratingKey}/items{utils.joinArgs({'uri': self.build_smart_filter(uri_args)})}", put=True)

    def smart_filter(self, collection):
        smart_filter = self.get_collection(collection).content
        return smart_filter[smart_filter.index("?"):]

    def collection_visibility(self, collection):
        try:
            attrs = self._query(f"/hubs/sections/{self.Plex.key}/manage?metadataItemId={collection.ratingKey}")[0].attrib
            return {
                "library": utils.cast(bool, attrs.get("promotedToRecommended", "0")),
                "home": utils.cast(bool, attrs.get("promotedToOwnHome", "0")),
                "shared": utils.cast(bool, attrs.get("promotedToSharedHome", "0"))
            }
        except IndexError:
            return {"library": False, "home": False, "shared": False}

    def collection_visibility_update(self, collection, visibility=None, library=None, home=None, shared=None):
        if visibility is None:
            visibility = self.collection_visibility(collection)
        key = f"/hubs/sections/{self.Plex.key}/manage?metadataItemId={collection.ratingKey}"
        key += f"&promotedToRecommended={1 if (library is None and visibility['library']) or library else 0}"
        key += f"&promotedToOwnHome={1 if (home is None and visibility['home']) or home else 0}"
        key += f"&promotedToSharedHome={1 if (shared is None and visibility['shared']) or shared else 0}"
        self._query(key, post=True)

    def get_playlist(self, title):
        try:
            return self.PlexServer.playlist(title)
        except NotFound:
            raise Failed(f"Plex Error: Playlist {title} not found")

    def validate_collections(self, collections):
        valid_collections = []
        for collection in collections:
            try:                                        valid_collections.append(self.get_collection(collection))
            except Failed as e:                         logger.error(e)
        if len(valid_collections) == 0:
            raise Failed(f"Collection Error: No valid Plex Collections in {collections}")
        return valid_collections

    def get_rating_keys(self, method, data):
        items = []
        if method == "plex_all":
            logger.info(f"Processing Plex All {data.capitalize()}s")
            items = self.get_all(collection_level=data)
        elif method == "plex_pilots":
            logger.info(f"Processing Plex Pilot {data.capitalize()}s")
            items = []
            for item in self.get_all():
                try:
                    items.append(item.episode(season=1, episode=1))
                except NotFound:
                    logger.warning(f"Plex Warning: {item.title} has no Season 1 Episode 1 ")
        elif method == "plex_search":
            logger.info(data[1])
            items = self.get_filter_items(data[2])
        elif method == "plex_collectionless":
            good_collections = []
            logger.info(f"Processing Plex Collectionless")
            logger.info("Collections Excluded")
            for col in self.get_all_collections():
                keep_collection = True
                for pre in data["exclude_prefix"]:
                    if col.title.startswith(pre) or (col.titleSort and col.titleSort.startswith(pre)):
                        keep_collection = False
                        logger.info(f"{col.title} excluded by prefix match {pre}")
                        break
                if keep_collection:
                    for ext in data["exclude"]:
                        if col.title == ext or (col.titleSort and col.titleSort == ext):
                            keep_collection = False
                            logger.info(f"{col.title} excluded by exact match")
                            break
                if keep_collection:
                    logger.info(f"Collection Passed: {col.title}")
                    good_collections.append(col)
            logger.info("")
            logger.info("Collections Not Excluded (Items in these collections are not added to Collectionless)")
            for col in good_collections:
                logger.info(col.title)
            collection_indexes = [c.index for c in good_collections]
            all_items = self.get_all()
            for i, item in enumerate(all_items, 1):
                logger.ghost(f"Processing: {i}/{len(all_items)} {item.title}")
                add_item = True
                self.reload(item)
                for collection in item.collections:
                    if collection.id in collection_indexes:
                        add_item = False
                        break
                if add_item:
                    items.append(item)
            logger.info(f"Processed {len(all_items)} {self.type}s")
        else:
            raise Failed(f"Plex Error: Method {method} not supported")
        if len(items) > 0:
            ids = [(item.ratingKey, "ratingKey") for item in items]
            logger.debug("")
            logger.debug(f"{len(ids)} Keys Found: {ids}")
            return ids
        else:
            raise Failed("Plex Error: No Items found in Plex")

    def get_collection(self, data):
        if isinstance(data, int):
            return self.fetchItem(data)
        elif isinstance(data, Collection):
            return data
        else:
            cols = self.search(title=str(data), libtype="collection")
            for d in cols.items:
                if d.name == data:
                    return self.fetchItem(d.id) 
                    #return d
            logger.debug("")
            for d in cols.items:
                logger.debug(f"Found: {d.name}")
            logger.debug(f"Looking for: {data}")
        raise Failed(f"Plex Error: Collection {data} not found")

    def get_collection_id_and_items(self, collection, smart_label_collection):
        if collection:
            collections = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id,
                recursive=True, search_term=collection, include_item_types='boxset')
            for c in collections.items:
                if c.name == collection:
                    collection_id = c.id
                    results = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id,
                        parent_id=collection_id)
                    return collection_id, results.items
            else:
                return None, []
        else:
            return None, []

    def get_collection_name_and_items(self, collection, smart_label_collection):
        name = collection.title if isinstance(collection, (Collection, Playlist)) else str(collection)
        collection_id, collection_items = self.get_collection_id_and_items(collection, smart_label_collection)
        return name, collection_id, collection_items

    def get_collection_id(self, collection):
        #fields = self.fields
        #fields = 'ProviderIds,SortName'
        if collection:
            collections = embyapi.ItemsServiceApi(self.EmbyServer).get_users_by_userid_items(user_id=self.user_id,
                recursive=True, search_term=collection, include_item_types='boxset')
            for c in collections.items:
                if c.name == collection:
                    collection_id = c.id
                    return collection_id
        else:
            raise Failed("Emby Error: Unable to find Collection ID")


    def get_filter_items(self, uri_args):
        key = f"/library/sections/{self.Plex.key}/all{uri_args}"
        logger.debug(key)
        return self.Plex._search(key, None, 0, plexapi.X_PLEX_CONTAINER_SIZE)

    def get_tmdb_from_map(self, item):
        return self.movie_rating_key_map[item.id] if item.id in self.movie_rating_key_map else None

    def get_tvdb_from_map(self, item):
        return self.show_rating_key_map[item.id] if item.id in self.show_rating_key_map else None

    def search_item(self, data, year=None):
        kwargs = {}
        if year is not None:
            kwargs["year"] = year
        for d in self.search(title=str(data), **kwargs):
            if d.title == data:
                return d
        return None

    def edit_item(self, item, name, item_type, edits, advanced=False):
        if len(edits) > 0:
            logger.debug(f"Details Update: {edits}")
            try:
                self.edit_query(item, edits, advanced=advanced)
                if advanced and ("languageOverride" in edits or "useOriginalTitle" in edits):
                    self.query(item.refresh)
                logger.info(f"{item_type}: {name}{' Advanced' if advanced else ''} Details Update Successful")
                return True
            except BadRequest:
                logger.stacktrace()
                logger.error(f"{item_type}: {name}{' Advanced' if advanced else ''} Details Update Failed")
        return False

    def edit_tags(self, attr, obj, add_tags=None, remove_tags=None, sync_tags=None, do_print=True):
        display = ""
        final = ""
        key = builder.filter_translation[attr] if attr in builder.filter_translation else attr
        attr_display = attr.replace("_", " ").title()
        attr_call = attr_display.replace(" ", "")
        if add_tags or remove_tags or sync_tags is not None:
            _add_tags = add_tags if add_tags else []
            _remove_tags = [t.lower() for t in remove_tags] if remove_tags else []
            _sync_tags = [t.lower() for t in sync_tags] if sync_tags else []
            try:
                self.reload(obj)
                _item_tags = [item_tag.tag.lower() for item_tag in getattr(obj, key)]
            except BadRequest:
                _item_tags = []
            _add = [f"{t[:1].upper()}{t[1:]}" for t in _add_tags + _sync_tags if t.lower() not in _item_tags]
            _remove = [t for t in _item_tags if (sync_tags is not None and t not in _sync_tags) or t in _remove_tags]
            if _add:
                self.query_data(getattr(obj, f"add{attr_call}"), _add)
                display += f"+{', +'.join(_add)}"
            if _remove:
                self.query_data(getattr(obj, f"remove{attr_call}"), _remove)
                display += f"-{', -'.join(_remove)}"
            final = f"{obj.title[:25]:<25} | {attr_display} | {display}" if display else display
            if do_print and final:
                logger.info(final)
        return final

    def find_assets(self, item, name=None, upload=True, overlay=None, folders=None, create=None):
        itemType = item.type
        if itemType in ["Movie", "MusicArtist", "Series"]:
            path_test = str(item.path)
            if not os.path.dirname(path_test):
                path_test = path_test.replace("\\", "/")
            name = os.path.basename(os.path.dirname(path_test) if itemType in ["Movie"] else path_test)
        elif itemType in ["BoxSet"]:
            name = name if name else item.name
        else:
            return None, None, None
        if not folders:
            folders = self.asset_folders
        if not create:
            create = self.create_asset_folders
        found_folder = None
        poster = None
        background = None
        for ad in self.asset_directory:
            item_dir = None
            if folders:
                if os.path.isdir(os.path.join(ad, name)):
                    item_dir = os.path.join(ad, name)
                else:
                    for n in range(1, self.asset_depth + 1):
                        new_path = ad
                        for i in range(1, n + 1):
                            new_path = os.path.join(new_path, "*")
                        matches = util.glob_filter(os.path.join(new_path, name))
                        if len(matches) > 0:
                            item_dir = os.path.abspath(matches[0])
                            break
                if item_dir is None:
                    continue
                found_folder = item_dir
                poster_filter = os.path.join(item_dir, "poster.*")
                background_filter = os.path.join(item_dir, "background.*")
            else:
                poster_filter = os.path.join(ad, f"{name}.*")
                background_filter = os.path.join(ad, f"{name}_background.*")

            poster_matches = util.glob_filter(poster_filter)
            if len(poster_matches) > 0:
                poster = ImageData("asset_directory", os.path.abspath(poster_matches[0]), prefix=f"{item.name}'s ", is_url=False)

            background_matches = util.glob_filter(background_filter)
            if len(background_matches) > 0:
                background = ImageData("asset_directory", os.path.abspath(background_matches[0]), prefix=f"{item.name}'s ", is_poster=False, is_url=False)

            if item_dir and self.dimensional_asset_rename and (not poster or not background):
                for file in util.glob_filter(os.path.join(item_dir, "*.*")):
                    if file.lower().endswith((".jpg", ".png", ".jpeg")):
                        image = Image.open(file)
                        _w, _h = image.size
                        image.close()
                        if not poster and _h >= _w:
                            new_path = os.path.join(os.path.dirname(file), f"poster{os.path.splitext(file)[1].lower()}")
                            os.rename(file, new_path)
                            poster = ImageData("asset_directory", os.path.abspath(new_path), prefix=f"{item.name}'s ", is_url=False)
                        elif not background and _w > _h:
                            new_path = os.path.join(os.path.dirname(file), f"background{os.path.splitext(file)[1].lower()}")
                            os.rename(file, new_path)
                            background = ImageData("asset_directory", os.path.abspath(new_path), prefix=f"{item.name}'s ", is_poster=False, is_url=False)
                        if poster and background:
                            break

            if poster or background:
                if upload:
                    self.upload_images(item, poster=poster, background=background, overlay=overlay)
                else:
                    return poster, background, item_dir
            if isinstance(item, Show):
                missing_seasons = ""
                missing_episodes = ""
                found_season = False
                found_episode = False
                for season in self.query(item.seasons):
                    season_name = f"Season{'0' if season.seasonNumber < 10 else ''}{season.seasonNumber}"
                    if item_dir:
                        season_poster_filter = os.path.join(item_dir, f"{season_name}.*")
                        season_background_filter = os.path.join(item_dir, f"{season_name}_background.*")
                    else:
                        season_poster_filter = os.path.join(ad, f"{name}_{season_name}.*")
                        season_background_filter = os.path.join(ad, f"{name}_{season_name}_background.*")
                    season_poster = None
                    season_background = None
                    matches = util.glob_filter(season_poster_filter)
                    if len(matches) > 0:
                        season_poster = ImageData("asset_directory", os.path.abspath(matches[0]), prefix=f"{item.title} Season {season.seasonNumber}'s ", is_url=False)
                        found_season = True
                    elif self.show_missing_season_assets and season.seasonNumber > 0:
                        missing_seasons += f"\nMissing Season {season.seasonNumber} Poster"
                    matches = util.glob_filter(season_background_filter)
                    if len(matches) > 0:
                        season_background = ImageData("asset_directory", os.path.abspath(matches[0]), prefix=f"{item.title} Season {season.seasonNumber}'s ", is_poster=False, is_url=False)
                    if season_poster or season_background:
                        self.upload_images(season, poster=season_poster, background=season_background)
                    for episode in self.query(season.episodes):
                        if episode.seasonEpisode:
                            if item_dir:
                                episode_filter = os.path.join(item_dir, f"{episode.seasonEpisode.upper()}.*")
                            else:
                                episode_filter = os.path.join(ad, f"{name}_{episode.seasonEpisode.upper()}.*")
                            matches = util.glob_filter(episode_filter)
                            if len(matches) > 0:
                                episode_poster = ImageData("asset_directory", os.path.abspath(matches[0]), prefix=f"{item.title} {episode.seasonEpisode.upper()}'s ", is_url=False)
                                found_episode = True
                                self.upload_images(episode, poster=episode_poster)
                            elif self.show_missing_episode_assets:
                                missing_episodes += f"\nMissing {episode.seasonEpisode.upper()} Title Card"

                if (found_season and missing_seasons) or (found_episode and missing_episodes):
                    output = f"Missing Posters for {item.title}"
                    if found_season:
                        output += missing_seasons
                    if found_episode:
                        output += missing_episodes
                    logger.info(output)
            if isinstance(item, Artist):
                missing_assets = ""
                found_album = False
                for album in self.query(item.albums):
                    if item_dir:
                        album_poster_filter = os.path.join(item_dir, f"{album.title}.*")
                        album_background_filter = os.path.join(item_dir, f"{album.title}_background.*")
                    else:
                        album_poster_filter = os.path.join(ad, f"{name}_{album.title}.*")
                        album_background_filter = os.path.join(ad, f"{name}_{album.title}_background.*")
                    album_poster = None
                    album_background = None
                    matches = util.glob_filter(album_poster_filter)
                    if len(matches) > 0:
                        album_poster = ImageData("asset_directory", os.path.abspath(matches[0]), prefix=f"{item.title} Album {album.title}'s ", is_url=False)
                        found_album = True
                    else:
                        missing_assets += f"\nMissing Album {album.title} Poster"
                    matches = util.glob_filter(album_background_filter)
                    if len(matches) > 0:
                        album_background = ImageData("asset_directory", os.path.abspath(matches[0]), prefix=f"{item.title} Album {album.title}'s ", is_poster=False, is_url=False)
                    if album_poster or album_background:
                        self.upload_images(album, poster=album_poster, background=album_background)
                if self.show_missing_season_assets and found_album and missing_assets:
                    logger.info(f"Missing Album Posters for {item.title}{missing_assets}")

        if isinstance(item, (Movie, Show)) and not poster and overlay:
            self.upload_images(item, overlay=overlay)
        if create and folders and not found_folder:
            filename, _ = util.validate_filename(name)
            found_folder = os.path.join(self.asset_directory[0], filename)
            os.makedirs(found_folder, exist_ok=True)
            logger.info(f"Asset Directory Created: {found_folder}")
        elif isinstance(item, (Movie, Show)) and not overlay and folders and not found_folder:
            logger.warning(f"Asset Warning: No asset folder found called '{name}'")
        elif isinstance(item, (Movie, Show)) and not poster and not background and self.show_missing_assets:
            logger.warning(f"Asset Warning: No poster or background found in an assets folder for '{name}'")
        return None, None, found_folder

    def get_ids(self, item):
        tmdb_id = None
        tvdb_id = None
        imdb_id = None
        if self.config.Cache:
            t_id, i_id, guid_media_type, _ = self.config.Cache.query_guid_map(item.id)
            if t_id:
                if "movie" in guid_media_type:
                    tmdb_id = t_id[0]
                else:
                    tvdb_id = t_id[0]
            if i_id:
                imdb_id = i_id[0]
        if not tmdb_id and not tvdb_id:
            tmdb_id = self.get_tmdb_from_map(item)
        if not tmdb_id and not tvdb_id and self.is_show:
            tvdb_id = self.get_tvdb_from_map(item)
        return tmdb_id, tvdb_id, imdb_id

    def get_locked_attributes(self, item, titles=None):
        attrs = {}
        fields = {f.name: f for f in item.fields if f.locked}
        if isinstance(item, (Movie, Show)) and titles and titles.count(item.title) > 1:
            map_key = f"{item.title} ({item.year})"
            attrs["title"] = item.title
            attrs["year"] = item.year
        elif isinstance(item, (Season, Episode, Track)) and item.index:
            map_key = int(item.index)
        else:
            map_key = item.title

        if "title" in fields:
            if isinstance(item, (Movie, Show)):
                tmdb_id, tvdb_id, imdb_id = self.get_ids(item)
                tmdb_item = self.config.TMDb.get_item(item, tmdb_id, tvdb_id, imdb_id, is_movie=isinstance(item, Movie))
                if tmdb_item:
                    attrs["alt_title"] = tmdb_item.title
            elif isinstance(item, (Season, Episode, Track)):
                attrs["title"] = item.title

        def check_field(plex_key, pmm_key, var_key=None):
            if plex_key in fields and pmm_key not in self.metadata_backup["exclude"]:
                if not var_key:
                    var_key = plex_key
                if hasattr(item, var_key):
                    plex_value = getattr(item, var_key)
                    if isinstance(plex_value, list):
                        plex_tags = [t.tag for t in plex_value]
                        if len(plex_tags) > 0 or self.metadata_backup["sync_tags"]:
                            attrs[f"{pmm_key}.sync" if self.metadata_backup["sync_tags"] else pmm_key] = None if not plex_tags else plex_tags[0] if len(plex_tags) == 1 else plex_tags
                    elif isinstance(plex_value, datetime):
                        attrs[pmm_key] = datetime.strftime(plex_value, "%Y-%m-%d")
                    else:
                        attrs[pmm_key] = plex_value

        check_field("titleSort", "sort_title")
        check_field("originalTitle", "original_artist" if self.is_music else "original_title")
        check_field("originallyAvailableAt", "originally_available")
        check_field("contentRating", "content_rating")
        check_field("userRating", "user_rating")
        check_field("audienceRating", "audience_rating")
        check_field("rating", "critic_rating")
        check_field("studio", "record_label" if self.is_music else "studio")
        check_field("tagline", "tagline")
        check_field("summary", "summary")
        check_field("index", "track")
        check_field("parentIndex", "disc")
        check_field("director", "director", var_key="directors")
        check_field("country", "country", var_key="countries")
        check_field("genre", "genre", var_key="genres")
        check_field("writer", "writer", var_key="writers")
        check_field("producer", "producer", var_key="producers")
        check_field("collection", "collection", var_key="collections")
        check_field("label", "label", var_key="labels")
        check_field("mood", "mood", var_key="moods")
        check_field("style", "style", var_key="styles")
        check_field("similar", "similar_artist")
        if self.type in util.advance_tags_to_edit:
            for advance_edit in util.advance_tags_to_edit[self.type]:
                key, options = item_advance_keys[f"item_{advance_edit}"]
                if advance_edit in self.metadata_backup["exclude"] or not hasattr(item, key):
                    continue
                keys = {v: k for k, v in options.items()}
                if keys[getattr(item, key)] not in ["default", "all", "never"]:
                    attrs[advance_edit] = keys[getattr(item, key)]

        def _recur(sub):
            sub_items = {}
            for sub_item in getattr(item, sub)():
                sub_item_key, sub_item_attrs = self.get_locked_attributes(sub_item)
                if sub_item_attrs:
                    sub_items[sub_item_key] = sub_item_attrs
            if sub_items:
                attrs[sub] = sub_items

        if isinstance(item, Show):
            _recur("seasons")
        elif isinstance(item, Season):
            _recur("episodes")
        elif isinstance(item, Artist):
            _recur("albums")
        elif isinstance(item, Album):
            _recur("tracks")

        return map_key, attrs if attrs else None
