"""Generate simple RGBA toolbar icons for 4designer buttons."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "toolbar"
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 64
FG = (230, 230, 235, 255)
BG = (0, 0, 0, 0)
STROKE = 3


def blank():
	return Image.new("RGBA", (SIZE, SIZE), BG)


def save(img, name):
	path = OUT / f"{name}.png"
	img.save(path)
	print(path)
	return path


def main():
	# select: rounded square outline
	img = blank()
	d = ImageDraw.Draw(img)
	d.rounded_rectangle([12, 12, 52, 52], radius=6, outline=FG, width=STROKE)
	save(img, "select")

	# translate: cross with arrow heads
	img = blank()
	d = ImageDraw.Draw(img)
	cx = cy = 32
	d.line([(cx, 14), (cx, 50)], fill=FG, width=STROKE)
	d.line([(14, cy), (50, cy)], fill=FG, width=STROKE)
	d.polygon([(cx, 8), (cx - 6, 18), (cx + 6, 18)], fill=FG)
	d.polygon([(cx, 56), (cx - 6, 46), (cx + 6, 46)], fill=FG)
	d.polygon([(8, cy), (18, cy - 6), (18, cy + 6)], fill=FG)
	d.polygon([(56, cy), (46, cy - 6), (46, cy + 6)], fill=FG)
	save(img, "translate")

	# rotate: arc with arrow
	img = blank()
	d = ImageDraw.Draw(img)
	d.arc([12, 12, 52, 52], start=40, end=300, fill=FG, width=STROKE)
	d.polygon([(48, 18), (40, 14), (46, 28)], fill=FG)
	save(img, "rotate")

	# scale: corner brackets
	img = blank()
	d = ImageDraw.Draw(img)
	d.line([(10, 22), (10, 10), (22, 10)], fill=FG, width=STROKE)
	d.line([(42, 54), (54, 54), (54, 42)], fill=FG, width=STROKE)
	d.line([(20, 20), (44, 44)], fill=FG, width=2)
	save(img, "scale")

	# discover: circular arrows
	img = blank()
	d = ImageDraw.Draw(img)
	d.arc([12, 12, 52, 52], start=20, end=160, fill=FG, width=STROKE)
	d.arc([12, 12, 52, 52], start=200, end=340, fill=FG, width=STROKE)
	d.polygon([(50, 28), (56, 38), (44, 38)], fill=FG)
	d.polygon([(14, 36), (8, 26), (20, 26)], fill=FG)
	save(img, "discover")

	# resetview: house
	img = blank()
	d = ImageDraw.Draw(img)
	d.polygon([(32, 10), (52, 28), (12, 28)], fill=FG)
	d.rectangle([18, 28, 46, 52], outline=FG, width=STROKE)
	d.rectangle([28, 38, 36, 52], fill=FG)
	save(img, "resetview")

	# snapgrid: 2x2
	img = blank()
	d = ImageDraw.Draw(img)
	d.rectangle([12, 12, 52, 52], outline=FG, width=STROKE)
	d.line([(32, 12), (32, 52)], fill=FG, width=STROKE)
	d.line([(12, 32), (52, 32)], fill=FG, width=STROKE)
	save(img, "snapgrid")

	# refreshrenders
	img = blank()
	d = ImageDraw.Draw(img)
	d.arc([10, 10, 54, 54], start=30, end=300, fill=FG, width=STROKE)
	d.polygon([(48, 14), (56, 28), (40, 24)], fill=FG)
	save(img, "refreshrenders")

	print("done", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
	main()
