"""Text acquisition for a tax document: born-digital PDF text first, OCR otherwise.

The engine is the slide-manager sidecar's (rapidocr-onnxruntime: CPU, pip-only, ~150 MB with
opencv-python-headless) and is an OPTIONAL pack, exactly as there: without it `engine_available()`
is False, the reading records "OCR engine not installed" and nothing else changes. Install once per
bench:  bench pip install rapidocr-onnxruntime opencv-python-headless
"""
import logging
import re

log = logging.getLogger(__name__)

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic")
PDF_EXT = (".pdf",)
MAX_PIXELS = 4000 * 4000


class EngineMissing(RuntimeError):
	"""The optional OCR pack is not installed on this bench."""


def supported(file_name):
	return (file_name or "").lower().endswith(IMAGE_EXT + PDF_EXT)


def engine_available():
	try:
		import rapidocr_onnxruntime  # noqa: F401
		return True
	except ImportError:
		return False


_engine = None


def _get_engine():
	global _engine
	if _engine is None:
		from rapidocr_onnxruntime import RapidOCR

		_engine = RapidOCR()
	return _engine


def read(path, rotation_hint=0):
	"""-> (lines, source, confidence). source is "pdf-text" or "ocr"; confidence 0..1 (1.0 for text)."""
	if path.lower().endswith(PDF_EXT):
		lines = _born_digital_lines(path)
		if lines:  # a DJP letter or card as issued: real text, no OCR needed
			return lines, "pdf-text", 1.0
		return read_pixels(path, rotation_hint)
	from PIL import Image, ImageOps

	img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # phone photos carry their orientation in EXIF
	if img.width * img.height > MAX_PIXELS:
		img.thumbnail((4000, 4000))
	lines, conf = _ocr_best_rotation(img, rotation_hint)
	return lines, "ocr", conf


def read_pixels(path, rotation_hint=0):
	"""The first page of a PDF through OCR whatever text it carries: for a PDF whose text held no
	tax number (a card pasted as a picture into a page with other text on it)."""
	pages = _pdf_render(path, dpi=200)
	if not pages:
		return [], "ocr", 0.0
	lines, conf = _ocr_best_rotation(pages[0], rotation_hint)
	return lines, "ocr", conf


def read_pdf_text_only(path):
	"""A born-digital PDF without the engine; a scan raises EngineMissing."""
	lines = _born_digital_lines(path)
	if lines:
		return lines, "pdf-text", 1.0
	raise EngineMissing("This PDF is a scan; reading it needs the OCR engine (pip install rapidocr-onnxruntime)")


def _born_digital_lines(path):
	"""The PDF's own text, or [] when there is too little of it or it is a scanner's OCR layer.
	That layer is written invisible (text render mode 3) over the picture; it is somebody else's
	OCR ("CY. C0NT'ilII,OH INIX}NESIA") and must not pass for text the tax office issued."""
	if _text_is_invisible(path):
		return []
	text = _pdf_text(path)
	if len(re.sub(r"\s", "", text)) < 40:
		return []
	return [l.strip() for l in text.splitlines() if l.strip()]


def _text_is_invisible(path):
	import pypdfium2 as pdfium
	import pypdfium2.raw as raw

	doc = pdfium.PdfDocument(path)
	try:
		modes = [raw.FPDFTextObj_GetTextRenderMode(o.raw) for i in range(min(len(doc), 1))
		         for o in doc[i].get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT], max_depth=4)]
	finally:
		doc.close()
	return bool(modes) and modes.count(raw.FPDF_TEXTRENDERMODE_INVISIBLE) * 2 > len(modes)


def _pdf_text(path):
	import pypdfium2 as pdfium

	doc = pdfium.PdfDocument(path)
	try:
		return "\n".join(doc[i].get_textpage().get_text_range() for i in range(min(len(doc), 3)))
	finally:
		doc.close()


def _pdf_render(path, dpi=200):
	import pypdfium2 as pdfium

	doc = pdfium.PdfDocument(path)
	try:
		return [doc[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in range(min(len(doc), 1))]
	finally:
		doc.close()


def _ocr(img):
	import numpy as np

	res, _elapsed = _get_engine()(np.asarray(img))
	return res or []


def _ocr_best_rotation(img, hint=0):
	"""The sidecar's search, with one correction learnt on a KTP: the upright read is kept
	unless another quarter turn reads clearly MORE text. Sideways text still yields boxes
	with decent confidence, so a bare confidence sum can prefer the wrong orientation."""
	first = int(hint or 0) % 360
	order = [first] + [d for d in (0, 90, 270, 180) if d != first]
	best, best_score = [], 0.0
	for deg in order:
		res = _ocr(img.rotate(-deg, expand=True) if deg else img)
		score = sum(float(c) * len(re.sub(r"\W", "", t)) for _, t, c in res)
		if deg == order[0] and res and score / len(res) >= 6:  # about a confident word per box: upright, stop
			return _rows(res), _mean_conf(res)
		if score > best_score * 1.15:
			best, best_score = res, score
	return _rows(best), _mean_conf(best)


def _mean_conf(res):
	return (sum(float(c) for _, _, c in res) / len(res)) if res else 0.0


def _front_only(res):
	"""An NPWP card is often issued and scanned with its back beside its front. The back's rows
	share a height with the front's, so without this they end up inside the address."""
	from erpbio_indonesia_localization.tax_ocr.parser import CARD_BACK_HEADING, OFFICE, compact

	left = lambda b: min(p[0] for p in b)  # noqa: E731
	right = lambda b: max(p[0] for p in b)  # noqa: E731
	back = [left(b) for b, t, _c in res if CARD_BACK_HEADING.search(compact(t))]
	front = [right(b) for b, t, _c in res if OFFICE.search(compact(t))]
	if not back or not front:
		return res
	edge = max(front)  # the office line runs to the front card's right edge
	if min(back) <= edge:
		return res
	return [r for r in res if left(r[0]) <= edge]


def _rows(res):
	"""Cluster boxes into visual rows (y-centre within half a box height), left to right, so a
	KTP's "Nama" label box and its ": ANDI ..." value box come out as one line."""
	items = []
	for box, text, conf in _front_only(res):
		ys = [p[1] for p in box]
		xs = [p[0] for p in box]
		items.append((sum(ys) / 4.0, (max(ys) - min(ys)) or 1.0, min(xs), text.strip()))
	items.sort(key=lambda t: (t[0], t[2]))
	rows, cur, cur_y, cur_h = [], [], None, None
	for y, h, x, text in items:
		if cur and abs(y - cur_y) <= max(cur_h, h) * 0.5:
			cur.append((x, text))
		else:
			if cur:
				rows.append(" ".join(t for _, t in sorted(cur)))
			cur, cur_y, cur_h = [(x, text)], y, h
	if cur:
		rows.append(" ".join(t for _, t in sorted(cur)))
	return rows
