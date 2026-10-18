from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from blind_watermark import WaterMark

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "signature.png"
ENV_FILE = ROOT / ".env"

OUT_DIR = ROOT / "out"
IMAGES_DIR = OUT_DIR / "images"
META_DIR = OUT_DIR / "watermark"

LATEST_IMAGE = IMAGES_DIR / "signature_watermarked.png"
LATEST_META = META_DIR / "watermark.txt"

# W + 7 uppercase hexadecimal characters.
# With blind_watermark's current string-to-bit conversion this is always 63 bits.
WM_SHAPE_DEFAULT = 63


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"Missing .env: {path}")

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def env_int(env: dict[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def password_seeds(password: str) -> tuple[int, int]:
    if len(password) < 12:
        raise RuntimeError("WATERMARK_PASSWORD must contain at least 12 characters.")

    img_digest = hashlib.sha256(("img:" + password).encode("utf-8")).digest()
    wm_digest = hashlib.sha256(("wm:" + password).encode("utf-8")).digest()

    # RandomState accepts 0..2**32-1.
    password_img = int.from_bytes(img_digest[:4], "big")
    password_wm = int.from_bytes(wm_digest[:4], "big")
    return password_img, password_wm


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def alpha_bbox(img: Image.Image):
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise RuntimeError("signature.png contains no visible pixels.")
    return bbox


def clamp_box(box, width, height, padding):
    l, t, r, b = box
    return (
        max(0, l - padding),
        max(0, t - padding),
        min(width, r + padding),
        min(height, b + padding),
    )


def ensure_padding(img: Image.Image, bbox, padding: int) -> Image.Image:
    # Crop around the visible signature first.
    crop_box = clamp_box(bbox, img.width, img.height, padding)
    cropped = img.crop(crop_box)

    # Ensure enough carrier area even when the original PNG is tightly cropped.
    min_w, min_h = 320, 192
    target_w = max(cropped.width, min_w)
    target_h = max(cropped.height, min_h)

    if target_w == cropped.width and target_h == cropped.height:
        return cropped

    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    x = (target_w - cropped.width) // 2
    y = (target_h - cropped.height) // 2
    canvas.alpha_composite(cropped, (x, y))
    return canvas


def feather_mask(width: int, height: int, alpha_max: int, feather: int) -> np.ndarray:
    y, x = np.mgrid[0:height, 0:width]
    d_left = x
    d_right = width - 1 - x
    d_top = y
    d_bottom = height - 1 - y
    d = np.minimum(np.minimum(d_left, d_right), np.minimum(d_top, d_bottom)).astype(np.float32)

    feather = max(1, feather)
    u = np.clip(d / feather, 0.0, 1.0)

    # Smoothstep: 0 -> 1 without hard edges.
    u = u * u * (3.0 - 2.0 * u)
    return np.round(u * alpha_max).astype(np.uint8)


def build_carrier(
    master: Image.Image,
    mode: str,
    alpha_max: int,
    feather: int,
    texture_strength: int,
    texture_seed: int,
) -> Image.Image:
    w, h = master.size

    if mode == "white":
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        alpha = np.full((h, w), 255, dtype=np.uint8)

    elif mode == "translucent":
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        alpha = np.full((h, w), alpha_max, dtype=np.uint8)

    elif mode in {"feathered", "feathered_texture"}:
        if mode == "feathered_texture":
            rng = np.random.default_rng(texture_seed)
            noise = rng.integers(
                -texture_strength,
                texture_strength + 1,
                size=(h, w, 1),
                dtype=np.int16,
            )
            base = np.full((h, w, 3), 250, dtype=np.int16)
            rgb = np.clip(base + noise, 0, 255).astype(np.uint8)
        else:
            rgb = np.full((h, w, 3), 255, dtype=np.uint8)

        alpha = feather_mask(w, h, alpha_max, feather)

    else:
        raise RuntimeError(f"Unknown carrier mode: {mode}")

    carrier_arr = np.dstack((rgb, alpha))
    carrier = Image.fromarray(carrier_arr, mode="RGBA")

    # Put the original signature on top of the carrier.
    # The carrier remains visible around/under the signature, which gives the
    # blind watermark real screen-visible image content to survive flattening.
    carrier.alpha_composite(master)
    return carrier


def capacity_bits(width: int, height: int) -> int:
    # Same geometry as blind_watermark's DWT + 4x4 block partitioning.
    ca_h = (height + 1) // 2
    ca_w = (width + 1) // 2
    return (ca_h // 4) * (ca_w // 4)


def choose_background() -> str:
    print()
    print("Background mode")
    print("  1. White")
    print("  2. Translucent")
    print("  3. Feathered")
    print("  4. Feathered texture  [recommended]")
    choice = input("Select [4]: ").strip() or "4"

    modes = {
        "1": "white",
        "2": "translucent",
        "3": "feathered",
        "4": "feathered_texture",
    }
    if choice not in modes:
        raise RuntimeError("Invalid background selection. Choose 1, 2, 3 or 4.")
    return modes[choice]


def short_id() -> str:
    # Fixed 8 characters and fixed wm_shape with blind_watermark.
    return "W" + secrets.token_hex(4).upper()[:7]


def make_sig_id(short: str) -> str:
    return f"SIG-{datetime.now().strftime('%Y%m%d')}-{short}"


def write_metadata(path: Path, values: dict[str, str | int]):
    text = "".join(f"{key}={value}\n" for key, value in values.items())
    path.write_text(text, encoding="utf-8")
    return text


def parse_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in raw:
            k, v = raw.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def matching_metadata(image_path: Path) -> Path:
    # Exact archive image -> exact archive metadata.
    exact = META_DIR / f"{image_path.stem}.txt"
    if exact.exists():
        return exact
    return LATEST_META


def embed():
    if not INPUT_FILE.exists():
        raise RuntimeError(f"Missing transparent signature: {INPUT_FILE}")

    env = read_env(ENV_FILE)
    password = env.get("WATERMARK_PASSWORD", "").strip()
    password_img, password_wm = password_seeds(password)

    padding = env_int(env, "CARRIER_PADDING", 64, 16, 300)
    alpha_max = env_int(env, "CARRIER_ALPHA", 96, 16, 255)
    feather = env_int(env, "CARRIER_FEATHER", 48, 4, 250)
    texture_strength = env_int(env, "TEXTURE_STRENGTH", 4, 0, 20)

    purpose = input("PURPOSE [signature-use]: ").strip() or "signature-use"
    mode = choose_background()

    master = Image.open(INPUT_FILE).convert("RGBA")
    bbox = alpha_bbox(master)
    master = ensure_padding(master, bbox, padding)

    short = short_id()
    sig_id = make_sig_id(short)

    # Deterministic texture for this signature instance.
    texture_seed = int(hashlib.sha256(sig_id.encode("ascii")).hexdigest()[:8], 16)
    carrier = build_carrier(
        master=master,
        mode=mode,
        alpha_max=alpha_max,
        feather=feather,
        texture_strength=texture_strength,
        texture_seed=texture_seed,
    )

    cap = capacity_bits(carrier.width, carrier.height)

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    archive_image = IMAGES_DIR / f"{sig_id}.png"
    archive_meta = META_DIR / f"{sig_id}.txt"

    with tempfile.TemporaryDirectory(prefix="sigwm-") as td:
        carrier_path = Path(td) / "carrier.png"
        carrier.save(carrier_path, format="PNG")

        bwm = WaterMark(password_img=password_img, password_wm=password_wm)
        bwm.read_img(filename=str(carrier_path))
        bwm.read_wm(short, mode="str")
        wm_shape = len(bwm.wm_bit)

        if cap <= wm_shape:
            raise RuntimeError(
                f"Carrier is too small for this watermark: capacity={cap}, watermark={wm_shape}. "
                "Increase CARRIER_PADDING."
            )

        bwm.embed(str(archive_image))

    # Verify blind_watermark preserved the generated alpha channel exactly.
    expected_alpha = np.asarray(carrier.getchannel("A"))
    actual_alpha = np.asarray(Image.open(archive_image).convert("RGBA").getchannel("A"))
    if expected_alpha.shape != actual_alpha.shape or not np.array_equal(expected_alpha, actual_alpha):
        archive_image.unlink(missing_ok=True)
        raise RuntimeError("Alpha verification failed: output transparency changed unexpectedly.")

    # Round-trip extraction from the generated original.
    checker = WaterMark(password_img=password_img, password_wm=password_wm)
    extracted = checker.extract(
        filename=str(archive_image),
        wm_shape=wm_shape,
        mode="str",
    )
    if extracted != short:
        archive_image.unlink(missing_ok=True)
        raise RuntimeError(f"Blind watermark self-check failed: extracted={extracted!r}")

    metadata = {
        "FORMAT": "SIG-BLIND-WM-1",
        "ID": sig_id,
        "SHORT_ID": short,
        "CREATED": datetime.now().astimezone().isoformat(timespec="seconds"),
        "PURPOSE": purpose,
        "BACKGROUND": mode,
        "WM_SHAPE": wm_shape,
        "WIDTH": carrier.width,
        "HEIGHT": carrier.height,
        "CARRIER_PADDING": padding,
        "CARRIER_ALPHA": alpha_max if mode != "white" else 255,
        "CARRIER_FEATHER": feather if mode.startswith("feathered") else 0,
        "TEXTURE_STRENGTH": texture_strength if mode == "feathered_texture" else 0,
        "SOURCE_SHA256": sha256_file(INPUT_FILE),
        "OUTPUT_SHA256": sha256_file(archive_image),
    }
    write_metadata(archive_meta, metadata)

    shutil.copy2(archive_image, LATEST_IMAGE)
    shutil.copy2(archive_meta, LATEST_META)

    print()
    print("SUCCESS")
    print(f"ID:         {sig_id}")
    print(f"SHORT_ID:   {short}")
    print(f"PURPOSE:    {purpose}")
    print(f"BACKGROUND: {mode}")
    print(f"WM_SHAPE:   {wm_shape}")
    print(f"IMAGE:      {archive_image}")
    print(f"LATEST:     {LATEST_IMAGE}")
    print(f"METADATA:   {archive_meta}")
    print("VERIFY:     original watermarked PNG extracted correctly")


def normalize_for_extract(target: Path, meta: dict[str, str]) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    expected_w = int(meta.get("WIDTH", "0") or 0)
    expected_h = int(meta.get("HEIGHT", "0") or 0)

    if expected_w <= 0 or expected_h <= 0:
        return target, None

    img = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"Cannot read image: {target}")

    h, w = img.shape[:2]
    if (w, h) == (expected_w, expected_h):
        return target, None

    # Helps with pure resize attacks. It cannot automatically locate a signature
    # inside a full-page screenshot; crop to the signature area first in that case.
    td = tempfile.TemporaryDirectory(prefix="sigwm-extract-")
    restored = Path(td.name) / "restored.png"
    resized = cv2.resize(img, (expected_w, expected_h), interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(restored), resized)
    return restored, td


def extract(target_arg: str | None = None):
    env = read_env(ENV_FILE)
    password = env.get("WATERMARK_PASSWORD", "").strip()
    password_img, password_wm = password_seeds(password)

    target = Path(target_arg).resolve() if target_arg else LATEST_IMAGE
    if not target.exists():
        raise RuntimeError(f"Image not found: {target}")

    meta_path = matching_metadata(target)
    meta = parse_metadata(meta_path)
    wm_shape = int(meta.get("WM_SHAPE", str(WM_SHAPE_DEFAULT)))

    normalized, td = normalize_for_extract(target, meta)
    try:
        bwm = WaterMark(password_img=password_img, password_wm=password_wm)
        extracted = bwm.extract(
            filename=str(normalized),
            wm_shape=wm_shape,
            mode="str",
        )
    finally:
        if td is not None:
            td.cleanup()

    expected = meta.get("SHORT_ID", "")
    print()
    print("EXTRACT RESULT")
    print(f"IMAGE:     {target}")
    print(f"WM_SHAPE:  {wm_shape}")
    print(f"EXTRACTED: {extracted}")
    if expected:
        print(f"EXPECTED:  {expected}")
        print(f"MATCH:     {'YES' if extracted == expected else 'NO'}")
    print()
    print("Note: for a full document screenshot, crop to the signature/carrier area first.")


def flatten_on_white(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, rgba).convert("RGB")


def extract_value(path: Path, meta: dict[str, str], password_img: int, password_wm: int) -> str:
    wm_shape = int(meta.get("WM_SHAPE", str(WM_SHAPE_DEFAULT)))
    normalized, td = normalize_for_extract(path, meta)
    try:
        bwm = WaterMark(password_img=password_img, password_wm=password_wm)
        return bwm.extract(filename=str(normalized), wm_shape=wm_shape, mode="str")
    finally:
        if td is not None:
            td.cleanup()


def test():
    if not LATEST_IMAGE.exists() or not LATEST_META.exists():
        raise RuntimeError("Generate a watermarked signature first.")

    env = read_env(ENV_FILE)
    password = env.get("WATERMARK_PASSWORD", "").strip()
    password_img, password_wm = password_seeds(password)
    meta = parse_metadata(LATEST_META)
    expected = meta.get("SHORT_ID", "")

    src = Image.open(LATEST_IMAGE).convert("RGBA")
    flat = flatten_on_white(src)

    with tempfile.TemporaryDirectory(prefix="sigwm-test-") as td:
        td = Path(td)
        cases: list[tuple[str, Path]] = []

        p = td / "flat.png"
        flat.save(p, "PNG")
        cases.append(("Flattened PNG", p))

        p = td / "scale75.png"
        flat.resize((max(1, int(flat.width * 0.75)), max(1, int(flat.height * 0.75))), Image.Resampling.LANCZOS).save(p, "PNG")
        cases.append(("75% resize", p))

        p = td / "scale50.png"
        flat.resize((max(1, int(flat.width * 0.50)), max(1, int(flat.height * 0.50))), Image.Resampling.LANCZOS).save(p, "PNG")
        cases.append(("50% resize", p))

        p = td / "jpeg90.jpg"
        flat.save(p, "JPEG", quality=90)
        cases.append(("JPEG quality 90", p))

        print()
        print(f"EXPECTED: {expected}")
        print("-" * 68)
        for label, path in cases:
            try:
                value = extract_value(path, meta, password_img, password_wm)
                ok = value == expected
                print(f"{label:<22} {'PASS' if ok else 'FAIL':<5}  extracted={value!r}")
            except Exception as exc:
                print(f"{label:<22} ERROR  {exc}")
        print("-" * 68)
        print("These are synthetic checks, not a guarantee for every real screenshot.")


def main():
    try:
        command = sys.argv[1].lower() if len(sys.argv) >= 2 else "embed"

        if command in {"embed", "run"}:
            embed()
        elif command in {"extract", "-x", "--extract"}:
            extract(sys.argv[2] if len(sys.argv) >= 3 else None)
        elif command == "test":
            test()
        else:
            raise RuntimeError(f"Unknown command: {command}")

    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
