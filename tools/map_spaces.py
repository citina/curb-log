#!/usr/bin/env python3
"""Draw the tracked metered spaces on an OpenStreetMap background.

Used to agree on WHICH curb we are talking about before collecting against it —
block-face numbers like "3650 VERMONT AVE" are unreadable as geography.

  ./map_spaces.py --highlight "VERMONT AVE 36xx,VERMONT AVE 37xx,36TH ST 11xx" \
                  --out coverage.png

Highlighted clusters are drawn solid; everything else currently tracked is drawn
muted, so the difference between "what you asked for" and "what is running" is
visible at a glance.

For the page's Basis map, draw the background alone and let the page draw the
spaces, so ticking a location can change them:

  ./map_spaces.py --highlight "VERMONT AVE 36xx,36TH ST 11xx" --bare \
                  --out ../docs/basemap.png --json ../docs/map.json

map.json holds the image size, metres per pixel (for the walking scale), and the
pixel position of the office and of every space inside the frame.

Tiles come from OpenStreetMap under their usage policy: a handful of tiles, a
descriptive User-Agent, cached on disk so re-runs do not refetch. Anything that
shows them must credit "© OpenStreetMap contributors".
"""
import argparse, io, json, math, os, re, sys, urllib.request

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Needs Pillow:  pip install Pillow")

TILE = 256
UA = "curb-log/1.0 (personal parking study; contact via github.com/citina/curb-log)"


def deg2num(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(math.radians(lat)) +
                        1 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def get_tile(z, x, y, cache=".tilecache"):
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, f"{z}_{x}_{y}.png")
    if os.path.exists(path):
        return Image.open(path).convert("RGB")
    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return Image.open(io.BytesIO(data)).convert("RGB")


def font(size, bold=False):
    for p in ([f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
               "/System/Library/Fonts/Helvetica.ttc"]):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def cluster_of(blockface):
    m = re.match(r"^(\d+)\s+(.*)$", blockface.strip())
    return f"{m.group(2)} {int(m.group(1))//100}xx" if m else blockface


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spaces", default="spaces.json")
    p.add_argument("--highlight", default="", help="comma-separated cluster names")
    p.add_argument("--office", default="34.0206,-118.2890")
    p.add_argument("--zoom", type=int, default=17)
    p.add_argument("--pad", type=float, default=0.0016, help="degrees of margin")
    p.add_argument("--out", default="coverage.png")
    p.add_argument("--bare", action="store_true",
                   help="background only: no spaces, labels or legend (the page draws them)")
    p.add_argument("--json", help="also write the frame and each space's pixel position here")
    a = p.parse_args()

    meta = json.load(open(a.spaces))
    pts = []
    for sid, m in meta.items():
        ll = m.get("latlng")
        if not ll:
            continue
        pts.append((float(ll["latitude"]), float(ll["longitude"]),
                    cluster_of(m.get("blockface", "?")), m.get("blockface", "?")))

    hi = {c.strip() for c in a.highlight.split(",") if c.strip()}
    focus = [q for q in pts if q[2] in hi] or pts

    olat, olon = (float(v) for v in a.office.split(","))
    lats = [q[0] for q in focus] + [olat]
    lons = [q[1] for q in focus] + [olon]
    n, s = max(lats) + a.pad, min(lats) - a.pad
    e, w = max(lons) + a.pad * 1.2, min(lons) - a.pad * 1.2

    x0f, y0f = deg2num(n, w, a.zoom)
    x1f, y1f = deg2num(s, e, a.zoom)
    tx0, ty0, tx1, ty1 = int(x0f), int(y0f), int(x1f), int(y1f)

    img = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), "white")
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            img.paste(get_tile(a.zoom, tx, ty), ((tx - tx0) * TILE, (ty - ty0) * TILE))

    def px(lat, lon):
        x, y = deg2num(lat, lon, a.zoom)
        return (x - tx0) * TILE, (y - ty0) * TILE

    left, top = px(n, w)
    right, bottom = px(s, e)
    img = img.crop((int(left), int(top), int(right), int(bottom)))
    ox, oy = int(left), int(top)

    # Fade the basemap so the markers carry the eye
    img = Image.blend(img, Image.new("RGB", img.size, "white"), 0.32)

    if a.json:
        W, H = img.size

        def rel(lat, lon):
            x, y = px(lat, lon)
            return [round(x - ox, 1), round(y - oy, 1)]

        inside = {}
        for sid, m in sorted(meta.items()):
            ll = m.get("latlng")
            if ll:
                xy = rel(float(ll["latitude"]), float(ll["longitude"]))
                if 0 <= xy[0] <= W and 0 <= xy[1] <= H:
                    inside[sid] = xy
        json.dump({
            "image": os.path.basename(a.out), "size": [W, H],
            # ground distance per image pixel at this zoom and latitude (Web Mercator)
            "m_per_px": round(156543.03392 * math.cos(math.radians((n + s) / 2)) / 2 ** a.zoom, 4),
            "office": rel(olat, olon),
            "spaces": inside,
        }, open(a.json, "w"), separators=(",", ":"))
        print(f"{a.json}  {len(inside)} spaces inside the frame")

    if a.bare:
        img.save(a.out)
        print(f"{a.out}  {img.size[0]}x{img.size[1]} (background only)")
        return

    d = ImageDraw.Draw(img, "RGBA")

    def draw_pt(lat, lon, fill, r, ring="white", rw=2):
        x, y = px(lat, lon)
        x, y = x - ox, y - oy
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=ring, width=rw)

    for lat, lon, c, _ in pts:
        if c not in hi:
            draw_pt(lat, lon, (140, 140, 134, 190), 3, (255, 255, 255, 160), 1)
    for lat, lon, c, _ in pts:
        if c in hi:
            draw_pt(lat, lon, (42, 120, 214, 255), 6)

    # office marker
    x, y = px(olat, olon)
    x, y = x - ox, y - oy
    d.line([x - 9, y - 9, x + 9, y + 9], fill=(208, 59, 59, 255), width=4)
    d.line([x - 9, y + 9, x + 9, y - 9], fill=(208, 59, 59, 255), width=4)
    d.text((x + 13, y - 8), "office (my estimate)", font=font(13, True), fill=(160, 30, 30),
           stroke_width=3, stroke_fill="white")

    # label each highlighted cluster once, at its centroid
    seen = {}
    for lat, lon, c, _ in pts:
        if c in hi:
            seen.setdefault(c, []).append((lat, lon))
    for c, ps in seen.items():
        clat = sum(q[0] for q in ps) / len(ps)
        clon = sum(q[1] for q in ps) / len(ps)
        x, y = px(clat, clon)
        d.text((x - ox + 12, y - oy - 7), f"{c}  ({len(ps)})", font=font(14, True),
               fill=(20, 60, 120), stroke_width=3, stroke_fill="white")

    # legend
    lg = font(13)
    rows = [((42, 120, 214), f"proposed: {sum(len(v) for v in seen.values())} spaces"),
            ((140, 140, 134), f"tracked now, not proposed: {sum(1 for q in pts if q[2] not in hi)}")]
    bh = 20 * len(rows) + 14
    d.rectangle([8, 8, 300, 8 + bh], fill=(255, 255, 255, 232), outline=(120, 120, 115))
    for i, (col, txt) in enumerate(rows):
        yy = 18 + i * 20
        d.ellipse([18, yy, 28, yy + 10], fill=col, outline="white", width=2)
        d.text((36, yy - 3), txt, font=lg, fill=(30, 30, 28))

    img.save(a.out)
    print(f"{a.out}  {img.size[0]}x{img.size[1]}")
    for c, ps in sorted(seen.items()):
        print(f"  {c}: {len(ps)} spaces")


if __name__ == "__main__":
    main()
