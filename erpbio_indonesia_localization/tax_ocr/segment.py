"""Names as the new DJP card prints them: "PERSEROAN TERBATAS - BADAN" on the same line as the name,
and RapidOCR's Latin model dropping the spaces -- PERSEROANTERBATAS-BADANSAMJAYAPERKASA on a real card.

The legal form is stripped by a fixed list; the spaces come back from a word-segmentation over the
names this site already knows (every Customer/Supplier name, alias and registered name), which is
how SAMJAYAPERKASA becomes SAM JAYA PERKASA. A token the site has never seen stays glued, and the
person fixes it in the suggestion -- better than inventing a split.
"""
import re

import frappe

# Longest first: "PERSEROAN TERBATAS - BADAN" must win over "BADAN".
LEGAL_FORMS = (
	"PERSEROAN TERBATAS - BADAN",
	"PERSEROAN KOMANDITER - BADAN",
	"YAYASAN - BADAN",
	"KOPERASI - BADAN",
	"PERKUMPULAN - BADAN",
	"BADAN USAHA MILIK NEGARA",
	"BADAN USAHA MILIK DAERAH",
	"BADAN LAYANAN UMUM DAERAH",
	"BADAN LAYANAN UMUM",
	"PERSEROAN TERBATAS",
	"PERSEROAN KOMANDITER",
	"ORANG PRIBADI",
	"INSTANSI PEMERINTAH",
	"BADAN",
)

# Words common enough in Indonesian institution names to seed the vocabulary on a young site.
SEED = (
	"PT CV RS RSU RSUD RSUP RSIA RSK UPT UPTD DINAS KESEHATAN RUMAH SAKIT UMUM DAERAH PUSAT KHUSUS IBU ANAK KANKER JIWA "
	"JAYA ABADI MAKMUR SEJAHTERA MANDIRI UTAMA PRIMA PERKASA SENTOSA NUSANTARA INDONESIA MEDIKA MEDICAL MEDIS "
	"LABORATORIUM LAB KLINIK KLINIKA DIAGNOSTIKA DIAGNOSTIK FARMA FARMASI KIMIA BIO BIOTECH BIOTEK SAINS SCIENCE SCIENTIFIC "
	"UNIVERSITAS INSTITUT POLITEKNIK FAKULTAS KEDOKTERAN AKADEMI SEKOLAH TINGGI YAYASAN PERKUMPULAN KOPERASI PERSEKUTUAN "
	"GLOBAL INTERNASIONAL INTERNATIONAL TEKNOLOGI TEKNIK SOLUSI SOLUTION SUKSES BERSAMA KARYA CIPTA CITRA MITRA MAJU "
	"SUMBER SINAR SURYA CAHAYA BUANA PUTRA PUTRI TUNGGAL TRI DWI EKA PANCA CATUR ANUGERAH BERKAH BERKAT RAHAYU RAHMAT "
	"HUSADA SEHAT WARAS SAKTI SIAGA HARAPAN KASIH BUNDA PERTAMINA SILOAM HERMINA MAYAPADA PRODIA KIMIA FARMA "
	"LESTARI MULIA PRATAMA PERSADA NUSA INTI AGUNG MURNI SEJATI GEMILANG CEMERLANG TUNAS BAKTI BHAKTI DHARMA DARMA "
	"BINTANG MEGAH INDAH ASRI SENTRAL CENTRAL GENETIKA GENOMIK GENOMIC INSTRUMEN INSTRUMENT ALAT ALKES SARANA PRASARANA "
	"SEMESTA SAMUDRA SAMUDERA GRAHA GRIYA WISMA MEDIKATAMA MEDIKARYA HUSADA WALUYA WALUYO SEJAHTERA SENTOSA AMANAH "
	"BAROKAH REJEKI REZEKI JAYAMAS DIAN KENCANA PELANGI MENTARI PURNAMA CANDRA CHANDRA ARTA ARTHA GUNA DAYA CIPTA "
	"KABUPATEN KOTA PROVINSI JAKARTA BANDUNG SURABAYA SEMARANG YOGYAKARTA MEDAN MAKASSAR DENPASAR PALEMBANG BOGOR "
	"DEPOK TANGERANG BEKASI MALANG SOLO SURAKARTA PADANG PEKANBARU BANJARMASIN BALIKPAPAN MANADO AMBON KUPANG "
	"DR DRG DRH PROF SP PA SPPA HJ TBK PERSERO"
).split()


def strip_legal_form(text):
	"""'PERSEROAN TERBATAS - BADAN SAM JAYA PERKASA' -> ('SAM JAYA PERKASA', 'PERSEROAN TERBATAS - BADAN'),
	and the same for the spaceless form a new card's OCR produces. Spaces the OCR kept are kept."""
	text = re.sub(r"\s+", " ", (text or "").upper()).strip()
	for form in LEGAL_FORMS:
		# the form's words with any amount of space (including none) between them
		pat = r"\s*".join(re.escape(w) for w in form.split(" "))
		m = re.match(rf"^{pat}\s*[-:.,/]*\s*(.*)$", text)
		if m:
			return m.group(1).strip(), form
		m = re.match(rf"^(.*?)\s*[-:.,/]*\s*{pat}$", text)
		if m and m.group(1).strip():
			return m.group(1).strip(), form
	return text, None


def site_vocabulary():
	"""Token -> frequency over the names this site already holds. Cached per site
	for an hour: a new customer's name is in the cache the next time it matters."""

	def build():
		counts = {}
		for word in SEED:
			counts[word] = counts.get(word, 0) + 1
		for doctype, fields in (("Customer", ("customer_name", "custom_alias", "eil_tax_name")),
		                        ("Supplier", ("supplier_name", "eil_tax_name"))):
			meta = frappe.get_meta(doctype)
			cols = [f for f in fields if meta.has_field(f)]
			for row in frappe.get_all(doctype, fields=cols, limit=0):
				for col in cols:
					for token in re.findall(r"[A-Z0-9]{2,}", (row.get(col) or "").upper()):  # no single letters: "M" from M.Si. would split MAJU
						counts[token] = counts.get(token, 0) + 1
		return counts

	key = "eil_tax_ocr_vocabulary"
	cached = frappe.cache.get_value(key, expires=True)
	if cached is None:
		cached = build()
		frappe.cache.set_value(key, cached, expires_in_sec=3600)
	return cached


def segment(compact, vocab=None):
	"""Most-likely split of a spaceless upper-case string into known tokens.

	Dynamic programming over prefixes: a known token costs 1/(1+frequency), an unknown
	run costs a flat 6 plus 2 per character. The flat part is what keeps an unknown
	stretch whole: without it the search shaves any 3-letter word it knows out of the
	middle of a name it does not (MAJUBERSAMA -> M A JUBER SAM A)."""
	if not compact:
		return ""
	if " " in compact.strip():
		return re.sub(r"\s+", " ", compact).strip()  # already spaced: nothing to recover
	vocab = vocab if vocab is not None else site_vocabulary()
	s = compact
	n = len(s)
	best = [(0.0, [])] + [(float("inf"), [])] * n
	for i in range(1, n + 1):
		for j in range(max(0, i - 24), i):
			word = s[j:i]
			if not word.isalnum():
				cost = best[j][0] + 0.5  # punctuation is its own token
			elif word in vocab:
				# a 2-letter word explains little; it must not be cheaper than leaving letters attached
				cost = best[j][0] + (1.5 if len(word) <= 2 else 1.0 / (1 + vocab[word]))
			else:
				cost = best[j][0] + 6.0 + 2.0 * len(word)
			if cost < best[i][0]:
				best[i] = (cost, best[j][1] + [word])
	out = " ".join(best[n][1])
	# an unknown run of single letters means the split failed there: glue it back
	out = re.sub(r"\b(?:[A-Z0-9] ){2,}[A-Z0-9]\b", lambda m: m.group(0).replace(" ", ""), out)
	return re.sub(r"\s+([,.\-/])", r"\1", out).strip()


def recover_name(raw, vocab=None):
	"""A name as OCR returned it -> (registered name with spaces, legal form or None).

	Only glued tokens are segmented: a token of 10+ characters the site has never
	seen as a word. Anything the OCR spaced correctly is left exactly as read."""
	body, form = strip_legal_form(raw)
	if not body:
		return "", form
	vocab = vocab if vocab is not None else site_vocabulary()
	out = []
	for token in body.split(" "):
		if len(token) >= 10 and token.isalnum() and token not in vocab:
			out.append(segment(token, vocab))
		else:
			out.append(token)
	return re.sub(r"\s+", " ", " ".join(out)).strip(), form
