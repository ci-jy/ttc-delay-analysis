import pytest

from ttc_delay.stations import StationMatcher, clean_name


@pytest.fixture(scope="module")
def matcher():
    return StationMatcher()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("KENNEDY BD STATION", ("KENNEDY", "BD")),
        ("KENNEDY BD STATION - P", ("KENNEDY", "BD")),
        ("PIONEER VILLAGE STATIO", ("PIONEER VILLAGE", None)),
        ("KIPLING STATION (ENTER", ("KIPLING", None)),
        ("ST. GEORGE YUS STATION", ("ST GEORGE", "YU")),
        ("ST GEORGE BD/YU STATIO", ("ST GEORGE", None)),
        ("SHEPPARD-YONGE STATION", ("SHEPPARD YONGE", None)),
        ("QUEEN'S PARK STATION", ("QUEENS PARK", None)),
        ("UNION STATION TO KING", ("UNION STATION TO KING", None)),
        ("DUFFERIN STATON", ("DUFFERIN", None)),
        ("EGLINTON STN", ("EGLINTON", None)),
        (None, ("", None)),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


@pytest.mark.parametrize(
    "raw,line,code",
    [
        ("KENNEDY BD STATION", "BD", "BD_KENNEDY"),
        ("KENNEDY SRT STATION", "SRT", "SRT_KENNEDY"),
        ("KENNEDY STATION", "SRT", "SRT_KENNEDY"),
        ("KENNEDY STATION", "BD", "BD_KENNEDY"),
        ("BLOOR STATION", "YU", "YU_BLOOR_YONGE"),
        ("YONGE BD STATION", "BD", "BD_BLOOR_YONGE"),
        ("YONGE SHP STATION", "SHP", "SHP_SHEPPARD_YONGE"),
        ("SHEPPARD STATION", "YU", "YU_SHEPPARD_YONGE"),
        ("SHEPPARD-YONGE STATION", "SHP", "SHP_SHEPPARD_YONGE"),
        ("ST GEORGE YUS STATION", "BD", "YU_ST_GEORGE"),  # the name's hint beats the line field
        ("ST GEORGE STATION", "BD", "BD_ST_GEORGE"),
        ("SPADINA BD STATION", "BD", "BD_SPADINA"),
        ("DOWNSVIEW STATION", "YU", "YU_SHEPPARD_WEST"),
        ("DOWNSVIEW PARK STATION", "YU", "YU_DOWNSVIEW_PARK"),
        ("DUNDAS STATION", "YU", "YU_TMU"),
        ("TMU STATION", "YU", "YU_TMU"),
        ("DUNDAS WEST STATION", "BD", "BD_DUNDAS_WEST"),
        ("EGLINTON WEST STATION", "YU", "YU_CEDARVALE"),
        ("VMC STATION", "YU", "YU_VAUGHAN_MC"),
        ("SCARB CTR STATION", "SRT", "SRT_SCARBOROUGH_CENTRE"),
        ("NORTH YORK CTR STATION", "YU", "YU_NORTH_YORK_CENTRE"),
    ],
)
def test_alias_matches(matcher, raw, line, code):
    m = matcher.match(raw, line)
    assert (m.location_type, m.station_code, m.method) == ("station", code, "alias")


def test_reviewed_fuzzy_match(matcher):
    m = matcher.match("GLENCARIN STATION", "YU")
    assert (m.station_code, m.method) == ("YU_GLENCAIRN", "fuzzy_reviewed")
    assert m.score >= 0.85


def test_unreviewed_fuzzy_match_is_flagged(matcher):
    m = matcher.match("KENEDY BD STATION", "BD")
    assert (m.station_code, m.method) == ("BD_KENNEDY", "fuzzy")


def test_rejected_fuzzy_match_stays_unmatched(matcher):
    m = matcher.match("LAWRENCE E", "SRT")
    assert (m.location_type, m.station_code, m.method) == ("unmatched", None, "fuzzy_rejected")


@pytest.mark.parametrize(
    "raw,location_type",
    [
        ("YONGE UNIVERSITY LINE", "line_wide"),
        ("BLOOR DANFORTH SUBWAY", "line_wide"),
        ("TORONTO TRANSIT COMMIS", "line_wide"),
        ("GREENWOOD YARD", "facility"),
        ("WILSON HOSTLER", "facility"),
        ("DAVISVILLE BUILD UP", "facility"),
        ("UNION STATION TO KING", "segment"),
        ("ISLINGTON AND JANE", "segment"),
        ("ZZZ NOWHERE", "unmatched"),
    ],
)
def test_non_station_locations(matcher, raw, location_type):
    assert matcher.match(raw, "YU").location_type == location_type


def test_reference_files_are_consistent(matcher):
    lines = {s.line_code for s in matcher.stations}
    assert lines == {"YU", "BD", "SRT", "SHP"}
    assert len(matcher.stations) == len(matcher.by_code)
    # every station name resolves to itself on its own line
    for st in matcher.stations:
        assert matcher.match(st.station_name.upper() + " STATION", st.line_code).station_code == st.station_code
