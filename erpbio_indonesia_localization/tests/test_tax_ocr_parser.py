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
		self.assertEqual(r["tax_address"], "JLPAJAJARAN, 123A, ARJUNA, CICENDO, KOTA, BANDUNG, JAWABARAT, 40172")
		self.assertEqual(P.parse(OLD_CARD)["tax_address"], "JL. MELATI RAYA NO. 12 RT 003 RW 004, KEBAYORAN BARU, JAKARTA SELATAN 12160")

	def test_kpp_and_date_lines_are_not_mistaken_for_a_name(self):
		r = P.parse(["NPWP : 01.234.567.8-901.000", "KPP PRATAMA JAKARTA", "Terdaftar : 01-01-2020"])
		self.assertIsNone(r["tax_name"])


class TestSegmentation(unittest.TestCase):
	def test_legal_form_prefix_comes_off_spaced_or_glued(self):
		self.assertEqual(strip_legal_form("PERSEROANTERBATAS-BADANSAMJAYAPERKASA"), ("SAMJAYAPERKASA", "PERSEROAN TERBATAS - BADAN"))
		self.assertEqual(strip_legal_form("PERSEROAN TERBATAS - BADAN SAM JAYA PERKASA"), ("SAM JAYA PERKASA", "PERSEROAN TERBATAS - BADAN"))
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
