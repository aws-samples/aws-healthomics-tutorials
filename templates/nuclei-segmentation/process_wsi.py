"""
WSI Nuclei Segmentation Pipeline

Processes an SVS whole slide image with HoVerNet, using overlapping tiles
and centroid-based stitching to avoid boundary artifacts.
Outputs nuclei contours + classifications as GeoJSON.

Usage:
    python process_wsi.py /path/to/slide.svs --output results.geojson
"""
import os
import sys
import platform
import time

# Emit startup banner immediately so task logs confirm the container ran
print("=" * 60, flush=True)
print("[STARTUP] process_wsi.py starting", flush=True)
print(f"[STARTUP] Python {sys.version}", flush=True)
print(f"[STARTUP] Platform: {platform.platform()}", flush=True)
print(f"[STARTUP] Arch: {platform.machine()}", flush=True)
print(f"[STARTUP] PID: {os.getpid()}", flush=True)
print("=" * 60, flush=True)

print("[STARTUP] Importing numpy...", flush=True)
import argparse
import dataclasses
import json
import shutil
import tempfile
import zipfile
import numpy as np
print("[STARTUP] Importing torch...", flush=True)
import torch
print(f"[STARTUP] torch {torch.__version__}, CUDA available: {torch.cuda.is_available()}", flush=True)
if torch.cuda.is_available():
    print(f"[STARTUP] GPU: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB", flush=True)
from PIL import Image
from scipy import ndimage
from skimage.measure import find_contours
from tqdm import tqdm

print("[STARTUP] Importing openslide + monai...", flush=True)
import openslide
import threading
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from monai.networks.nets import HoVerNet
from monai.apps.pathology.inferers import SlidingWindowHoVerNetInferer
print("[STARTUP] All imports done", flush=True)


@dataclasses.dataclass
class ROIPolygon:
    """A single ROI polygon parsed from a GeoJSON FeatureCollection."""
    coordinates: list  # exterior ring [[x, y], ...]
    label: str | None  # optional annotation label
    bbox: tuple[float, float, float, float] = dataclasses.field(init=False)  # (min_x, min_y, max_x, max_y)

    def __post_init__(self):
        xs = [pt[0] for pt in self.coordinates]
        ys = [pt[1] for pt in self.coordinates]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))


def parse_roi_geojson(path: str) -> list[ROIPolygon]:
    """Parse a GeoJSON ROI file (or .zip containing one) into ROIPolygon objects.

    Validates FeatureCollection structure, skips non-Polygon features with a
    stderr warning, and extracts exterior rings with optional labels.
    """
    geojson_path = path
    tmp_dir = None

    try:
        if path.endswith(".zip"):
            tmp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(tmp_dir)
            geojson_files = [
                os.path.join(root, f)
                for root, _, files in os.walk(tmp_dir)
                for f in files
                if f.endswith(".geojson")
            ]
            if not geojson_files:
                raise ValueError("No .geojson file found in the zip archive")
            geojson_path = geojson_files[0]

        with open(geojson_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(f"ROI file is not valid JSON: {exc}") from exc

        if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
            raise ValueError(
                "ROI file is not a valid GeoJSON FeatureCollection "
                "(expected object with \"type\": \"FeatureCollection\" and \"features\" array)"
            )

        polygons: list[ROIPolygon] = []
        for idx, feature in enumerate(data["features"]):
            geom = feature.get("geometry", {})
            geom_type = geom.get("type")
            if geom_type != "Polygon":
                print(
                    f"Warning: skipping feature {idx} with geometry type '{geom_type}' (expected Polygon)",
                    file=sys.stderr,
                )
                continue
            exterior_ring = geom["coordinates"][0]
            label = (feature.get("properties") or {}).get("label")
            polygons.append(ROIPolygon(coordinates=exterior_ring, label=label))

        return polygons
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _point_in_polygon_raycast(px, py, polygon):
    """Ray-casting point-in-polygon test (pure-Python fallback).

    Args:
        px: X coordinate of the test point.
        py: Y coordinate of the test point.
        polygon: List of [x, y] coordinate pairs forming the polygon boundary.

    Returns:
        True if the point (px, py) is inside the polygon, False otherwise.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


class ROIFilter:
    """Filters tiles against a set of ROI polygons.

    Uses a two-phase approach: fast bounding-box rejection followed by
    point-in-polygon testing (matplotlib.path.Path primary, ray-casting fallback).
    """

    def __init__(self, polygons: list[ROIPolygon]):
        self.polygons = polygons
        # Try to use matplotlib.path.Path for point-in-polygon
        try:
            from matplotlib.path import Path as MplPath
            self._mpl_paths = [MplPath(p.coordinates) for p in polygons]
        except ImportError:
            self._mpl_paths = None

    def tile_in_roi(self, tile_cx: float, tile_cy: float, tile_bbox: tuple) -> bool:
        """Check whether a tile overlaps with any ROI polygon.

        Two-phase test:
        1. Bounding-box intersection (fast reject).
        2. Point-in-polygon for the tile center (precise check).

        Args:
            tile_cx: Tile center X coordinate.
            tile_cy: Tile center Y coordinate.
            tile_bbox: (x_min, y_min, x_max, y_max) of the tile.

        Returns:
            True if the tile center is inside at least one ROI polygon.
        """
        tx0, ty0, tx1, ty1 = tile_bbox
        for idx, poly in enumerate(self.polygons):
            px0, py0, px1, py1 = poly.bbox
            # Phase 1: bounding-box intersection check
            if tx1 <= px0 or tx0 >= px1 or ty1 <= py0 or ty0 >= py1:
                continue
            # Phase 2: point-in-polygon for tile center
            if self._mpl_paths is not None:
                if self._mpl_paths[idx].contains_point((tile_cx, tile_cy)):
                    return True
            else:
                if _point_in_polygon_raycast(tile_cx, tile_cy, poly.coordinates):
                    return True
        return False

    def filter_tiles(self, tiles: list[dict]) -> tuple[list[dict], int]:
        """Filter a tile list, keeping only tiles whose center is inside an ROI.

        Each tile dict is expected to have keys 'x', 'y', 'width' (or 'w'),
        and 'height' (or 'h').

        Returns:
            A tuple of (filtered_tiles, skipped_count).
        """
        filtered = []
        skipped = 0
        for tile in tiles:
            x = tile["x"]
            y = tile["y"]
            w = tile.get("width", tile.get("w"))
            h = tile.get("height", tile.get("h"))
            cx = x + w / 2
            cy = y + h / 2
            bbox = (x, y, x + w, y + h)
            if self.tile_in_roi(cx, cy, bbox):
                filtered.append(tile)
            else:
                skipped += 1
        return filtered, skipped


class ResourceMonitor:
    """Background thread that periodically logs CPU, RAM, and GPU usage."""

    def __init__(self, interval=30, device=None):
        self.interval = interval
        self.device = device
        self._stop = threading.Event()
        self._thread = None

    def _get_cpu_ram(self):
        try:
            with open("/proc/meminfo") as f:
                lines = {l.split(":")[0]: int(l.split()[1]) for l in f if len(l.split()) >= 2}
            total = lines.get("MemTotal", 0) / 1024 / 1024  # GiB
            avail = lines.get("MemAvailable", 0) / 1024 / 1024
            used = total - avail
            ram_pct = (used / total * 100) if total > 0 else 0

            with open("/proc/loadavg") as f:
                load1 = f.read().split()[0]

            cpu_count = os.cpu_count() or 1
            return f"CPU load={load1}/{cpu_count}cores, RAM={used:.1f}/{total:.1f}GiB ({ram_pct:.0f}%)"
        except Exception as e:
            return f"CPU/RAM: unavailable ({e})"

    def _get_gpu(self):
        if self.device is None or not str(self.device).startswith("cuda"):
            return None
        try:
            alloc = torch.cuda.memory_allocated(self.device) / 1e9
            reserved = torch.cuda.memory_reserved(self.device) / 1e9
            total = torch.cuda.get_device_properties(self.device).total_memory / 1e9
            util = ""
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode().strip()
                util = f", util={out}%"
            except Exception:
                pass
            return f"GPU VRAM alloc={alloc:.1f}G reserved={reserved:.1f}G/{total:.1f}G{util}"
        except Exception as e:
            return f"GPU: unavailable ({e})"

    def _run(self):
        tick = 0
        while not self._stop.wait(self.interval):
            tick += 1
            parts = [f"[MONITOR t={tick * self.interval}s]", self._get_cpu_ram()]
            gpu = self._get_gpu()
            if gpu:
                parts.append(gpu)
            print(" | ".join(parts), flush=True)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

TYPE_NAMES = {
    0: "Background",
    1: "Miscellaneous",
    2: "Inflammatory",
    3: "Epithelial",
    4: "Spindle-Shaped",
}

# HoVerNet config (fast mode)
PATCH_SIZE = 256
OUT_SIZE = 164
MARGIN = (PATCH_SIZE - OUT_SIZE) // 2  # 46

# Tissue detection
TISSUE_THRESHOLD = 220  # pixels darker than this are "tissue"
MIN_TISSUE_PCT = 10     # minimum % of tissue pixels to process a tile


def validate_params(tile_size, overlap):
    """Validate tile_size and overlap parameters."""
    if tile_size < 128 or tile_size > 1024:
        sys.exit(f"Error: tile_size must be between 128 and 1024, got {tile_size}")
    if overlap < 0:
        sys.exit(f"Error: overlap must be non-negative, got {overlap}")
    if overlap >= tile_size:
        sys.exit(f"Error: overlap must be less than tile_size ({tile_size}), got {overlap}")


def load_model(bundle_root, device):
    model = HoVerNet(mode="fast", adapt_standard_resnet=True, in_channels=3, out_classes=5)
    checkpoint = torch.load(
        f"{bundle_root}/models/model.pt", map_location=device, weights_only=True,
    )
    model.load_state_dict(checkpoint)
    model.to(device)
    model.eval()
    return model


def create_inferer():
    return SlidingWindowHoVerNetInferer(
        roi_size=PATCH_SIZE,
        sw_batch_size=32,
        overlap=1.0 - float(OUT_SIZE) / float(PATCH_SIZE),
        padding_mode="constant",
        cval=0,
        progress=False,
        extra_input_padding=(MARGIN,) * 4,
    )


def is_tissue(tile_rgb):
    """Check if tile has enough tissue. Returns (bool, tissue_pct)."""
    arr = np.array(tile_rgb)
    gray = arr.mean(axis=2)
    pct = (gray < TISSUE_THRESHOLD).sum() / gray.size * 100
    return pct >= MIN_TISSUE_PCT, round(pct, 1)


def preprocess_tile(tile_rgb):
    arr = np.array(tile_rgb, dtype=np.float32)
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0) / 255.0


def postprocess_hovernet(output):
    from monai.transforms import Compose, FlattenSubKeysd
    from monai.apps.pathology.transforms.post.dictionary import (
        HoVerNetInstanceMapPostProcessingd,
        HoVerNetNuclearTypePostProcessingd,
    )
    # Remove batch dimension
    output = {k: v[0] for k, v in output.items()}

    post = Compose([
        FlattenSubKeysd(
            keys="pred",
            sub_keys=["horizontal_vertical", "nucleus_prediction", "type_prediction"],
            delete_keys=True,
        ),
        HoVerNetInstanceMapPostProcessingd(
            sobel_kernel_size=21, marker_threshold=0.4, marker_radius=2,
        ),
        HoVerNetNuclearTypePostProcessingd(),
    ])
    result = post({"pred": output})
    inst = result["instance_map"]
    types = result["type_map"]
    # Convert to numpy if tensor
    if hasattr(inst, "numpy"):
        inst = inst.numpy()
    if hasattr(types, "numpy"):
        types = types.numpy()
    return inst, types


def extract_nuclei_from_tile(instance_map, type_map, tile_x, tile_y, inner_bbox):
    """Extract nuclei whose centroids fall within the inner region. Returns global coords."""
    inst = np.squeeze(instance_map)
    types = np.squeeze(type_map)

    inner_x0, inner_y0, inner_x1, inner_y1 = inner_bbox
    nuclei = []

    for nid in np.unique(inst):
        if nid == 0:
            continue

        mask = (inst == nid).astype(np.uint8)
        row_c, col_c = ndimage.center_of_mass(mask)

        if not (inner_x0 <= col_c < inner_x1 and inner_y0 <= row_c < inner_y1):
            continue

        nuc_type = int(np.median(types[mask.astype(bool)]))
        if nuc_type == 0:
            continue

        contours = find_contours(mask, level=0.5)
        if not contours:
            continue

        contour = max(contours, key=len)
        if len(contour) > 50:
            contour = contour[np.linspace(0, len(contour) - 1, 50, dtype=int)]
        if len(contour) < 3:
            continue

        # find_contours returns (row, col), GeoJSON needs (x, y) = (col, row)
        global_coords = contour[:, ::-1] + np.array([tile_x, tile_y])

        nuclei.append({
            "contour": global_coords.tolist(),
            "centroid": [float(col_c + tile_x), float(row_c + tile_y)],
            "type": nuc_type,
            "type_name": TYPE_NAMES.get(nuc_type, f"Unknown ({nuc_type})"),
            "area_px": int(mask.sum()),
        })

    return nuclei


def generate_tiles(slide, tile_size, overlap, stride, level=0):
    w, h = slide.level_dimensions[level]
    tiles = []
    y = 0
    while y < h:
        x = 0
        while x < w:
            tw = min(tile_size, w - x)
            th = min(tile_size, h - y)
            inner_x0 = overlap if x > 0 else 0
            inner_y0 = overlap if y > 0 else 0
            inner_x1 = tw - overlap if x + tile_size < w else tw
            inner_y1 = th - overlap if y + tile_size < h else th
            tiles.append({
                "x": x, "y": y, "w": tw, "h": th,
                "inner_bbox": (inner_x0, inner_y0, inner_x1, inner_y1),
            })
            x += stride
        y += stride
    return tiles


def tile_mask_to_geojson(tile_records, output_path, roi_filtering=False, roi_polygon_count=0, roi_skipped_tiles=0, roi_filter=None):
    """Write tissue/non-tissue tile grid as GeoJSON rectangles."""
    features = []
    for i, rec in enumerate(tile_records):
        x, y, w, h = rec["x"], rec["y"], rec["w"], rec["h"]
        coords = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]
        props = {
            "classification": "Tissue" if rec["is_tissue"] else "Non-Tissue",
            "tissue_pct": rec["tissue_pct"],
        }
        if roi_filtering and roi_filter is not None:
            cx = x + w / 2
            cy = y + h / 2
            bbox = (x, y, x + w, y + h)
            props["roi_overlap"] = roi_filter.tile_in_roi(cx, cy, bbox)
        features.append({
            "type": "Feature",
            "id": i + 1,
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": props,
        })
    tissue_n = sum(1 for r in tile_records if r["is_tissue"])
    metadata = {
        "total_tiles": len(tile_records),
        "tissue_tiles": tissue_n,
        "non_tissue_tiles": len(tile_records) - tissue_n,
        "roi_filtering": roi_filtering,
    }
    if roi_filtering:
        metadata["roi_polygon_count"] = roi_polygon_count
        metadata["roi_skipped_tiles"] = roi_skipped_tiles
    geojson = {
        "type": "FeatureCollection",
        "metadata": metadata,
        "features": features,
    }
    with open(output_path, "w") as f:
        json.dump(geojson, f)
    print(f"Saved tile mask ({tissue_n} tissue / {len(tile_records) - tissue_n} non-tissue) to {output_path}")


def nuclei_to_geojson(all_nuclei, output_path, slide_path=None, level=0, tile_size=512, overlap=128, roi_filtering=False, roi_polygon_count=0, roi_skipped_tiles=0):
    features = []
    for i, nuc in enumerate(all_nuclei):
        coords = nuc["contour"]
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        features.append({
            "type": "Feature",
            "id": i + 1,
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
            "properties": {
                "nucleus_id": i + 1,
                "classification": nuc["type_name"],
                "type_code": nuc["type"],
                "centroid_x": nuc["centroid"][0],
                "centroid_y": nuc["centroid"][1],
                "area_px": nuc["area_px"],
            },
        })

    metadata = {
        "source": str(slide_path) if slide_path else None,
        "level": level,
        "model": "HoVerNet (MONAI v0.2.8)",
        "tile_size": tile_size,
        "overlap": overlap,
        "total_nuclei": len(features),
        "roi_filtering": roi_filtering,
    }
    if roi_filtering:
        metadata["roi_polygon_count"] = roi_polygon_count
        metadata["roi_skipped_tiles"] = roi_skipped_tiles

    geojson = {
        "type": "FeatureCollection",
        "metadata": metadata,
        "features": features,
    }

    with open(output_path, "w") as f:
        json.dump(geojson, f)
    print(f"Saved {len(features)} nuclei to {output_path}")




def _postprocess_batch(batch):
    """Process a batch of tiles in a single worker process.
    Each item: (output_np_dict, tile_x, tile_y, inner_bbox)
    Returns a flat list of nuclei dicts.
    """
    all_nuclei = []
    for output_np, tile_x, tile_y, inner_bbox in batch:
        output_cpu = {k: torch.from_numpy(v) for k, v in output_np.items()}
        instance_map, type_map = postprocess_hovernet(output_cpu)
        nuclei = extract_nuclei_from_tile(instance_map, type_map, tile_x, tile_y, inner_bbox)
        all_nuclei.extend(nuclei)
    return all_nuclei


def process_wsi(slide_path, output_path, bundle_root, level=0, device=None, max_tiles=None, tile_size=512, overlap=None, roi_path=None):
    if overlap is None:
        overlap = tile_size // 4
    validate_params(tile_size, overlap)
    stride = tile_size - 2 * overlap

    # --- ROI loading (before model loading to fail fast) ---
    roi_filter = None
    roi_polygons = []
    if roi_path is not None:
        if not os.path.isfile(roi_path):
            sys.exit(f"Error: ROI file not found: {roi_path}")
        roi_polygons = parse_roi_geojson(roi_path)
        roi_filter = ROIFilter(roi_polygons)
        print(f"[ROI] Loaded {len(roi_polygons)} ROI polygon(s) from {roi_path}")

    if device is None:
        if torch.cuda.is_available():
            device = torch.device("cuda:0")
        else:
            device = torch.device("cpu")

    if str(device).startswith("cuda"):
        torch.backends.cudnn.benchmark = True

    print(f"Device: {device}")
    print("=" * 60, flush=True)
    if str(device).startswith("cuda"):
        print(f"[GPU] Using CUDA device: {torch.cuda.get_device_name(device)}", flush=True)
        print(f"[GPU] VRAM: {torch.cuda.get_device_properties(device).total_memory / 1e9:.1f} GB", flush=True)
    else:
        print("[WARNING] Running on CPU — this will be very slow!", flush=True)
    print("=" * 60, flush=True)
    print(f"Loading model...")
    model = load_model(bundle_root, device)
    inferer = create_inferer()

    print(f"Opening slide: {slide_path}")
    try:
        slide = openslide.OpenSlide(str(slide_path))
    except openslide.OpenSlideError as e:
        sys.exit(f"Error: cannot open slide: {slide_path} — {e}")
    except FileNotFoundError:
        sys.exit(f"Error: slide file not found: {slide_path}")
    dims = slide.level_dimensions[level]
    print(f"Level {level}: {dims[0]} x {dims[1]}")

    tiles = generate_tiles(slide, tile_size, overlap, stride, level)
    if max_tiles:
        tiles = tiles[:max_tiles]

    roi_skipped_tiles = 0
    if roi_filter is not None:
        tiles, roi_skipped_tiles = roi_filter.filter_tiles(tiles)
        print(f"[ROI] {roi_skipped_tiles} tiles outside ROI, {len(tiles)} tiles remaining")

    print(f"Tiles to process: {len(tiles)}")

    # Batched process pool: fewer processes, each handles many tiles
    num_workers = max(1, min(3, (os.cpu_count() or 4) - 2))
    batch_size = 50  # tiles per batch sent to a worker
    print(f"Postprocessing: {num_workers} workers, batch_size={batch_size}", flush=True)

    all_nuclei = []
    tile_records = []
    skipped = 0
    t0 = time.time()

    monitor = ResourceMonitor(interval=30, device=device)
    monitor.start()

    executor = ProcessPoolExecutor(max_workers=num_workers, mp_context=__import__('multiprocessing').get_context('spawn'))
    pending_futures = []
    inference_batch = []  # accumulate GPU outputs before dispatching

    for tile_info in tqdm(tiles, desc="Processing"):
        x, y, w, h = tile_info["x"], tile_info["y"], tile_info["w"], tile_info["h"]

        region = slide.read_region((x, y), level, (w, h)).convert("RGB")
        if w < tile_size or h < tile_size:
            padded = Image.new("RGB", (tile_size, tile_size), (255, 255, 255))
            padded.paste(region, (0, 0))
            region = padded

        has_tissue, tissue_pct = is_tissue(region)
        tile_records.append({"x": x, "y": y, "w": w, "h": h, "is_tissue": has_tissue, "tissue_pct": tissue_pct})

        if not has_tissue:
            skipped += 1
            continue

        tensor = preprocess_tile(region).to(device)
        with torch.no_grad(), torch.amp.autocast("cuda", enabled=str(device).startswith("cuda")):
            output = inferer(tensor, model)

        # Convert to numpy for cross-process pickling
        output_np = {k: v.cpu().numpy() for k, v in output.items()}
        inference_batch.append((output_np, x, y, tile_info["inner_bbox"]))

        # Dispatch batch to a worker when full
        if len(inference_batch) >= batch_size:
            fut = executor.submit(_postprocess_batch, inference_batch)
            pending_futures.append(fut)
            inference_batch = []

            # Drain completed futures to bound memory
            still_pending = []
            for f in pending_futures:
                if f.done():
                    all_nuclei.extend(f.result())
                else:
                    still_pending.append(f)
            pending_futures = still_pending

            # Backpressure: don't queue more than num_workers batches ahead
            while len(pending_futures) >= num_workers:
                time.sleep(0.05)
                still_pending = []
                for f in pending_futures:
                    if f.done():
                        all_nuclei.extend(f.result())
                    else:
                        still_pending.append(f)
                pending_futures = still_pending

    # Dispatch remaining partial batch
    if inference_batch:
        fut = executor.submit(_postprocess_batch, inference_batch)
        pending_futures.append(fut)

    # Collect all remaining results
    for fut in pending_futures:
        all_nuclei.extend(fut.result())
    executor.shutdown(wait=True)

    elapsed = time.time() - t0
    monitor.stop()
    processed = len(tiles) - skipped
    print(f"\n{len(tiles)} tiles total, {skipped} skipped (no tissue), {processed} processed")
    print(f"Time: {elapsed:.1f}s ({elapsed/max(processed,1):.2f}s/tile)")
    print(f"Total nuclei: {len(all_nuclei)}")

    from collections import Counter
    for t, c in Counter(n["type_name"] for n in all_nuclei).most_common():
        print(f"  {t}: {c}")

    nuclei_to_geojson(
        all_nuclei, output_path, slide_path, level, tile_size, overlap,
        roi_filtering=(roi_filter is not None),
        roi_polygon_count=len(roi_polygons),
        roi_skipped_tiles=roi_skipped_tiles,
    )

    # Save tissue mask
    mask_path = output_path.replace(".geojson", "_tissue_mask.geojson")
    tile_mask_to_geojson(
        tile_records, mask_path,
        roi_filtering=(roi_filter is not None),
        roi_polygon_count=len(roi_polygons),
        roi_skipped_tiles=roi_skipped_tiles,
        roi_filter=roi_filter,
    )

    slide.close()




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WSI nuclei segmentation with HoVerNet")
    parser.add_argument("slide", help="Path to SVS slide")
    parser.add_argument("--output", "-o", default="nuclei.geojson", help="Output GeoJSON path")
    parser.add_argument("--bundle-root", default="bundles/pathology_nuclei_segmentation_classification")
    parser.add_argument("--level", type=int, default=0, help="Pyramid level (0=highest res)")
    parser.add_argument("--max-tiles", type=int, default=None, help="Limit tiles (for testing)")
    parser.add_argument("--device", default=None, help="Device (cpu, cuda:0)")
    parser.add_argument("--tile-size", type=int, default=512, help="Tile size in pixels (128-1024)")
    parser.add_argument("--overlap", type=int, default=None, help="Tile overlap in pixels (default: tile_size // 4)")
    parser.add_argument("--roi", default=None, help="Optional GeoJSON ROI file for region filtering")
    args = parser.parse_args()

    tile_size = args.tile_size
    overlap = args.overlap if args.overlap is not None else tile_size // 4
    validate_params(tile_size, overlap)
    stride = tile_size - 2 * overlap

    dev = torch.device(args.device) if args.device else None
    process_wsi(args.slide, args.output, args.bundle_root, args.level, dev, args.max_tiles, tile_size, overlap, roi_path=args.roi)
