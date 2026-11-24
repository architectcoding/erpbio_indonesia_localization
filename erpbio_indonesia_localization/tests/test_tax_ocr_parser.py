"""The tax-document parser on text alone: no engine, no database, no files.

Line sets are what RapidOCR's rows look like on the documents Biozatix' customers actually send:
the 2024 DJP card (legal form glued to the name, NPWP16 line), the old card (unlabelled name), a KTP
(label and value in separate columns, clustered back into one row), an SKT letter as a born-digital
PDF. The real 2024 card read on erp.biozatix.com on 2026-09-21 is the first case, digits altered.
"""
import unittest

from erpbio_indonesia_localization.tax_ocr import parser as P
from erpbio_indonesia_localization.tax_ocr.segment import recover_name, segment, strip_legal_form

VOCAB = {w: 5 for w in "SAM JAYA PERKASA BELEFINA SARANA MEDIKA RUMAH SAKIT UMUM DAERAH DR PIRNGADI CONTOH SEJAHTERA ABADI PT CV".split()}

NEW_CARD = ["Odjp", "npwp 70.895.848.3-428.001", "PERSEROANTERBATAS-BADANSAMJAYAPERKASA", "NPWP16:0708958483428001",
            "JLPAJAJARAN,123A,ARJUNA,CICENDO,KOTA", "BANDUNG,JAWABARAT,4O172", "KPPPRATAMABANDUNGBOJONAGARA", "TanggalTerdaftar29/08/2014"]
OLD_CARD = ["DIREKTORAT JENDERAL PAJAK KEMENTERIAN KEUANGAN REPUBLIK INDONESIA", "NPWp : 01.234.567.8-901.000", "PT CONTOH SEJAHTERA ABADI",
            "NIK :", "JL. MELATI RAYA NO. 12 RT 003 RW 004", "KEBAYORAN BARU, JAKARTA SELATAN 12160", "KPP PRATAMA JAKARTA KEBAYORAN BARU SATU",
            "Terdaftar : 12-03-2015"]
INDIVIDUAL_CARD = ["KEMENTERIAN KEUANGAN REPUBLIK INDONESIA", "DIREKTORAT JENDERAL PAJAK", "NPWp : 3171 0456 0187 0002", "NAMA : STELLA CONTOH MANSUR",
                   "NIK : 3171045601870002", "JL. KENANGA II NO. 8", "KPP PRATAMA JAKARTA TEBET"]
KTP = ["PROVINSI DKI JAKARTA", "JAKARTA SELATAN", "NIK :3174012507850003", "Nama : ANDI CONTOH PRATAMA", "Tempat/T gl Lahir : JAKARTA, 25-07-1985",
       "Jenis Kelamin : LAKi-LAKI Gol. Darah : O", "Alamat : JL. ANGGREK NO. 5", "RT/RW : 004/007", "Kel/Desa : CILANDAK BARAT", "Agama : ISLAM"]
SKT = ["DIREKTORAT JENDERAL PAJAK", "SURAT KETERANGAN TERDAFTAR", "Nomor: S-1234KT/WPJ.04/KP.0503/2024", "Nama : CV MAJU BERSAMA JAYA",
       "NPWP : 0987654321012000", "Alamat : JL. DAMAI NO. 3, BEKASI", "Kategori : Badan"]

# The card Coretax issues since 2025: nothing on it has a label (the word npwp is a picture).
CORETAX = ["KANTOR PELAYANAN PAJAK PRATAMA BEKASI BARAT", "1000 0000 0123 4567", "CONTOH ELEKTRONIKA UTAMA",
           "PLAZA CONTOH BEKASI, LANTAI 7, JL. BULEVAR", "AHMAD YANI RT. 000 RW. 000, HARAPANMULYA,",
           "MEDANSATRIA, KOTA BEKASI, JAWA BARAT", "TANGGAL TERDAFTAR 25/07/2025"]
# The same card photographed: RapidOCR's rows.
CORETAX_OCR = ["np/p. KANTOR PELAYANAN PAJAKPRATAMA BEKASIBARAT", "10000000.0123 4567", "CONTOHELEKTRONIKA UTAMA",
               "PLAZA CONTOH BEKASI, LANTAI7, JL.BULEVAR", "AHMAD YANI RT. 00O RW. 00O, HARAPANMULYA,",
               "MEDANSATRIA,KOTA BEKASI,JAWA BARAT Odjp", "TANGGALTERDAFTAR25/07/2025 Odjp"]
CORETAX_PERSON = ["KANTOR PELAYANAN PAJAK PRATAMA MALANG UTARA", "3507 0164 0790 0007", "SITI CONTOH WARDANI",
                  "PERUM CONTOH B NO.1 RT. 001 RW. 002, BLIMBING, KOTA MALANG, JAWA", "TIMUR", "TANGGAL TERDAFTAR 06/02/2010"]


class TestCoretaxCard(unittest.TestCase):
	def test_the_unlabelled_number_name_and_address_are_read(self):
		r = P.parse(CORETAX, source="pdf-text")
		self.assertEqual((r["tax_id"], r["id_type"], r["kind"], r["verified"]), ("1000000001234567", "TIN", "NPWP", True))
		self.assertEqual(r["tax_name"], "CONTOH ELEKTRONIKA UTAMA")
		self.assertEqual(r["tax_address"], "PLAZA CONTOH BEKASI, LANTAI 7, JL. BULEVAR AHMAD YANI RT. 000 RW. 000, HARAPANMULYA, "
		                                   "MEDANSATRIA, KOTA BEKASI, JAWA BARAT")

	def test_a_photo_of_it_is_read_but_never_verified(self):
		r = P.parse(CORETAX_OCR)
		self.assertEqual((r["tax_id"], r["id_type"], r["kind"], r["verified"]), ("1000000001234567", "TIN", "NPWP", False))
		self.assertEqual(r["tax_name"], "CONTOHELEKTRONIKA UTAMA")
		self.assertIn("RT. 000 RW. 000", r["tax_address"])
		self.assertTrue(r["tax_address"].endswith("JAWA BARAT"))  # the DJP logo stays out

	def test_a_persons_card_carries_the_nik(self):
		r = P.parse(CORETAX_PERSON, source="pdf-text")
		self.assertEqual((r["tax_id"], r["id_type"], r["kind"], r["tax_name"]), ("3507016407900007", "NIK", "NPWP", "SITI CONTOH WARDANI"))
		self.assertTrue(r["tax_address"].endswith("KOTA MALANG, JAWA TIMUR"))

	def test_a_wrapped_name_and_a_wrapped_office(self):
		r = P.parse(["KANTOR PELAYANAN PAJAK PRATAMA JAKARTA KELAPA", "GADING", "0001 2345 6780 1000",
		             "POLTEKES KEMENKES CONTOH DIREKTORAT JENDERAL SUMBER DAYA", "MANUSIA KESEHATAN KEMENTERIAN KESEHATAN",
		             "JL. SOEKARNO-HATTA RT. 000", "RW. 000, LAGANG", "TANGGAL TERDAFTAR 01/04/2020"], source="pdf-text")
		self.assertEqual(r["tax_name"], "POLTEKES KEMENKES CONTOH DIREKTORAT JENDERAL SUMBER DAYA MANUSIA KESEHATAN KEMENTERIAN KESEHATAN")
		self.assertEqual(r["tax_address"], "JL. SOEKARNO-HATTA RT. 000 RW. 000, LAGANG")

	def test_a_16_digit_run_off_a_card_is_not_an_npwp(self):
		"""A virtual account on an invoice: no office above it, no registration date below."""
		for lines in (["PT CONTOH", "Virtual Account", "1000 0000 0123 4567", "Total 20.000.000"],
		              ["KANTOR PELAYANAN PAJAK PRATAMA BEKASI BARAT", "Nomor", "1000 0000 0123 4567", "Total 20.000.000"]):
			self.assertIsNone(P.parse(lines, source="pdf-text")["tax_id"])


class Test2024CardLayout(unittest.TestCase):
	def _card(self, name_rows, id_row="NPWP16 : 0001 2345 6765 5000"):
		return P.parse(["KPP PRATAMA PARE", "00.123.456.7-655.000", *name_rows, id_row, "GEDUNG CONTOH STRATEGIC - SOUTH",
		                "TOWER LT.20, JL JENDRAL SUDIRMAN,", "KAB. NGANJUK, JAWA", "TIMUR, 64411", "Tanggal Terdaftar 01/04/2020"], source="pdf-text")

	def test_kabupaten_in_a_name_is_a_name(self):
		r = self._card(["RUMAH SAKIT UMUM DAERAH NGANJUK KABUPATEN NGANJUK"])
		self.assertEqual(r["tax_name"], "RUMAH SAKIT UMUM DAERAH NGANJUK KABUPATEN NGANJUK")
		self.assertEqual(r["tax_address"], "GEDUNG CONTOH STRATEGIC - SOUTH TOWER LT.20, JL JENDRAL SUDIRMAN, KAB. NGANJUK, JAWA TIMUR, 64411")

	def test_a_name_runs_up_to_the_npwp16_line(self):
		self.assertEqual(self._card(["RS PARU CONTOH DITJEN", "PELAYANAN KESEHATAN"])["tax_name"], "RS PARU CONTOH DITJEN PELAYANAN KESEHATAN")

	def test_npwp16_that_is_a_nik_is_the_number(self):
		r = self._card(["BUDI CONTOH"], "NPWP16 : 3573011506800001")
		self.assertEqual((r["tax_id"], r["id_type"], r["verified"]), ("3573011506800001", "NIK", True))

	def test_a_nik_beside_the_name_stays_out_of_it(self):
		r = P.parse(["KPP PRATAMA SUBULUSSALAM", "80.123.456.0-107.000", "RINA CONTOH 1110015508900001",
		             "JL.MAWAR, KAB. ACEH SINGKIL, ACEH,", "24785", "12-01-2017"], source="pdf-text")
		self.assertEqual((r["tax_name"], r["tax_address"]), ("RINA CONTOH", "JL.MAWAR, KAB. ACEH SINGKIL, ACEH, 24785"))

	def test_letters_of_a_name_are_not_digits(self):
		"""The I of INTAN became a 17th digit and the card read as nothing."""
		self.assertEqual(P.parse(["KPP PRATAMA X", "NPWP16:3512014912900001 INTAN CONTOH"])["tax_id"], "3512014912900001")

	def test_a_misread_separator_still_reads(self):
		self.assertEqual(P.parse(["DIREKTORATJENDERAL PAJAK", "NPWP :45.123.456.1-017,000", "I G A CONTOH"])["tax_id"], "0451234561017000")

	def test_golden_is_a_name(self):
		self.assertEqual(P.parse(["NPWP : 01.234.567.8-901.000", "PT GOLDEN CONTOH", "JL MAWAR NO 1"])["tax_name"], "PT GOLDEN CONTOH")


class TestNumbers(unittest.TestCase):
	def test_new_card_verifies_itself_through_its_two_number_lines(self):
		r = P.parse(NEW_CARD)
		self.assertEqual(r["tax_id"], "0708958483428001")
		self.assertEqual(r["id_type"], "TIN")
		self.assertTrue(r["verified"])
		self.assertEqual(r["kind"], "NPWP")

	def test_old_card_read_once_is_a_suggestion_in_the_16_digit_form(self):
		r = P.parse(OLD_CARD)
		self.assertEqual(r["tax_id"], "0012345678901000")
		self.assertFalse(r["verified"])
		self.assertIn("15-digit", " ".join(r["notes"]))

	def test_individuals_npwp_that_is_their_nik_is_typed_nik(self):
		"""Coretax's own rule: a NIK-shaped 16-digit NPWP is an orang pribadi."""
		r = P.parse(INDIVIDUAL_CARD)
		self.assertEqual((r["tax_id"], r["id_type"]), ("3171045601870002", "NIK"))
		self.assertTrue(r["verified"])  # NPWP and NIK lines agree

	def test_ktp_is_never_verified_from_pixels(self):
		r = P.parse(KTP)
		self.assertEqual((r["tax_id"], r["id_type"], r["kind"]), ("3174012507850003", "NIK", "KTP"))
		self.assertFalse(r["verified"])

	def test_born_digital_pdf_with_a_labelled_number_is_verified(self):
		r = P.parse(SKT, source="pdf-text")
		self.assertEqual(r["tax_id"], "0987654321012000")
		self.assertTrue(r["verified"])
		self.assertEqual(r["kind"], "Letter")

	def test_two_different_numbers_under_the_npwp_label_are_never_verified(self):
		r = P.parse(["NPWP : 01.234.567.8-901.000", "PT X", "NPWP16: 0012345678901001"])
		self.assertFalse(r["verified"])
		self.assertIn("two different numbers", " ".join(r["notes"]))

	def test_ocr_letter_confusions_inside_a_number_are_repaired(self):
		r = P.parse(["NPWP : O1.234.567.8-9O1.OOO", "PT CONTOH"])
		self.assertEqual(r["tax_id"], "0012345678901000")

	def test_nik_plausibility(self):
		self.assertTrue(P.nik_plausible("3174012507850003"))
		self.assertTrue(P.nik_plausible("3174016507850003"))  # a woman: day + 40
		self.assertFalse(P.nik_plausible("0012345678901000"))  # province 00 -- an NPWP
		self.assertFalse(P.nik_plausible("3174013507850003"))  # day 35


class TestNameAndAddress(unittest.TestCase):
	def test_old_card_name_is_the_unlabelled_line_under_the_number(self):
		self.assertEqual(P.parse(OLD_CARD)["tax_name"], "PT CONTOH SEJAHTERA ABADI")

	def test_labelled_name_and_address_win(self):
		r = P.parse(KTP)
		self.assertEqual(r["tax_name"], "ANDI CONTOH PRATAMA")
		self.assertEqual(r["tax_address"], "JL. ANGGREK NO. 5")

	def test_card_address_spans_two_rows_and_the_postcode_letter_is_a_digit(self):
		r = P.parse(NEW_CARD)
		self.assertEqual(r["tax_address"], "JLPAJAJARAN, 123A, ARJUNA, CICENDO, KOTA BANDUNG, JAWABARAT, 40172")
		self.assertEqual(P.parse(OLD_CARD)["tax_address"], "JL. MELATI RAYA NO. 12 RT 003 RW 004, KEBAYORAN BARU, JAKARTA SELATAN 12160")

	def test_kpp_and_date_lines_are_not_mistaken_for_a_name(self):
		r = P.parse(["NPWP : 01.234.567.8-901.000", "KPP PRATAMA JAKARTA", "Terdaftar : 01-01-2020"])
		self.assertIsNone(r["tax_name"])


class TestReader(unittest.TestCase):
	def _box(self, x, y, w, text):
		return [[[x, y], [x + w, y], [x + w, y + 20], [x, y + 20]], text, 0.9]

	def test_the_back_of_the_card_beside_the_front_stays_out(self):
		from erpbio_indonesia_localization.tax_ocr.reader import _rows

		rows = _rows([self._box(300, 10, 400, "KANTORPELAYANANPAJAKPRATAMA BEKASIBARAT"), self._box(900, 10, 200, "www.pajak.go.id"),
		              self._box(50, 100, 500, "JL. BULEVAR"), self._box(950, 100, 300, "Kartuiniharapdisimpan")])
		self.assertEqual(rows, ["KANTORPELAYANANPAJAKPRATAMA BEKASIBARAT", "JL. BULEVAR"])

	def test_a_back_below_the_front_removes_nothing_from_it(self):
		from erpbio_indonesia_localization.tax_ocr.reader import _rows

		rows = _rows([self._box(300, 10, 400, "KPPPRATAMABEKASI"), self._box(50, 100, 500, "JL. BULEVAR"), self._box(50, 300, 200, "www.pajak.go.id")])
		self.assertEqual(len(rows), 3)

	def _pdf(self, mode):
		import tempfile

		text = "BT /F1 12 Tf %d Tr 50 700 Td (NPWP 01.234.567.8-901.000 PT CONTOH SEJAHTERA ABADI JAKARTA) Tj ET" % mode
		objs = ["<</Type/Catalog/Pages 2 0 R>>", "<</Type/Pages/Kids[3 0 R]/Count 1>>",
		        "<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
		        "<</Length %d>>stream\n%s\nendstream" % (len(text), text), "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
		out, offsets = "%PDF-1.4\n", []
		for i, o in enumerate(objs, 1):
			offsets.append(len(out))
			out += "%d 0 obj%s\nendobj\n" % (i, o)
		xref = len(out)
		out += "xref\n0 6\n0000000000 65535 f \n" + "".join("%010d 00000 n \n" % o for o in offsets)
		out += "trailer<</Size 6/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % xref
		f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
		f.write(out.encode())
		f.close()
		self.addCleanup(__import__("os").unlink, f.name)
		return f.name

	def test_a_scanners_hidden_text_layer_is_not_issued_text(self):
		from erpbio_indonesia_localization.tax_ocr import reader

		self.assertEqual(reader.read_pdf_text_only(self._pdf(0))[1], "pdf-text")
		with self.assertRaises(reader.EngineMissing):
			reader.read_pdf_text_only(self._pdf(3))


class TestSegmentation(unittest.TestCase):
	def test_legal_form_prefix_comes_off_spaced_or_glued(self):
		self.assertEqual(strip_legal_form("PERSEROANTERBATAS-BADANSAMJAYAPERKASA"), ("SAMJAYAPERKASA", "PERSEROAN TERBATAS - BADAN"))
		self.assertEqual(strip_legal_form("PERSEROAN TERBATAS - BADAN SAM JAYA PERKASA"), ("SAM JAYA PERKASA", "PERSEROAN TERBATAS - BADAN"))
		self.assertEqual(strip_legal_form("BADAN PENDIDIKAN TINGGI CONTOH"), ("BADAN PENDIDIKAN TINGGI CONTOH", None))
		self.assertEqual(strip_legal_form("YAYASAN - BADAN KASIH IBU"), ("KASIH IBU", "YAYASAN - BADAN"))
		self.assertEqual(strip_legal_form("PT CONTOH SEJAHTERA ABADI"), ("PT CONTOH SEJAHTERA ABADI", None))

	def test_glued_name_is_respaced_from_the_vocabulary(self):
		self.assertEqual(segment("SAMJAYAPERKASA", VOCAB), "SAM JAYA PERKASA")
		self.assertEqual(segment("BELEFINASARANAMEDIKA", VOCAB), "BELEFINA SARANA MEDIKA")
		self.assertEqual(segment("RUMAHSAKITUMUMDAERAHDRPIRNGADI", VOCAB), "RUMAH SAKIT UMUM DAERAH DR PIRNGADI")

	def test_unknown_token_stays_glued_rather_than_sprayed_into_letters(self):
		self.assertEqual(segment("CVMAJUBERSAMAJAYA", VOCAB), "CV MAJUBERSAMA JAYA")

	def test_recover_name_keeps_spaces_the_ocr_kept(self):
		self.assertEqual(recover_name("PERSEROANTERBATAS-BADANSAMJAYAPERKASA", VOCAB), ("SAM JAYA PERKASA", "PERSEROAN TERBATAS - BADAN"))
		self.assertEqual(recover_name("PT CONTOH SEJAHTERA ABADI", VOCAB), ("PT CONTOH SEJAHTERA ABADI", None))
		self.assertEqual(recover_name("STELLA CONTOH MANSUR", VOCAB), ("STELLA CONTOH MANSUR", None))
