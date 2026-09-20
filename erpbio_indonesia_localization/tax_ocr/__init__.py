"""Reading a party's tax documents (NPWP card, KTP, SKT/SPPKP letter) into their tax identity.

Modelled on the biogear_slide_manager sidecar's label OCR: the same RapidOCR engine, the same
rotation search, the same rule that a machine read is a SUGGESTION a person accepts -- with one
extension the owner asked for: a blank field may be filled automatically, but only from a read that
proves itself (see api.tax_ocr._auto_fill). Raw OCR text is never persisted: a KTP carries religion,
marital status and a birth date, and none of that belongs in the ERP.

  reader.py   -- text acquisition: born-digital PDF text, else OCR (image or rendered PDF page)
  parser.py   -- lines -> {tax_id, id_type, tax_name, tax_address, kind, ...}, pure and unit-tested
  segment.py  -- the legal-form prefix and the spaceless names new DJP cards produce
"""
