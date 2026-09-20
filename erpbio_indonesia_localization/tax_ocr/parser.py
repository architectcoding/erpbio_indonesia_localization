"""OCR lines -> tax identity fields. Pure functions: no engine, no database, unit-tested on text.

What the documents print (all upper case, all read as rows):
  NPWP card (2024 design)  NPWP : 70.895.848.3-428.000  |  <legal form> <name>  |  NPWP16: 0708958483428000  |  address  |  KPP ...
  NPWP card (old design)   NPWP : 01.234.567.8-901.000  |  <name, no label>     |  NIK : ...  |  address  |  KPP ...
  KTP                      NIK : 3174...  |  Nama : ...  |  Tempat/Tgl Lahir ...  |  Alamat : ...  |  RT/RW ...
  SKT / SPPKP letter       Nama : ...  |  NPWP : ...  |  Alamat : ...  (born-digital PDFs read as text)

A number is `verified` when the document states it twice and the two agree (the 15-digit and the
16-digit line of a badan card, NPWP16 and NIK of an individual's card), or when it came out of a
born-digital PDF with its label. Anything read once from pixels is a suggestion, whatever its
confidence -- one misread digit is a different taxpayer.
"""
import re

NPWP15 = re.compile(r"(?<!\d)(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[.\s]?(\d)[-.\s]?(\d{3})[.\s]?(\d{3})(?!\d)")
DIGIT_RUN = re.compile(r"(?<!\d)(\d[\d\s.]{13,22}\d)(?!\d)")
LABEL = re.compile(r"^\s*(NPWP\s*16|NPWP16|NPWP|NIK|NAMA|NAME|ALAMAT|ADDRESS)\b\s*[:.\-]?\s*(.*)$", re.I)
NOISE = ("KEMENTERIAN", "DIREKTORAT", "REPUBLIK", "PROVINSI", "KABUPATEN", "KPP ", "KPPPRATAMA", "TERDAFTAR", "BERLAKU",
         "TEMPAT", "JENIS KELAMIN", "GOL", "AGAMA", "STATUS", "PEKERJAAN", "KEWARGANEGARAAN", "RT/RW", "KEL/DESA", "KECAMATAN",
         "TANGGAL", "DJP", "PAJAK")
ADDRESS_HINT = re.compile(r"\b(JL|JLN|JALAN|GG|GANG|KOMP|KOMPLEK|PERUM|RUKO|RT|RW|KEL|KEC|KOTA|KAB|BLOK|NO)\b\.?", re.I)


def fix_digits(text):
	"""OCR confusions, applied to number fields only: O->0, I/l->1, S->5, B->8."""
	return (text or "").translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"}))


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
		fixed = fix_digits(rest)
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


def parse(lines, source="ocr"):
	"""-> dict(tax_id, id_type, tax_name, tax_address, kind, verified, evidence, notes)."""
	lines = [re.sub(r"\s+", " ", l).strip() for l in (lines or []) if l and l.strip()]
	up = "\n".join(lines).upper()
	out = {"tax_id": None, "id_type": None, "tax_name": None, "tax_address": None, "kind": None,
	       "verified": False, "evidence": [], "notes": []}

	if "SURAT KETERANGAN TERDAFTAR" in up or "PENGUKUHAN PENGUSAHA KENA PAJAK" in up:
		out["kind"] = "Letter"
	elif "NPWP" in up and ("DIREKTORAT JENDERAL PAJAK" in up or "KPP" in up or "NOMOR POKOK WAJIB PAJAK" in up or "DJP" in up):
		out["kind"] = "NPWP"
	elif "NIK" in up and ("PROVINSI" in up or "TEMPAT/TGL" in up or "KEWARGANEGARAAN" in up or "GOL. DARAH" in up or "GOL.DARAH" in up):
		out["kind"] = "KTP"

	cands = number_candidates(lines)
	npwp = next((c for c in cands if c["label"] in ("NPWP", "NPWP16")), None) \
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
		if any(c["value"] != chosen["value"] and family.get(c["label"]) == family.get(chosen["label"]) for c in cands):
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

	# NPWP cards print the name under the number with no label; the new design puts the
	# legal form on the same line ("PERSEROAN TERBATAS - BADAN SAM JAYA PERKASA")
	if not out["tax_name"] and npwp:
		for cand in lines[npwp["line"] + 1:npwp["line"] + 3]:
			c = cand.strip(" :.-")
			cu = c.upper()
			if c and not _label_of(c)[0] and not any(n in cu for n in NOISE) and re.search(r"[A-Za-z]{3,}", c) \
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
		out["tax_address"] = re.sub(r"\s*,\s*", ", ", out["tax_address"]).strip(" ,")
	if out["tax_id"] and not out["kind"]:
		out["kind"] = "NPWP" if out["id_type"] == "TIN" else "KTP"
	return out
