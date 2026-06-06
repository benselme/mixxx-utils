import sqlite3
from sqlite3 import Connection

from tqdm import tqdm

from python_tools.utils.track_utils import (
    BeatGridInfo,
    snap_cue_frame,
)

from python_tools.utils.misc import confirm_config

import python_tools.snap_cues.config as cfg

from python_tools.utils.config import MIXXX_DB
from utils.track_utils import get_fixed_beat_grid


def update_cue(
    cursor_: sqlite3.Cursor, cue_id: int, position: float, length_: float
) -> None:
    cursor_.execute(
        "UPDATE cues SET position = ?, length = ?, label='toto' WHERE id = ?",
        (position, length, cue_id),
    )


def update_beatgrid(cursor_: sqlite3.Cursor, track_id: int, beats: bytes) -> None:
    cursor_.execute(
        "UPDATE library SET played=12, beats = ? where id = ?", (beats, track_id)
    )


if __name__ == "__main__":
    confirm_config(cfg)
    connection = Connection(MIXXX_DB)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    error_log = ""
    lib_rows = list(
        cursor.execute("SELECT id, beats, samplerate, artist, title FROM library")
    )
    for lib_row in tqdm(lib_rows, total=len(lib_rows)):
        cues_rows = list(
            cursor.execute(
                "SELECT id, type, hotcue, position, length from cues where track_id = ?",
                (lib_row["id"],),
            )
        )
        if len(cues_rows) > 0:
            try:
                samplerate = lib_row["samplerate"]
                fixed_beats = get_fixed_beat_grid(lib_row["beats"], samplerate)
                update_beatgrid(cursor, lib_row["id"], fixed_beats)
                beatgrid_info = BeatGridInfo(fixed_beats, samplerate)
                if beatgrid_info.bpm <= 0:
                    error_log += (
                        f"\n Skipping track with invalid BPM ({beatgrid_info.bpm}): "
                        f"{lib_row['artist']} - {lib_row['title']}"
                    )
                    continue

                beat_interval_sec = 60 / beatgrid_info.bpm
                for cue_row in cues_rows:
                    if cue_row["type"] in [1, 2, 6] and (  # hotcue, cue, intro
                        not cfg.IDX_SNAPPED_CUES
                        or cue_row["hotcue"] + 1 in cfg.IDX_SNAPPED_CUES
                    ):
                        new_start_pos = snap_cue_frame(
                            cue_row["position"],
                            samplerate,
                            beatgrid_info.start_sec,
                            beat_interval_sec,
                        )
                        length = cue_row["length"]
                        if length:
                            end_position = new_start_pos + length
                            new_end_position = snap_cue_frame(
                                end_position,
                                samplerate,
                                beatgrid_info.start_sec,
                                beat_interval_sec,
                            )
                            length = new_end_position - new_start_pos
                        update_cue(cursor, cue_row["id"], new_start_pos, length)

            except TypeError:
                error_log += (
                    "\n The following track has cue points defined but no BeatGrid !?: "
                    f"{lib_row['artist']} - {lib_row['title']}"
                )
                pass

    print(error_log)

    connection.commit()
