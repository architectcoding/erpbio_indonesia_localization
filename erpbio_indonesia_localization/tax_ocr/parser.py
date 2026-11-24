"""OCR lines -> tax identity fields. Pure functions: no engine, no database, unit-tested on text.

What the documents print (all upper case, all read as rows):
  NPWP card (Coretax 2025) KANTOR PELAYANAN PAJAK ...  |  1000 0000 0123 4567  |  <name>  |  address  |  TANGGAL TERDAFTAR ...
                           (no label anywhere: the word npwp is a picture; a company registered since Coretax
                           has a number that starts with 1000, a person's number is their NIK)
  NPWP card (2024 design)  NPWP : 70.895.848.3-428.000  |  <legal form> <name>  |  NPWP16: 0708958483428000  |  address  |  KPP ...
  NPWP card (old design)   NPWP : 01.234.567.8-901.000  |  <name, no label>     |  NIK : ...  |  address  |  KPP ...
  KTP                      NIK : 3174...  |  Nama : ...  |  Tempat/Tgl Lahir ...  |  Alamat : ...  |  RT/RW ...
  SKT / SPPKP letter       Nama : ...  |  NPWP : ...  |  Alamat : ...  (born-digital PDFs read as text)

A number is `verified` when the document states it twice and the two agree (the 15-digit and the
16-digit line of a badan card, NPWP16 and NIK of an individual's card), or when it came out of a
born-digital PDF with its label (a Coretax card's layout stands in for the label). Anything read once from pixels is a suggestion, whatever its
confidence -- one misread digit is a different taxpayer.
"""
import html
import re

NPWP15 = re.compile(r"(?<!\d)(\d{2})[.,:\s]?(\d{3})[.,:\s]?(\d{3})[.,:\s]?(\d)[-.\s]{0,2}(\d{3})[.,:\s]?(\d{3})(?!\d)")
DIGIT_RUN = re.compile(r"(?<!\d)(\d[\d\s.]{13,22}\d)(?!\d)")
LABEL = re.compile(r"^\s*(NPWP\s*16|NPWP16|NPWP|NIK|NAMA|NAME|ALAMAT|ADDRESS)\b\s*[:.\-]?\s*(.*)$", re.I)
NOISE = ("KEMENTERIAN", "DIREKTORAT", "REPUBLIK", "PROVINSI", "KABUPATEN", "KPP ", "KPPPRATAMA", "TERDAFTAR", "BERLAKU",
         "TEMPAT", "JENIS KELAMIN", "GOL", "AGAMA", "STATUS", "PEKERJAAN", "KEWARGANEGARAAN", "RT/RW", "KEL/DESA", "KECAMATAN",
         "TANGGAL", "DJP", "PAJAK")
ADDRESS_HINT = re.compile(r"\b(JL|JLN|JALAN|GG|GANG|KOMP|KOMPLEK|PERUM|RUKO|RT|RW|KEL|KEC|KOTA|KAB|BLOK|NO)\b\.?", re.I)


# What a NAME line may not start with. Anchored, unlike NOISE: "RSUD KABUPATEN NGANJUK",
# "POLTEKKES ... DIREKTORAT ..." and "GOLDEN ..." are names.
NAME_NOISE = re.compile(r"\W*(KEMENTERIAN\s*KEUANGAN|DIREKTORAT\s*JENDERAL\s*PAJAK|REPUBLIK\s*INDONESIA|KPP|KANTOR\s*PELAYANAN\s*PAJAK"
                        r"|TERDAFTAR|TANGGAL|TGL|BERLAKU|TEMPAT|JENIS\s*KELAMIN|GOL\b|AGAMA|STATUS|RT\s*/\s*RW|O?DJP"
                        r"|E-?MAIL|NITKU|NOMOR|D?IREKTORAT|.*RAL\s*PAJA)", re.I)  # the last two: the letterhead, half read
# The card's own furniture, matched without spaces because OCR drops them.
OFFICE = re.compile(r"KANTORPELAYANANPAJAK|KPP(PRATAMA|MADYA|WAJIB|PERUSAHAAN|MINYAK|PENANAMAN|BADAN)")
CARD_END = re.compile(r"TERDAFTAR|KANTORPELAYANANPAJAK|^\W*KPP(PRATAMA|MADYA|WAJIB|PERUSAHAAN|MINYAK|PENANAMAN|BADAN)|^\W*\d{1,2}-\d{1,2}-\d{4}\W*$")
CARD_BACK = re.compile(r"PAJAK\.?GO\.?ID|PAJAKKITAUNTUKKITA|KARTUINIHARAP|AGARDICANTUMKAN|WAJIBPAJAKPINDAH|LAYANANPERPAJAKAN|PAJAKTERDAFTAR|KEMENTERIANKEUANGAN|^\W*O?DJP\W*$|DIPINDAIDENGAN")

CARD_BACK_HEADING = re.compile(r"PAJAK\.?GO\.?ID|PAJAKKITAUNTUKKITA|KARTUINIHARAP")


def compact(text):
	return re.sub(r"\s+", "", (text or "").upper())


def fix_digits(text):
	"""OCR confusions, applied to number fields only: O->0, I/l->1, S->5, B->8."""
	return (text or "").translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"}))


def fix_number_tokens(text):
	"""fix_digits, but only on words that can be part of a number. Applied to a whole row it
	turned the I of "3512014912900001 INTAN" into a 17th digit, and the card read as nothing."""
	def fix(m):
		t = re.sub(r"\W", "", m.group(0))
		return fix_digits(m.group(0)) if t and re.fullmatch(r"[0-9OoIlSB]+", t) and re.search(r"\d|^[Oo]+$", t) else m.group(0)
	return re.sub(r"\S+", fix, text or "")


def digits(text):
	return re.sub(r"\D", "", fix_digits(text))


def nik_plausible(d):
	"""16 digits: province 11-94, then DDMMYY with DD+40 for women, then a 4-digit serial."""
	if len(d) != 16 or not d.isdigit() or not (11 <= int(d[:2]) <= 94):
		return False
	dd, mm = int(d[6:8]), int(d[8:10])
	return (1 <= dd <= 31 or 41 <= dd <= 71) and 1 <= mm <= 12


def id_type_for(number16):
	"""Coretax's own split, as used for the customer match: a 16-digit number that is
	NIK-shaped is an orang pribadi even when the card labels it NPWP (their NPWP IS the NIK)."""
	return "NIK" if nik_plausible(number16) and not number16.endswith("000") else "TIN"


def _label_of(line):
	m = LABEL.match(line)
	if not m:
		return None, line
	label = re.sub(r"\s+", "", m.group(1).upper())
	return ("NPWP16" if label == "NPWP16" else label), m.group(2)


def number_candidates(lines):
	"""Every taxpayer-number-shaped thing on the document, with the label it stood under.

	Each candidate: {"label", "value" (16 digits), "raw", "line": index}. A 15-digit NPWP is
	returned as the 16-digit form Coretax uses (leading 0), which is also what makes the
	two lines of a badan card comparable."""
	found = []
	for i, line in enumerate(lines):
		label, rest = _label_of(line)
		fixed = fix_number_tokens(rest)
		m15 = NPWP15.search(fixed)
		if m15 and (label in ("NPWP", None) or "-" in m15.group(0)) and (label or "-" in m15.group(0) or "." in m15.group(0)):
			d15 = "".join(m15.groups())
			found.append({"label": label or "NPWP", "value": "0" + d15, "raw": m15.group(0), "line": i, "form": "15"})
			fixed = fixed.replace(m15.group(0), " ")
		for m in DIGIT_RUN.finditer(fixed):
			d = re.sub(r"\D", "", m.group(1))
			if len(d) == 16:
				found.append({"label": label, "value": d, "raw": m.group(1).strip(), "line": i, "form": "16"})
			elif len(d) == 15 and label == "NPWP":
				found.append({"label": label, "value": "0" + d, "raw": m.group(1).strip(), "line": i, "form": "15"})
	return found


def _is_card_layout(lines, number_line):
	"""The issued card's own order: the tax office above the number, the registration date below it.
	This is what lets a number without any label be taken for an NPWP; a 16-digit run on an
	invoice or a bank slip has neither around it."""
	above = [compact(l) for l in lines[:number_line + 1]]
	below = [compact(l) for l in lines[number_line + 1:]]
	return any(OFFICE.search(l) for l in above) and any("TERDAFTAR" in l or re.search(r"^\W*\d{1,2}-\d{1,2}-\d{4}\W*$", l) for l in below)


def _card_name_and_address(lines, number_line):
	"""Name and address of a 2024 or Coretax card, where neither has a label.

	Everything between the number and the office/date is name, then address. A wrapped name
	runs up to the NPWP16/NIK line when the card has one; a Coretax card has none, so there a
	second name row is only believed when the first one filled the card's width and the next
	row looks like no part of an address."""
	body, id_line = [], None
	for line in lines[number_line + 1:]:
		c = compact(line)
		if _label_of(line)[0] in ("NPWP16", "NPWP", "NIK"):
			id_line = len(body) if id_line is None else id_line
			continue
		if CARD_BACK.search(c):
			continue
		if CARD_END.search(c):
			break
		line = re.sub(r"\s+O?djp\W*$", "", line)  # the logo, on the last address row
		text = re.sub(r"\s*\b\d{12,16}\b.*$", "", line).strip(" :.-")  # the NIK printed beside a person's name
		if len(re.sub(r"\W", "", text)) > 2 or (body and re.search(r"[A-Za-z]{2}", text)):
			body.append(line.strip() if text == line.strip(" :.-") else text)
	if not body or NAME_NOISE.match(body[0]) or not re.search(r"[A-Za-z]{3,}", body[0]):
		return None, None
	if id_line and id_line <= 3:
		n = id_line
	else:
		n = 1
		if len(body) > 2 and len(body[0]) >= 44 and not re.search(r"[\d,]", body[1]) and not ADDRESS_HINT.search(body[1]):
			n = 2
	name = " ".join(body[:n]).strip(" :.-,")
	# rows wrap in the middle of a phrase ("JL. BULEVAR" / "AHMAD YANI"): the card's own commas are the separators
	address = re.sub(r"(\s*,\s*)+", ", ", " ".join(body[n:])).strip(" ,")
	return name, address or None


def parse(lines, source="ocr"):
	"""-> dict(tax_id, id_type, tax_name, tax_address, kind, verified, evidence, notes)."""
	lines = [re.sub(r"\s+", " ", html.unescape(l)).strip() for l in (lines or []) if l and l.strip()]
	up = "\n".join(lines).upper()
	flat = compact(up)
	out = {"tax_id": None, "id_type": None, "tax_name": None, "tax_address": None, "kind": None,
	       "verified": False, "evidence": [], "notes": []}

	if "SURATKETERANGANTERDAFTAR" in flat or "PENGUKUHANPENGUSAHAKENAPAJAK" in flat:
		out["kind"] = "Letter"
	elif "NPWP" in up and ("DIREKTORATJENDERALPAJAK" in flat or "KPP" in up or "KANTORPELAYANANPAJAK" in flat or "NOMORPOKOKWAJIBPAJAK" in flat or "DJP" in up):
		out["kind"] = "NPWP"
	elif "NIK" in up and ("PROVINSI" in up or "TEMPAT/TGL" in up or "KEWARGANEGARAAN" in up or "GOL. DARAH" in up or "GOL.DARAH" in up):
		out["kind"] = "KTP"

	cands = number_candidates(lines)
	# A Coretax card labels nothing: its layout is the label.
	for c in cands:
		if c["label"] is None and c["form"] == "16" and not any(x["label"] for x in cands) and out["kind"] in (None, "NPWP") \
				and _is_card_layout(lines, c["line"]):
			c["label"], out["kind"] = "NPWP", "NPWP"
			break
	if not out["kind"] and cands and _is_card_layout(lines, cands[0]["line"]):
		out["kind"] = "NPWP"
	# NPWP16 that is a NIK: since 2024 that IS the person's NPWP, the 15-digit line above it is the retired one
	npwp = next((c for c in cands if c["label"] == "NPWP16" and nik_plausible(c["value"])), None) \
		or next((c for c in cands if c["label"] in ("NPWP", "NPWP16")), None) \
		or next((c for c in cands if c["label"] is None and c["value"].startswith("0")), None)
	nik = next((c for c in cands if c["label"] == "NIK"), None) \
		or next((c for c in cands if c["label"] is None and nik_plausible(c["value"])), None)
	chosen = npwp or nik
	if chosen:
		out["tax_id"] = chosen["value"]
		out["id_type"] = id_type_for(chosen["value"])
		out["evidence"] = [c for c in cands]
		distinct_lines = {c["line"] for c in cands if c["value"] == chosen["value"]}
		if len(distinct_lines) >= 2:
			out["verified"] = True
			out["notes"].append("number printed twice on the document, both readings agree")
		elif source == "pdf-text" and chosen["label"]:
			out["verified"] = True
		if npwp and npwp["form"] == "15" and not any(c["form"] == "16" and c["value"] == npwp["value"] for c in cands):
			out["notes"].append("15-digit NPWP on the document; stored as the 16-digit form Coretax uses")
		if nik and npwp and nik["value"] != npwp["value"]:
			out["notes"].append("the document also shows NIK %s" % nik["value"])
		family = {"NPWP": "NPWP", "NPWP16": "NPWP", "NIK": "NIK"}
		retired = chosen["label"] == "NPWP16" and nik_plausible(chosen["value"])  # 15-digit beside a NIK: different by design
		if any(c["value"] != chosen["value"] and not (retired and c["form"] == "15") and family.get(c["label"]) == family.get(chosen["label"]) for c in cands):
			out["verified"] = False
			out["notes"].append("two different numbers under the same label -- check the card")

	# labelled name / address
	for i, line in enumerate(lines):
		label, rest = _label_of(line)
		if label in ("NAMA", "NAME") and rest.strip(" :.-") and not out["tax_name"]:
			out["tax_name"] = rest.strip(" :.-")
		if label in ("ALAMAT", "ADDRESS") and rest.strip(" :.-") and not out["tax_address"]:
			out["tax_address"] = rest.strip(" :.-")
			# an address wraps: keep following lines that look like address parts until a label or noise
			for cont in lines[i + 1:i + 3]:
				l2, _ = _label_of(cont)
				if l2 or any(n in cont.upper() for n in NOISE) or not ADDRESS_HINT.search(cont) and not re.search(r"\d{5}", cont):
					break
				out["tax_address"] += ", " + cont.strip(" :.-")

	# the 2024 and Coretax cards, read by their layout
	if chosen and not (out["tax_name"] or out["tax_address"]) and out["kind"] == "NPWP":
		first = min(c["line"] for c in cands if c["label"] in ("NPWP", "NPWP16") or c is chosen)
		if _is_card_layout(lines, first) or any(c["label"] == "NPWP16" for c in cands):
			out["tax_name"], out["tax_address"] = _card_name_and_address(lines, first)

	# NPWP cards print the name under the number with no label; the new design puts the
	# legal form on the same line ("PERSEROAN TERBATAS - BADAN SAM JAYA PERKASA")
	if not out["tax_name"] and npwp:
		for cand in lines[npwp["line"] + 1:npwp["line"] + 3]:
			c = cand.strip(" :.-")
			if c and not _label_of(c)[0] and not NAME_NOISE.match(c) and re.search(r"[A-Za-z]{3,}", c) \
					and not NPWP15.search(fix_digits(c)) and len(digits(c)) < 10:
				out["tax_name"] = c
				break

	# NPWP cards print the address after the name, unlabelled, over one or two rows
	if not out["tax_address"] and npwp and out["kind"] == "NPWP":
		start = npwp["line"] + 1
		parts = []
		for cand in lines[start:start + 5]:
			cu = cand.upper()
			if cand.strip() == (out["tax_name"] or "").strip() or _label_of(cand)[0] or NPWP15.search(fix_digits(cand)):
				continue
			if any(n in cu for n in NOISE):
				if parts:
					break
				continue
			if ADDRESS_HINT.search(cand) or re.search(r"\d{5}\b", fix_digits(cand)) or (parts and "," in cand):
				parts.append(cand.strip(" :.-"))
			elif parts:
				break
		if parts:
			out["tax_address"] = ", ".join(parts)

	if out["tax_address"]:
		# the postcode is the one place a letter can only be a misread digit
		out["tax_address"] = re.sub(r"(?<=\d)[OoIlSB](?=\d)|(?<=\d{2})[OoIlSB](?=\d{2})", lambda m: fix_digits(m.group(0)), out["tax_address"])
		out["tax_address"] = re.sub(r"(?<=\b\d{2})[Oo]\b", "0", out["tax_address"])  # RT. 00O
		out["tax_address"] = re.sub(r"\s*,\s*", ", ", out["tax_address"]).strip(" ,")
	if out["tax_id"] and not out["kind"]:
		out["kind"] = "NPWP" if out["id_type"] == "TIN" else "KTP"
	return out
