from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 480, 800
GREEN = (57, 255, 20)
INK = (3, 8, 5)

def new_canvas():
    img = Image.new("RGB", (W, H), INK)
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        t = y / H
        grad.putpixel((0, y), int(14 + 30 * (1 - t)))
    grad = grad.resize((W, H))
    overlay = Image.new("RGB", (W, H), (5, 16, 10))
    return Image.composite(overlay, img, grad)

img = new_canvas()

def overlay_alpha(thing):
    global img
    base = img.convert("RGBA")
    img = Image.alpha_composite(base, thing.convert("RGBA")).convert("RGB")

# faint grid
grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(grid)
for x in range(0, W, 48):
    gd.line([(x, 0), (x, H)], fill=(57, 255, 20, 14))
for y in range(0, H, 48):
    gd.line([(0, y), (W, y)], fill=(57, 255, 20, 14))
overlay_alpha(grid)

# radial aura
aura = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ad = ImageDraw.Draw(aura)
for r in range(320, 60, -8):
    a = int(max(0, (4 - r / 80)) * 9)
    ad.ellipse([W // 2 - r, H // 2 - r - 40, W // 2 + r, H // 2 + r - 40], outline=(57, 255, 20, a))
aura = aura.filter(ImageFilter.GaussianBlur(18))
overlay_alpha(aura)
d = ImageDraw.Draw(img)

bold = "/usr/share/fonts/truetype/firacode/FiraCode-Bold.ttf"
mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
f_small = ImageFont.truetype(mono, 16)
f_big = ImageFont.truetype(bold, 76)
f_tag = ImageFont.truetype(mono, 26)
f_sub = ImageFont.truetype(mono, 13)

def corner_brackets():
    d.line([(18, 70), (18, 24), (70, 24)], fill=(57, 255, 20, 255), width=3)
    d.line([(462, 24), (410, 24)], fill=(57, 255, 20, 255), width=3)
    d.line([(462, 24), (462, 70)], fill=(57, 255, 20, 255), width=3)
    d.line([(18, H - 70), (18, H - 24), (70, H - 24)], fill=(57, 255, 20, 255), width=3)
    d.line([(462, H - 24), (410, H - 24)], fill=(57, 255, 20, 255), width=3)
    d.line([(462, H - 24), (462, H - 70)], fill=(57, 255, 20, 255), width=3)
corner_brackets()

def glow_text(x, y, text, font, fill, anchor="ma", blur=9, spread=7):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    for i in range(spread):
        dl.text((x - i, y), text, font=font, fill=fill, anchor=anchor)
        dl.text((x + i, y), text, font=font, fill=fill, anchor=anchor)
        dl.text((x, y - i), text, font=font, fill=fill, anchor=anchor)
        dl.text((x, y + i), text, font=font, fill=fill, anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    overlay_alpha(layer)
    global d
    d = ImageDraw.Draw(img)
    d.text((x, y), text, font=font, fill=fill, anchor=anchor)

# top status
d.text((24, 34), "// SECURE THIS NETWORK", font=f_small, fill=(57, 150, 80, 255))
d.text((W - 24, 34), "NODE 07", font=f_small, fill=(57, 150, 80, 255), anchor="ra")

# DARKSEC wordmark
glow_text(W // 2, 300, "DARKSEC", f_big, GREEN, blur=10, spread=8)

# labs tag
tag_w = f_tag.getbbox("labs")[2] + 44
tag_x = W // 2 - tag_w // 2
tag_y = 394
d.rectangle([tag_x, tag_y, tag_x + tag_w, tag_y + 46], outline=(57, 255, 20, 200), width=2)
d.text((W // 2, tag_y + 23), "labs", font=f_tag, fill=(140, 255, 190, 255), anchor="mm")

# divider + tagline
d.line([(24, 524), (W - 24, 524)], fill=(26, 110, 78, 255), width=1)
d.text((W // 2, 540), "WIRELESS INTELLIGENCE PLATFORM", font=f_small, fill=(80, 160, 110, 255), anchor="ma")

# bottom readout
d.text((24, H - 64), "EST. 2026", font=f_sub, fill=(57, 120, 80, 255))
d.text((W - 24, H - 64), "10-OCT-2026 04:07:18 UTC", font=f_sub, fill=(57, 120, 80, 255), anchor="ra")
for i in range(5):
    col = (57, 255, 20) if i == 0 else (26, 110, 78)
    d.ellipse([W // 2 - 72 + i * 24, H - 44, W // 2 - 72 + i * 24 + 8, H - 36], fill=col)

img.save("/tmp/opencode/darksec/darksec.png")
print("saved", img.size)

sl = Image.new("RGBA", (W, 3), (0, 0, 0, 0))
sld = ImageDraw.Draw(sl)
sld.line([(0, 1), (W, 1)], fill=(57, 255, 20, 120), width=2)
sl.save("/tmp/opencode/darksec/scanline.png")

# verify
im = Image.open("/tmp/opencode/darksec/darksec.png").convert("RGB")
def green(p): return p[0] > 40 and p[1] > 150 and p[2] < 90
for k,(x,y) in {"title":(240,330),"bracket_tl":{"x":20,"y":26},"lab_tag":(240,430),"tagline":(240,540),"dots":(216,760)}.items():
    if isinstance(y, dict): pass
print("title green:", green(im.getpixel((240,330))),
      "| bracket green:", green(im.getpixel((24,28))),
      "| tagline green:", green(im.getpixel((240,540))),
      "| dots green:", green(im.getpixel((216,760))),
      "| bg dark:", im.getpixel((6,6)))