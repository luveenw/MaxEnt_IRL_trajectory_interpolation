"""Explicit calendar-season intervals and buffered sampling-window membership."""
from datetime import datetime, timedelta
import math

SOURCE_URL = 'https://www.climatestotravel.com/climate/brazil/pantanal'
# Source: https://www.climatestotravel.com/climate/brazil/pantanal
# Operational dates approved by the user: mid-month=15; summer ends March 21;
# autumn starts March 22. End dates below are exclusive; summer crosses years.
DEFAULT_SEASONS = (
    dict(name='winter', start_month=5, start_day=15, end_month=8, end_day=15,
         description='Dry with rare showers.'),
    dict(name='spring', start_month=8, start_day=15, end_month=11, end_day=15,
         description='Hottest season of the year.'),
    dict(name='summer', start_month=11, start_day=15, end_month=3, end_day=22,
         description='Hot, humid, with intense downpours or thunderstorms.'),
    dict(name='autumn', start_month=3, start_day=22, end_month=5, end_day=15,
         description='Temperature and rainfall decrease; rivers return to their banks.'),
)


def validate_seasons(seasons):
    names = [s['name'] for s in seasons]
    if len(names) != 4 or set(names) != {'winter','spring','summer','autumn'}:
        raise ValueError('Require exactly winter, spring, summer and autumn')
    for s in seasons:
        if not s['name'].isascii() or not s['name'].replace('_','').isalnum():
            raise ValueError('Season names must be ASCII letters/numbers/underscores')
        for prefix in ('start', 'end'):
            datetime(2001, s[prefix+'_month'], s[prefix+'_day'])
        if (s['start_month'],s['start_day']) == (s['end_month'],s['end_day']):
            raise ValueError('Season must have distinct start and end dates')
    for year in (2000,2001):
        at = datetime(year,1,1)
        while at.year == year:
            count = sum(start <= at < end for s in seasons for y in (year-1,year)
                        for start,end in [season_bounds(s,y)])
            if count != 1:
                raise ValueError('Season definitions must cover each date exactly once')
            at += timedelta(days=1)


def season_bounds(season, year):
    start = datetime(year, season['start_month'], season['start_day'])
    end_pair = season['end_month'],season['end_day']
    start_pair = season['start_month'],season['start_day']
    return start, datetime(year + (end_pair <= start_pair), *end_pair)


def window_seasons(start, end, seasons=DEFAULT_SEASONS, buffer_days=7):
    """Inclusive observation windows must fit within the half-open buffered season."""
    if not math.isfinite(buffer_days) or buffer_days < 0 or end < start:
        raise ValueError('Invalid window or season buffer')
    found=[]
    for season in seasons:
        for year in range(start.year-1,end.year+1):
            lo,hi=season_bounds(season,year)
            blo,bhi=lo-timedelta(days=buffer_days),hi+timedelta(days=buffer_days)
            if blo <= start and end < bhi:
                found.append(dict(season=season['name'],season_year=year,
                    core_start=lo,core_end=hi,buffer_start=blo,buffer_end=bhi))
    return found


def seasons_metadata(seasons, buffer_days, duration_days):
    return dict(schema='pantanal_seasons/1',source_url=SOURCE_URL,
        source_status='Season descriptions verified in the source page on 2026-11-01. Exact boundaries are user-approved operational definitions; the source describes late March and begins autumn in April.',
        boundary_interpretation='Half-open core intervals. Mid-month=15th; summer ends March21 inclusive; autumn starts March22. Season-year is the core start year.',
        membership_rule='Entire inclusive sampling window inside buffered half-open season',
        buffer_days=buffer_days,sampling_duration_days=duration_days,seasons=list(seasons))
