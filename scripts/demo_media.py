"""Synthetic demo media: drawn "site photos" and a short progress video for a few ongoing projects, every one marked
SYNTHETIC on the picture itself and flagged synthetic in its record, so nobody takes them for real evidence.

    python scripts/demo_media.py [PROJECT_ID ...]       (default: the 3 ongoing projects with the most active packages)
    python scripts/demo_media.py --remove               (takes all synthetic demo media out again)

Re-running replaces the earlier synthetic items. Needs Pillow and OpenCV (both already installed with the OCR stack).
"""
from __future__ import annotations

import io
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from procintel.intake import media  # noqa: E402
from procintel.monitoring import views  # noqa: E402

UPLOADER = "synthetic-demo"
W, H = 960, 600
SCENES = [  # (caption, sky, ground, what is drawn)
    ("Earthworks on the access road, chainage 2+400", (150, 190, 225), (150, 120, 80), "road"),
    ("Pipe laying along the main trunk line", (165, 200, 230), (125, 110, 90), "pipe"),
    ("Community meeting on the works schedule", (190, 205, 225), (110, 140, 90), "people"),
]


def _font(size: int):
    for name in ("Arial.ttf", "Helvetica.ttc", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _stamp(d: ImageDraw.ImageDraw, w: int) -> None:
    d.rectangle((0, 0, w, 44), fill=(200, 40, 40))
    d.text((14, 8), "SYNTHETIC DEMO IMAGE - not a real site photo", fill="white", font=_font(24))


def photo(caption: str, sky, ground, what: str, project: str) -> bytes:
    img = Image.new("RGB", (W, H), sky)
    d = ImageDraw.Draw(img)
    d.rectangle((0, int(H * 0.55), W, H), fill=ground)
    if what == "road":
        d.polygon([(W * 0.42, H * 0.55), (W * 0.58, H * 0.55), (W * 0.95, H), (W * 0.05, H)], fill=(90, 90, 95))
        for y in range(int(H * 0.6), H, 40):
            d.rectangle((W * 0.49, y, W * 0.51, y + 18), fill=(235, 220, 120))
    elif what == "pipe":
        d.rectangle((0, H * 0.70, W, H * 0.80), fill=(60, 60, 60))
        for x in range(40, W, 180):
            d.ellipse((x, H * 0.62, x + 90, H * 0.74), fill=(70, 110, 160), outline=(30, 50, 80), width=4)
    else:
        for i, x in enumerate(range(120, W - 80, 110)):
            d.ellipse((x, H * 0.52, x + 40, H * 0.52 + 40), fill=(90 + i * 10, 60, 50))
            d.rectangle((x - 5, H * 0.52 + 42, x + 45, H * 0.52 + 130), fill=(40 + i * 20, 90, 140))
    _stamp(d, W)
    d.rectangle((0, H - 50, W, H), fill=(0, 0, 0))
    d.text((14, H - 40), f"{project}: {caption}", fill="white", font=_font(22))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def video(project: str) -> bytes:
    """A 6-second clip of a progress bar filling, stamped synthetic (H.264 MP4, plays in every browser)."""
    import cv2
    w, h, fps = 640, 360, 12
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v.mp4"
        out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
        for i in range(fps * 6):
            img = Image.new("RGB", (w, h), (235, 238, 245))
            d = ImageDraw.Draw(img)
            _stamp(d, w)
            d.text((24, 80), f"{project}: works progress (synthetic)", fill=(30, 30, 40), font=_font(22))
            d.rectangle((24, 160, w - 24, 200), outline=(30, 30, 40), width=2)
            d.rectangle((26, 162, 26 + (w - 52) * (i + 1) / (fps * 6), 198), fill=(60, 120, 200))
            out.write(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR))
        out.release()
        return path.read_bytes()


def remove_all() -> int:
    con = media.connect()
    try:
        ids = [r[0] for r in con.execute("SELECT media_id FROM media WHERE synthetic AND uploaded_by = ?", [UPLOADER]).fetchall()]
    finally:
        con.close()
    for mid in ids:
        media.remove(mid)
    return len(ids)


def main() -> None:
    if "--remove" in sys.argv:
        print(f"removed {remove_all()} synthetic items")
        from procintel.intake import media_evidence
        print("evidence:", media_evidence.sync())
        return
    projects = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not projects:
        projects = [p["projectId"] for p in sorted(views.projects(), key=lambda p: -p["packages"]["active"])[:3]]
    print(f"replacing {remove_all()} earlier synthetic items")
    for n, pid in enumerate(projects):
        detail = views.project(pid) or {}
        active = [k for k in detail.get("packageList", []) if k["status"] != "finished"]
        works = next((k for k in active if k.get("procGroup") == "CW"), active[0] if active else None)
        ref = works["packageId"] if works else None
        for k, (caption, sky, ground, what) in enumerate(SCENES[n % 3:] + SCENES[:n % 3]):
            taken = date.today() - timedelta(days=7 * (k + 1))
            m = media.save(f"site-{k + 1}.jpg", photo(caption, sky, ground, what, pid), pid, UPLOADER,
                           package_ref=ref if k == 0 else None, caption=f"{caption} (synthetic)", taken_on=taken,
                           synthetic=True)
            print("  ", m["id"], pid, m["packageRef"] or "-", m["caption"])
        m = media.save("progress.mp4", video(pid), pid, UPLOADER, package_ref=ref,
                       caption="Works progress clip (synthetic)", taken_on=date.today(), synthetic=True)
        print("  ", m["id"], pid, "video", m["size"], "bytes")
    from procintel.intake import media_evidence
    print("evidence:", media_evidence.sync(), "(passages are cut and indexed by the next pipeline batch)")


if __name__ == "__main__":
    main()
