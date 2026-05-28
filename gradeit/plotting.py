"""Interactive map plotting for a :class:`~gradeit.io.GradeResult`.

Provides :func:`plot_grade_map`, which renders the GPS trace on a folium map
with each segment colored by its grade. Useful for spot-checking bridges and
overpasses, which show up as sharp negative grade spikes on the raw profile
where the bare-earth DEM dips into the valley underneath.

folium is an optional dependency; install via ``pip install gradeit[plot]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal, Optional, Tuple

import numpy as np

from gradeit.exceptions import InvalidInputError, MissingDependencyError
from gradeit.io import GradeResult

if TYPE_CHECKING:
    import folium

# Diverging red→yellow→green palette: steep negative grade → red, flat → yellow,
# steep positive grade → green. Reads naturally as "going down" vs "going up"
# without being so saturated that mid-range segments disappear into the tiles.
_DEFAULT_COLORS = ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"]

GradeChoice = Literal["auto", "raw", "filtered", "both"]


def plot_grade_map(
    result: GradeResult,
    *,
    grade: GradeChoice = "auto",
    grade_range_pct: Optional[Tuple[float, float]] = None,
    weight: int = 5,
    opacity: float = 0.85,
    tiles: str = "OpenStreetMap",
    show_endpoints: bool = True,
) -> "folium.Map":
    """Render the trace on an interactive folium map, colored by grade.

    Each segment between consecutive coordinates is drawn as a short polyline
    colored by the grade of that segment. Hovering reveals the segment's
    array index (e.g. ``result.grade_dec[i]``), grade, elevation, and segment
    length, so it is easy to find bridge/overpass artifacts where the
    bare-earth DEM dips into the valley underneath -- and to jump straight to
    the corresponding row in the underlying data.

    Parameters
    ----------
    result:
        The output of :func:`gradeit.gradeit`.
    grade:
        Which grade profile to plot.

        * ``"auto"`` (default) -- plot both raw and filtered as toggleable
          layers when filtering ran, else just raw.
        * ``"raw"`` -- always plot the raw, unfiltered grade.
        * ``"filtered"`` -- plot only the filtered grade (requires that
          ``gradeit()`` was called with a filter).
        * ``"both"`` -- plot raw and filtered as toggleable layers (requires
          that ``gradeit()`` was called with a filter).
    grade_range_pct:
        ``(vmin, vmax)`` percent-grade limits for the color scale. Grades
        beyond this range clamp to the extreme colors. If ``None``, the range
        is set symmetrically around 0 using the trace's largest absolute
        grade, so the midpoint color always means "flat".
    weight:
        Stroke width of each polyline segment, in pixels.
    opacity:
        Stroke opacity in ``[0, 1]``.
    tiles:
        Base map tile source passed through to ``folium.Map`` (e.g.
        ``"OpenStreetMap"``, ``"CartoDB positron"``).
    show_endpoints:
        If true, add Start/End markers at the first and last coordinates.

    Returns
    -------
    folium.Map
        A folium map fitted to the trace bounds, with a color scale legend
        and (when more than one layer is shown) a layer control.

    Raises
    ------
    MissingDependencyError
        If folium is not installed.
    InvalidInputError
        If the result has fewer than 2 coordinates or the requested layer
        is not available.
    """
    try:
        import folium
        from branca.colormap import LinearColormap
    except ImportError as e:
        raise MissingDependencyError(
            "folium is required for plot_grade_map(); install it with 'pip install gradeit[plot]'."
        ) from e

    coords = result.coordinates
    if len(coords) < 2:
        raise InvalidInputError("plot_grade_map() needs at least 2 coordinates.")

    layers = _select_layers(grade, result)

    lats = np.fromiter((c.latitude for c in coords), dtype=float, count=len(coords))
    lons = np.fromiter((c.longitude for c in coords), dtype=float, count=len(coords))

    vmin_pct, vmax_pct = _resolve_value_range(grade_range_pct, layers)
    cmap = LinearColormap(
        colors=_DEFAULT_COLORS,
        vmin=vmin_pct,
        vmax=vmax_pct,
        caption="Grade (%)",
    )

    elev_for_tooltip = (
        result.elevation_ft_filtered
        if result.elevation_ft_filtered is not None
        else result.elevation_ft
    )

    m = folium.Map(tiles=tiles)
    m.fit_bounds(
        [
            [float(np.nanmin(lats)), float(np.nanmin(lons))],
            [float(np.nanmax(lats)), float(np.nanmax(lons))],
        ]
    )

    multi_layer = len(layers) > 1
    for label, grade_arr in layers:
        # Each layer becomes a FeatureGroup when there is more than one, so the
        # LayerControl can toggle them. Otherwise we add directly to the map.
        container = folium.FeatureGroup(name=label, show=True) if multi_layer else m
        _add_segments(
            container,
            lats=lats,
            lons=lons,
            grade_arr=grade_arr,
            elevation_arr=elev_for_tooltip,
            distances_ft=result.distances_ft,
            label=label,
            cmap=cmap,
            vmin_pct=vmin_pct,
            vmax_pct=vmax_pct,
            weight=weight,
            opacity=opacity,
        )
        if multi_layer:
            container.add_to(m)

    if show_endpoints:
        folium.Marker(
            location=(float(lats[0]), float(lons[0])),
            popup="Start",
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
        ).add_to(m)
        folium.Marker(
            location=(float(lats[-1]), float(lons[-1])),
            popup="End",
            icon=folium.Icon(color="red", icon="stop", prefix="fa"),
        ).add_to(m)

    cmap.add_to(m)
    if multi_layer:
        folium.LayerControl(collapsed=False).add_to(m)

    return m


def _select_layers(grade: GradeChoice, result: GradeResult) -> List[Tuple[str, np.ndarray]]:
    has_filtered = result.grade_dec_filtered is not None
    if grade == "auto":
        grade = "both" if has_filtered else "raw"

    if grade in ("filtered", "both") and not has_filtered:
        raise InvalidInputError(
            f"plot_grade_map(grade={grade!r}) requires a filtered grade profile; "
            "rerun gradeit() with an elevation_filter."
        )

    if grade == "raw":
        return [("Raw grade", result.grade_dec)]
    if grade == "filtered":
        # mypy: narrowed by the has_filtered check above
        assert result.grade_dec_filtered is not None
        return [("Filtered grade", result.grade_dec_filtered)]
    if grade == "both":
        assert result.grade_dec_filtered is not None
        # Put filtered first so it shows on top of the raw layer by default.
        return [
            ("Filtered grade", result.grade_dec_filtered),
            ("Raw grade", result.grade_dec),
        ]
    raise InvalidInputError(
        f"plot_grade_map(grade={grade!r}) is not one of 'auto', 'raw', 'filtered', 'both'."
    )


def _resolve_value_range(
    grade_range_pct: Optional[Tuple[float, float]],
    layers: List[Tuple[str, np.ndarray]],
) -> Tuple[float, float]:
    if grade_range_pct is not None:
        vmin, vmax = grade_range_pct
        if vmin >= vmax:
            raise InvalidInputError(
                f"grade_range_pct must be (vmin, vmax) with vmin < vmax; got {grade_range_pct!r}."
            )
        return float(vmin), float(vmax)

    all_grades = np.concatenate([g for _, g in layers])
    finite = all_grades[np.isfinite(all_grades)]
    if finite.size == 0:
        return -10.0, 10.0
    # Symmetric around 0 so the midpoint color reliably reads as "flat",
    # regardless of whether the trace is mostly uphill or downhill.
    absmax_pct = max(1.0, float(np.max(np.abs(finite))) * 100.0)
    return -absmax_pct, absmax_pct


def _add_segments(
    container,
    *,
    lats: np.ndarray,
    lons: np.ndarray,
    grade_arr: np.ndarray,
    elevation_arr: np.ndarray,
    distances_ft: np.ndarray,
    label: str,
    cmap,
    vmin_pct: float,
    vmax_pct: float,
    weight: int,
    opacity: float,
) -> None:
    import folium

    n = len(lats)
    for i in range(1, n):
        g_dec = float(grade_arr[i])
        if np.isfinite(g_dec):
            g_pct = g_dec * 100.0
            clamped = min(max(g_pct, vmin_pct), vmax_pct)
            color = cmap(clamped)
            grade_text = f"{g_pct:+.2f}%"
        else:
            color = "#888888"
            grade_text = "n/a"

        elev_text = f"{float(elevation_arr[i]):.1f} ft" if np.isfinite(elevation_arr[i]) else "n/a"
        seg_len_text = f"{float(distances_ft[i]):.1f} ft"

        # `i` is the array index in result.grade_dec / .elevation_ft / .coordinates
        # for the end of this segment, so the tooltip doubles as a lookup key.
        tooltip = folium.Tooltip(
            f"<b>{label}</b><br>"
            f"index: {i} (segment {i - 1}→{i})<br>"
            f"grade: {grade_text}<br>"
            f"elev: {elev_text}<br>"
            f"segment: {seg_len_text}"
        )

        folium.PolyLine(
            locations=[
                (float(lats[i - 1]), float(lons[i - 1])),
                (float(lats[i]), float(lons[i])),
            ],
            color=color,
            weight=weight,
            opacity=opacity,
            tooltip=tooltip,
        ).add_to(container)
