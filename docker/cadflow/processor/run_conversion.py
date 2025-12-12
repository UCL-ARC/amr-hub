#!/usr/bin/env python
from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path
from typing import Any

import yaml
from dxf2geo.extract import FilterOptions, extract_geometries
from dxf2geo.visualise import load_geometries

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch convert DXF → GeoPackage (per file)")
    p.add_argument("--input", required=True, help="Directory containing .dxf files")
    p.add_argument("--output", required=True, help="Directory for outputs")
    p.add_argument(
        "--glob", default="*.dxf", help='Glob within --input (default: "*.dxf")'
    )
    p.add_argument(
        "--assume-crs", default=None, help="e.g. EPSG:27700 if inputs lack CRS"
    )
    p.add_argument(
        "--config-dir",
        default="config",
        help="Directory containing filter YAMLs (default: ./config)",
    )
    return p.parse_args()


# --- Config loading helpers -------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return data


def load_filter_config_for(stem: str, config_dir: Path) -> tuple[dict[str, Any], Path]:
    """
    Resolve filter config for a given DXF stem.

    Search order:
      1) {stem}.yml
      2) {stem}.yaml
      3) default_filters.yml
      4) blank_filters.yml
    """
    print(config_dir)
    candidates = [
        config_dir / f"{stem}.yml",
        config_dir / f"{stem}.yaml",
        config_dir / "default_filters.yml",
        config_dir / "blank_filters.yml",
    ]
    for p in candidates:
        print(p)
        if p.is_file():
            print(f"{p} is successful file!")
            return _read_yaml(p), p
        else:
            print(f"{p} is not a file?")
    # If config dir itself does not exist or contains none of the above
    return {
        "include_layer_patterns": [],
        "exclude_layer_patterns": [],
        "exclude_field_values": {},
        "assume_crs": None,
    }, Path("<built-in blank>")


def to_filter_options(cfg: dict[str, Any]) -> FilterOptions:
    inc = tuple(cfg.get("include_layer_patterns") or [])
    exc = tuple(cfg.get("exclude_layer_patterns") or [])
    efv = cfg.get("exclude_field_values") or {}
    # normalise any list under exclude_field_values to sets
    norm: dict[str, Any] = {}
    for k, v in efv.items():
        if isinstance(v, (list, tuple, set)):
            norm[k] = set(v)
        elif isinstance(v, dict):
            # nested dict of sets/lists
            norm[k] = {
                kk: set(vv) if isinstance(vv, (list, tuple, set)) else vv
                for kk, vv in v.items()
            }
        else:
            norm[k] = v
    return FilterOptions(
        include_layer_patterns=inc,
        exclude_layer_patterns=exc,
        exclude_field_values=norm,
    )


# --- Main -------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    args = parse_args()
    in_dir = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    cfg_dir = Path(args.config_dir).resolve()
    print(f"does it even exist? {cfg_dir.is_dir()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    dxfs = sorted(Path(p) for p in glob.glob(str(in_dir / args.glob)))
    if not dxfs:
        logger.info("No DXF files found in %s matching %s", in_dir, args.glob)
        sys.exit(2)

    tmp_root = out_dir / "_tmp_exports"
    tmp_root.mkdir(exist_ok=True)

    for dxf in dxfs:
        # Resolve per-file config
        cfg, cfg_path = load_filter_config_for(dxf.stem, cfg_dir)
        logger.info("Using config %s for %s", cfg_path, dxf.name)
        logger.info(cfg)

        filter_opts = to_filter_options(cfg)
        print(filter_opts)
        logging.info(filter_opts)
        assume_crs = cfg.get("assume_crs") or args.assume_crs

        d_out = tmp_root / dxf.stem
        d_out.mkdir(exist_ok=True)

        extract_geometries(
            dxf_path=dxf,
            output_root=d_out,
            output_format="GPKG",
            flatten=True,
            filter_options=filter_opts,
            assume_crs=assume_crs,
        )

        # Load exported geometries for this one DXF
        try:
            g = load_geometries(d_out)
        except RuntimeError:
            logger.warning("No geometries loaded from %s; skipping %s", d_out, dxf.name)
            continue
        if g.empty:
            logger.warning("Empty geometry set from %s; skipping %s", d_out, dxf.name)
            continue

        g = g.copy()
        g["source_file"] = dxf.name

        # Write one GPKG per input DXF
        per_file_out = out_dir / f"{dxf.stem}.gpkg"
        if per_file_out.exists():
            per_file_out.unlink()
        g.to_file(per_file_out, driver="GPKG", layer="features")
        logger.info("Wrote %s with %s features", per_file_out, len(g))

    # Clean temp exports
    for d in tmp_root.glob("*"):
        for child in d.glob("*"):
            child.unlink()
        d.rmdir()
    tmp_root.rmdir()


if __name__ == "__main__":
    main()
