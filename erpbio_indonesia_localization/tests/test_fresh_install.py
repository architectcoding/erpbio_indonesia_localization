"""A fresh `install-app` must get through Frappe's init_singles: no database, the doctype JSON alone.

frappe.installer.install_app saves every Single with its JSON defaults (add_to_installed_apps ->
post_install -> init_singles) BEFORE this app's after_install (setup_eil) seeds anything. A Link
default on a Single therefore points at a record that does not exist yet, the save fails link
validation, and the install stops half-done: listed as installed, with after_install, fixtures and
patch bookkeeping never run. Indonesia Tax Settings.pemungut_transaction_code = "02" did exactly
that (Lark 2026-10-07, kelola-fresh 2026-10-06). Defaults like that belong in
setup/install.py: seed_settings_defaults(), which runs after the records are seeded.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_fresh_install
"""
import json
import unittest
from pathlib import Path

import erpbio_indonesia_localization

LINK_TYPES = ("Link", "Dynamic Link", "Table MultiSelect")


def _app_doctypes():
	root = Path(erpbio_indonesia_localization.__file__).parent
	for path in sorted(root.glob("*/doctype/*/*.json")):
		meta = json.loads(path.read_text())
		if meta.get("doctype") == "DocType" and path.stem == path.parent.name:
			yield meta


class TestFreshInstall(unittest.TestCase):
	def test_the_doctypes_are_found(self):
		names = {meta["name"] for meta in _app_doctypes()}
		self.assertIn("Indonesia Tax Settings", names)

	def test_no_single_has_a_link_default(self):
		offenders = [
			f"{meta['name']}.{field['fieldname']} = {field['default']!r}"
			for meta in _app_doctypes()
			if meta.get("issingle")
			for field in meta.get("fields", [])
			if field.get("fieldtype") in LINK_TYPES and field.get("default")
		]
		self.assertEqual(
			offenders,
			[],
			"init_singles saves these before after_install seeds their targets; "
			"set them in setup/install.py: seed_settings_defaults() instead",
		)


if __name__ == "__main__":
	unittest.main()
