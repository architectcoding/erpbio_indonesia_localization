# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Seed the BPA1 print format — the sheet the employee is actually handed.

Shipped as a seeded Print Format rather than a file so it stays editable in
Desk: a company will want its own letterhead and signatory wording, and a format
that can only be changed by editing the app is a format that gets replaced by a
hand-made one.

Re-seeded on every migrate only while untouched. `_is_ours` compares against the
shipped HTML, so once someone edits the format their version is left alone.
"""

import frappe

FORMAT_NAME = "BPA1 - Bukti Pemotongan PPh 21 Tahunan"

HTML = """
<div class="bpa1">
  <div class="head">
    <div class="title">BUKTI PEMOTONGAN PAJAK PENGHASILAN PASAL 21</div>
    <div class="subtitle">TAHUNAN — PEGAWAI TETAP (BPA1)</div>
    <div class="year">Tahun Pajak {{ doc.tax_year }}</div>
  </div>

  <table class="parties">
    <tr>
      <td>
        <div class="lbl">Pemotong</div>
        <div class="val">{{ doc.company }}</div>
        <div class="lbl">NPWP</div>
        <div class="val mono">{{ frappe.db.get_value("Company", doc.company, "tax_id") or "-" }}</div>
      </td>
      <td>
        <div class="lbl">Penerima Penghasilan</div>
        <div class="val">{{ doc.employee_name }}</div>
        <div class="lbl">NPWP / NIK</div>
        <div class="val mono">{{ doc.npwp or doc.nik or "-" }}</div>
        <div class="lbl">Status PTKP</div>
        <div class="val">{{ doc.ptkp_status }}{% if doc.ter_category %} &middot; TER {{ doc.ter_category }}{% endif %}</div>
      </td>
    </tr>
  </table>

  <table class="calc">
    <tr class="section"><td colspan="2">A. PENGHASILAN BRUTO</td></tr>
    {{ row("1. Gaji atau Uang Pensiun Berkala", doc.gaji) }}
    {{ row("2. Tunjangan Lainnya, Uang Lembur dan Sebagainya", doc.tunjangan) }}
    {{ row("3. Natura/Kenikmatan yang Dikenakan Pemotongan", doc.natura) }}
    {{ row("4. Tantiem, Bonus, Gratifikasi, Jasa Produksi dan THR", doc.tantiem_bonus_thr) }}
    {{ row("5. Premi Asuransi Dibayar Pemberi Kerja", doc.premi_asuransi) }}
    {{ row("Jumlah Penghasilan Bruto", doc.gross, True) }}

    <tr class="section"><td colspan="2">B. PENGURANGAN</td></tr>
    {{ row("6. Biaya Jabatan / Biaya Pensiun", doc.biaya_jabatan) }}
    {{ row("7. Iuran Terkait Pensiun atau Hari Tua", doc.iuran_pensiun) }}
    {{ row("8. Zakat / Sumbangan Keagamaan Wajib", doc.zakat) }}
    {{ row("Jumlah Pengurangan", doc.total_pengurangan, True) }}

    <tr class="section"><td colspan="2">C. PENGHASILAN KENA PAJAK</td></tr>
    {{ row("9. Penghasilan Neto Setahun", doc.neto) }}
    {{ row("&nbsp;&nbsp;&nbsp;PTKP — untuk Wajib Pajak sendiri", doc.ptkp_self) }}
    {% if doc.ptkp_married %}{{ row("&nbsp;&nbsp;&nbsp;PTKP — tambahan karena menikah", doc.ptkp_married) }}{% endif %}
    {% if doc.ptkp_dependants %}{{ row("&nbsp;&nbsp;&nbsp;PTKP — tambahan tanggungan", doc.ptkp_dependants) }}{% endif %}
    {{ row("10. PTKP Setahun", doc.ptkp) }}
    {{ row("11. Penghasilan Kena Pajak Setahun", doc.pkp, True) }}

    <tr class="section"><td colspan="2">D. PPh PASAL 21</td></tr>
    {% if doc.pasal17_detail %}
    <tr><td class="detail" colspan="2">
      {% for line in doc.pasal17_detail.split("\\n") %}<div class="mono">{{ line }}</div>{% endfor %}
    </td></tr>
    {% endif %}
    {{ row("12. PPh Pasal 21 Terutang Setahun", doc.annual_tax, True) }}
    {{ row("13. PPh Pasal 21 Telah Dipotong", doc.tax_withheld_total) }}
    {% if doc.withheld_previous_employer %}
      {{ row("14. Dipotong Pemberi Kerja Sebelumnya", doc.withheld_previous_employer) }}
    {% endif %}
    {% if doc.dtp %}{{ row("15. PPh Pasal 21 Ditanggung Pemerintah", doc.dtp) }}{% endif %}
  </table>

  {% if doc.difference|round(0) != 0 %}
  <div class="warn">
    Selisih {{ frappe.utils.fmt_money(doc.difference, currency="IDR") }} antara pajak terutang dan
    yang telah dipotong. Periksa apakah seluruh masa pajak sudah diproses.
  </div>
  {% endif %}

  <div class="foot">
    <div class="note">
      {% if doc.months_worked and doc.months_worked < 12 %}
        Masa kerja {{ doc.months_worked }} bulan dalam tahun pajak ini.
        {% if doc.annualised %}Penghasilan disetahunkan.{% endif %}
      {% endif %}
    </div>
    <div class="sign">
      <div>{{ doc.company }}</div>
      <div class="space"></div>
      <div class="line">Pemotong Pajak</div>
      <div class="small">{{ doc.bp_number or "" }}{% if doc.bp_date %} &middot; {{ frappe.utils.formatdate(doc.bp_date, "d MMMM yyyy") }}{% endif %}</div>
    </div>
  </div>
</div>

<style>
.bpa1 { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 11px; color: #111; }
.bpa1 .head { text-align: center; margin-bottom: 14px; }
.bpa1 .title { font-size: 13px; font-weight: 700; letter-spacing: .02em; }
.bpa1 .subtitle { font-size: 11px; font-weight: 600; margin-top: 2px; }
.bpa1 .year { margin-top: 4px; }
.bpa1 table { width: 100%; border-collapse: collapse; }
.bpa1 .parties td { width: 50%; vertical-align: top; border: 1px solid #999; padding: 6px 8px; }
.bpa1 .lbl { font-size: 9px; text-transform: uppercase; color: #666; margin-top: 4px; }
.bpa1 .lbl:first-child { margin-top: 0; }
.bpa1 .val { font-weight: 600; }
.bpa1 .mono { font-variant-numeric: tabular-nums; }
.bpa1 .calc { margin-top: 10px; border: 1px solid #999; }
.bpa1 .calc td { padding: 3px 8px; border-bottom: 1px solid #e5e5e5; }
.bpa1 .calc tr.section td { background: #f2f2f2; font-weight: 700; font-size: 10px;
  text-transform: uppercase; letter-spacing: .03em; border-bottom: 1px solid #999; }
.bpa1 .calc td.amt { text-align: right; width: 30%; font-variant-numeric: tabular-nums; }
.bpa1 .calc tr.total td { font-weight: 700; border-top: 1px solid #999; }
.bpa1 .calc td.detail { padding-left: 24px; color: #444; }
.bpa1 .warn { margin-top: 10px; padding: 6px 8px; border: 1px solid #c00; color: #c00; }
.bpa1 .foot { margin-top: 18px; display: flex; justify-content: space-between; align-items: flex-end; }
.bpa1 .note { font-size: 10px; color: #444; max-width: 60%; }
.bpa1 .sign { text-align: center; min-width: 220px; }
.bpa1 .sign .space { height: 52px; }
.bpa1 .sign .line { border-top: 1px solid #333; padding-top: 3px; }
.bpa1 .sign .small { font-size: 9px; color: #666; margin-top: 2px; }
</style>
"""

# Jinja has no macros in Frappe print formats, so the row helper is inlined as a
# filter-free include at the top of the template.
MACRO = """
{%- macro row(label, amount, total=False) -%}
<tr class="{{ 'total' if total else '' }}">
  <td>{{ label }}</td>
  <td class="amt">{{ frappe.utils.fmt_money(amount or 0, currency="IDR") }}</td>
</tr>
{%- endmacro -%}
"""


def seed_print_format():
	"""Create or refresh the shipped BPA1 format, leaving edited copies alone."""
	html = MACRO + HTML
	if frappe.db.exists("Print Format", FORMAT_NAME):
		existing = frappe.get_doc("Print Format", FORMAT_NAME)
		if existing.html == html or not existing.get("custom_format"):
			return  # unchanged, or someone switched it to the builder — leave it
		if existing.modified_by not in ("Administrator", None):
			return  # edited by a person; theirs wins
		existing.html = html
		existing.save(ignore_permissions=True)
		return

	frappe.get_doc({
		"doctype": "Print Format",
		"name": FORMAT_NAME,
		"doc_type": "EIL Bukti Potong A1",
		"module": "ERPbio Indonesia Localization",
		"custom_format": 1,
		"print_format_type": "Jinja",
		"standard": "No",
		"html": html,
	}).insert(ignore_permissions=True)
