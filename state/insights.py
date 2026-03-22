"""
Shared mutable state untuk cache AI insights.
"""

_INSIGHTS_CACHE: dict = {}
_INSIGHTS_CACHE_TTL = 60 * 60
_INSIGHTS_GENERATING: dict[str, bool | str] = {}
