from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial import cKDTree
from shapely import minimum_rotated_rectangle, unary_union
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point
from sklearn.cluster import DBSCAN
from tqdm import tqdm


def rescale_geometries(
    gdf: gpd.GeoDataFrame, scale_factor: float = 250.0
) -> gpd.GeoDataFrame:
    """
    Rescale all geometries in the GeoDataFrame by dividing coordinates by the scale factor.

    Parameters:
    - gdf: GeoDataFrame with geometries to rescale.
    - scale_factor: Factor by which to divide coordinates (default is 250).

    Returns:
    - A new GeoDataFrame with rescaled geometries.
    """
    # Affine transform: [a, b, d, e, xoff, yoff]
    # For scaling only: a = 1/scale, e = 1/scale
    transform = [1 / scale_factor, 0, 0, 1 / scale_factor, 0, 0]
    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].apply(
        lambda geom: affine_transform(geom, transform)
    )
    return gdf


def get_size(bounds) -> dict[str, float]:
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    return {"width": width, "height": height}


def get_aspect_ratio(row: pd.Series) -> float:
    bounds = row.geometry.bounds
    size = get_size(bounds)
    width, height = size["width"], size["height"]

    if width == 0 or height == 0:
        return 0
    return max(width / height, height / width)


def is_big(row: pd.Series) -> bool:
    bounds = row.geometry.bounds
    size = get_size(bounds)
    if size["width"] > 1 or size["height"] > 1:
        return False
    return True


def find_rectangles(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    linestring_filter = gdf.geometry_type == "LINESTRING"
    subclasses_filter = gdf["SubClasses"] == "AcDbEntity:AcDbPolyline"

    polylines = gdf.loc[linestring_filter & subclasses_filter, :]

    polylines["aspect_ratio"] = polylines.apply(get_aspect_ratio, axis=1)
    aspect_ratio_filter = np.isclose(polylines["aspect_ratio"], 2.0)
    size_filter = polylines.apply(is_big, axis=1)
    candidate_rectangles = polylines.loc[aspect_ratio_filter & size_filter, :]
    return candidate_rectangles


def get_door_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf["geometry"] = gdf.geometry.centroid
    gdf["geometry_type"] = "POINT"

    return gdf


def get_door_rectangle_clusters(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    C = np.c_[gdf["geometry"].x.values, gdf["geometry"].y.values]
    tree = cKDTree(C)
    d1, _ = tree.query(C, k=2)
    nn_med = np.median(d1[:, 1])
    eps = float(nn_med * 1.6)
    min_samples = 2

    db = DBSCAN(eps=eps, min_samples=min_samples)
    labels_cl = db.fit_predict(C)
    gdf["cluster"] = labels_cl

    sizes = gdf.loc[gdf["cluster"] >= 0].groupby("cluster").size()
    valid_clusters = sizes[(sizes >= 2) & (sizes <= 6)].index
    gdf = gdf.loc[gdf["cluster"].isin(valid_clusters)].copy()

    return gdf


def label_rectangles(gdf: gpd.GeoDataFrame) -> gpd.GeoSeries:
    pass


def detect_rectangles_and_label(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Detect small rectangular polylines near doorways and label them with room text.

    Parameters:
    - gdf: GeoDataFrame containing all geometries.

    Returns:
    - GeoDataFrame of detected rectangles with room text labels.
    """
    # Filter candidate rectangular polylines
    candidates = gdf.loc[
        (gdf.geometry_type == "LINESTRING")
        & (gdf["SubClasses"] == "AcDbEntity:AcDbPolyline")
    ]

    # Heuristic: small area and 4-5 vertices
    rectangles = []

    for idx, row in tqdm(
        candidates.iterrows(), total=len(candidates), desc="Filtering rectangles"
    ):
        coords = list(row.geometry.coords)
        if len(coords) in (4, 5):
            # Assumes that rectangles are orthogonal to coordinate system
            bounds = row.geometry.bounds
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]

            area = width * height
            if 0.01 < area < 2.0:
                pass

            aspect_ratio = max(width / height, height / width)

            if 1.5 < aspect_ratio < 2.5:
                rectangles.append((idx, row.geometry.centroid))

    # Create GeoDataFrame of centroids
    centroids = [geom for _, geom in rectangles]
    rect_gdf = gpd.GeoDataFrame(geometry=centroids, crs=gdf.crs)

    # Attach room text from nearest label point
    points_gdf = gdf[
        (gdf.geometry_type == "POINT")
        & (gdf["SubClasses"] == "AcDbEntity:AcDbText:AcDbText")
    ]
    rect_gdf["room_text"] = None
    for idx, rect in tqdm(
        rect_gdf.iterrows(), total=len(rect_gdf), desc="Labeling rectangles"
    ):
        nearest_idx = points_gdf.distance(rect.geometry).idxmin()
        rect_gdf.at[idx, "room_text"] = points_gdf.at[nearest_idx, "Text"]

    # Annotate metadata
    rect_gdf["Layer"] = "DOORWAY_RECTANGLE"
    rect_gdf["PaperSpace"] = 0
    rect_gdf["SubClasses"] = "InferredDoorwayRectangle"
    rect_gdf["Linetype"] = None
    rect_gdf["EntityHandle"] = None
    rect_gdf["geometry_type"] = "POINT"
    rect_gdf["__source__"] = "rectangle_detection"

    return rect_gdf


def plot_geometries(gdf: gpd.GeoDataFrame, output_html: Path | str) -> None:
    """
    Plot geometries into an interactive HTML file using Plotly.

    The output groups features by ``geometry_type`` and draws points, lines,
    and polygon exteriors with simple defaults. Non-geometry columns are
    rendered as hover text.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Input features. Must contain ``geometry`` and ``geometry_type`` columns.
    output_html : path-like
        Destination path for the generated HTML file.

    Returns
    -------
    None

    Notes
    -----
    - The figure uses an equal-scale axis (``yaxis_scaleanchor='x'``).
    - ``plotly`` is used directly without specifying a theme to keep
      dependencies light.
    """
    fig = go.Figure()
    geometry_types = gdf.geometry_type.unique()

    for geom_type in geometry_types:
        layer = gdf[gdf["geometry_type"] == geom_type]
        if layer.empty:
            continue
        elif geom_type in {"POINT", "MULTIPOINT"}:
            xs, ys, hover = [], [], []
            for _, row in layer.iterrows():
                if geom_type == "POINT":
                    xs.append(row.geometry.x)
                    ys.append(row.geometry.y)
                    hover.append(format_hovertext(row))
                else:
                    for pt in row.geometry.geoms:
                        xs.append(pt.x)
                        ys.append(pt.y)
                        hover.append(format_hovertext(row))
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="markers",
                    name=geom_type,
                    marker={"size": 4},
                    text=hover,
                    hoverinfo="text",
                )
            )
        elif geom_type in {"LINESTRING", "MULTILINESTRING"}:
            all_x, all_y, hovertext = [], [], []
            for _, row in layer.iterrows():
                segments = (
                    [row.geometry.coords]
                    if geom_type == "LINESTRING"
                    else [line.coords for line in row.geometry.geoms]
                )
                for seg in segments:
                    xs, ys = _coords_to_xy(seg)
                    all_x.extend(xs + [None])
                    all_y.extend(ys + [None])
                    hovertext.extend([format_hovertext(row)] * (len(xs) + 1))
            fig.add_trace(
                go.Scatter(
                    x=all_x,
                    y=all_y,
                    mode="lines",
                    name=geom_type,
                    text=hovertext,
                    hoverinfo="text",
                    line={"width": 1},
                )
            )
        elif geom_type in {"POLYGON", "MULTIPOLYGON"}:
            all_x, all_y, hovertext = [], [], []
            for _, row in layer.iterrows():
                polys = [row.geometry] if geom_type == "POLYGON" else row.geometry.geoms
                for poly in polys:
                    xs, ys = _coords_to_xy(poly.exterior.coords)
                    all_x.extend(xs + [None])
                    all_y.extend(ys + [None])
                    hovertext.extend([format_hovertext(row)] * (len(xs) + 1))
            fig.add_trace(
                go.Scatter(
                    x=all_x,
                    y=all_y,
                    mode="lines",
                    name=geom_type,
                    text=hovertext,
                    hoverinfo="text",
                    fill="toself",
                    opacity=0.4,
                )
            )

    fig.update_layout(
        xaxis_title="X",
        yaxis_title="Y",
        legend_title="Geometry Type",
        autosize=True,
        showlegend=True,
        yaxis_scaleanchor="x",
    )

    output_html = Path(output_html)
    fig.write_html(str(output_html), include_plotlyjs="cdn")


def format_hovertext(row_entry: pd.Series) -> str:
    """
    Construct a multi-line hover label from non-geometry attributes.

    Parameters
    ----------
    row_entry : pandas.Series
        Row of attributes including a Shapely geometry.

    Returns
    -------
    str
        HTML string with ``<br>`` separators. Geometry/meta columns are omitted.
    """
    return (
        "<br>".join(
            f"{col}: {val}"
            for col, val in row_entry.items()
            if col not in ("geometry", "geometry_type", "__source__")
            and pd.notnull(val)
        )
        or " "
    )


def _coords_to_xy(seq: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    """
    Split a coordinate sequence into separate X and Y lists.

    Parameters
    ----------
    seq : Sequence[Sequence[float]]
        Iterable of 2D or 3D coordinates (e.g., ``[(x, y), ...]``).

    Returns
    -------
    (list of float, list of float)
        Two lists: ``(xs, ys)``.
    """
    xs, ys = [], []
    for c in seq:
        xs.append(c[0])
        ys.append(c[1])
    return xs, ys


def major_axis_orientation(poly) -> float:
    mrr = minimum_rotated_rectangle(poly)
    coords = np.asarray(mrr.exterior.coords)
    edges = np.diff(coords, axis=0)[:4]
    lens = np.hypot(edges[:, 0], edges[:, 1])
    vx, vy = edges[lens.argmax()]
    return float(np.arctan2(vy, vx))


def _angle(vx: float, vy: float) -> float:
    return float(np.arctan2(vy, vx))


def _cluster_centre(lines: list[LineString]) -> Point:
    return unary_union(lines).centroid


def _cluster_orientation(lines: list[LineString]) -> float:
    angles, weights = [], []
    for g in lines:
        if not isinstance(g, LineString) or g.is_empty:
            continue
        coords = list(g.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            vx, vy = (b[0] - a[0], b[1] - a[1])
            L = np.hypot(vx, vy)
            if L == 0:
                continue
            th = (_angle(vx, vy) + np.pi) % np.pi  # 180° symmetry
            angles.append(th)
            weights.append(L)
    if not angles:
        return 0.0
    z = np.sum(np.array(weights) * np.exp(1j * 2 * np.array(angles)))
    theta = 0.5 * np.angle(z)
    return float(theta % np.pi)


def get_jamb_nodes(
    rectangle_centroids: gpd.GeoDataFrame, cluster_col: str = "cluster"
) -> gpd.GeoDataFrame:
    """
    Aggregate rectangle centroids into jamb-side clusters.

    Parameters
    ----------
    centroids : GeoDataFrame
        Each row is the centroid (Point) of one rectangle, with a cluster label.
    cluster_col : str, default 'cluster'
        Column name giving the cluster assignment for each centroid.

    Returns
    -------
    GeoDataFrame
        One row per cluster with:
            - 'cluster': cluster id
            - 'geometry': cluster mean point (Point)
            - 'n_points': number of centroids in cluster
    """
    rows = []
    for cid, g in rectangle_centroids.groupby(cluster_col, sort=False):
        pts = [
            geom for geom in g.geometry if isinstance(geom, Point) and not geom.is_empty
        ]
        if not pts:
            continue
        xs, ys = zip(*[(p.x, p.y) for p in pts])
        centre = Point(np.mean(xs), np.mean(ys))
        rows.append(
            {
                "cluster": cid,
                "geometry": centre,
                "geometry_type": "POINT",
                "n_points": len(pts),
            }
        )
    return gpd.GeoDataFrame(
        rows, geometry="geometry", crs=rectangle_centroids.crs
    ).reset_index(drop=True)


def attach_room_labels_nearest(
    jambs: gpd.GeoDataFrame, labels: gpd.GeoDataFrame, max_dist: float | None = None
) -> gpd.GeoDataFrame:
    """
    Attach attributes from the nearest room label to each jamb.

    The result preserves the jamb geometries and columns, adds
    'label_dist_m', and any non-overlapping columns from labels.

    Parameters
    ----------
    jambs : GeoDataFrame
        Jamb centroid points.
    labels : GeoDataFrame
        Room label points with descriptive columns.
    max_dist : float, optional
        Maximum distance (in CRS units) for a match. None = no limit.

    Returns
    -------
    GeoDataFrame
        Jambs with extra columns from the nearest label.
    """
    if jambs.crs is None or labels.crs is None:
        raise ValueError("Both jambs and labels must have a CRS.")
    if jambs.crs != labels.crs:
        labels = labels.to_crs(jambs.crs)

    joined = gpd.sjoin_nearest(
        jambs,
        labels,
        how="left",
        distance_col="label_dist_m",
        max_distance=max_dist,
    )

    # Get index mapping from the join
    mapping = joined[["index_right", "label_dist_m"]].copy()

    # Keep jambs as the base frame
    result = jambs.copy()
    result["label_dist_m"] = mapping["label_dist_m"].values

    # Add only new label columns that don’t already exist in jambs
    label_cols = [
        c
        for c in labels.columns
        if c not in result.columns and c != labels.geometry.name
    ]

    if label_cols:
        for col in label_cols:
            result[col] = labels.loc[mapping["index_right"], col].values

    return result
