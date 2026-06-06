from dataclasses import dataclass
from math import prod
from re import sub

import pandas as pd
from jellyfish import levenshtein_distance

from .proto import beats_pb2  # type:ignore


def position_frame_to_sec(frame: int, samplerate: float) -> float:
    return frame / (2 * samplerate)


def position_sec_to_frame(time_sec: float, samplerate: float) -> int:
    return round(time_sec * (2 * samplerate))


def get_fixed_beat_grid(beats: bytes, samplerate: int) -> bytes:
    """If the declared first beat is at a position slightly earlier than the beat length,
    it means the first beat is actually at position 0. It happens when using Adjust beatgrid
    in mixxx that the play position will be slightly before 0.

    Return the adjusted beatgrid.
    """
    beatgrid = beats_pb2.BeatGrid()  # type: ignore
    beatgrid.ParseFromString(beats)
    start = beatgrid.first_beat.frame_position
    start_sec = start / samplerate
    beat_length = 60.0 / beatgrid.bpm.bpm
    if -(beat_length * 100 * 0.15) < (start_sec - beat_length) * 100 < 0:
        beatgrid.first_beat.frame_position = 0
    return beatgrid.SerializeToString()


@dataclass
class BeatGridInfo:
    start: int
    start_sec: float
    bpm: float

    def __init__(self, beats: bytes, samplerate: int) -> None:
        beatgrid = beats_pb2.BeatGrid()  # type: ignore
        beatgrid.ParseFromString(beats)
        self.start = beatgrid.first_beat.frame_position
        start_sec = self.start / samplerate
        beat_length = 60.0 / beatgrid.bpm.bpm
        if start_sec < 0:
            start_sec += beat_length

        if start_sec > beat_length:
            start_sec -= beat_length
        self.start_sec = start_sec
        self.bpm = beatgrid.bpm.bpm


def remove_feat(name: str) -> str:
    return sub(r" \(*f(?:ea)?t\. .+", "", name)


def levenshtein_distance_sum(
    row1: pd.Series, row2: pd.Series, col_names: list[str]
) -> int:
    return prod(1 + levenshtein_distance(row1[c], row2[c]) for c in col_names)


def get_closest_matches_indices(
    row: pd.Series,
    search_df: pd.DataFrame,
    col_names: list[str],
    max_distance: int,
    n_results: int,
) -> pd.Index:
    distance_serie = search_df.apply(
        lambda t: levenshtein_distance_sum(t, row, col_names), axis=1
    )
    distance_serie = distance_serie[distance_serie <= max_distance]
    distance_serie = distance_serie.sort_values()
    return distance_serie[:n_results].index


def snap_cue_frame(
    cue_position_frame: int,
    samplerate: float,
    beatgrid_start_sec: float,
    beat_interval_sec: float,
) -> int:
    position_sec = position_frame_to_sec(cue_position_frame, samplerate)
    scaled_position = (position_sec - beatgrid_start_sec) / beat_interval_sec
    snaped_position = round(scaled_position)
    unscaled_position = snaped_position * beat_interval_sec + beatgrid_start_sec
    return position_sec_to_frame(unscaled_position, samplerate)


def guess_inizio_sec(
    hot_cue_frame_pos: int, samplerate: float, bpm: float, beats_per_bar: int
) -> float:
    hot_cue_sec = position_frame_to_sec(hot_cue_frame_pos, samplerate)
    interval_sec = 60 / bpm  # length of a single beat in seconds
    return hot_cue_sec % (beats_per_bar * interval_sec)
