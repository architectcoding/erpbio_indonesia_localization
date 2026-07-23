frappe.ui.form.on("Coretax Faktur Export", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Fetch Invoices"), () => {
			frm.call("fetch_invoices").then((r) => {
				frm.reload_doc();
				const d = r.message || {};
				frappe.show_alert({
					message: __("{0} invoices found, {1} valid", [d.total, d.valid]),
					indicator: d.valid ? "green" : "orange",
				});
			});
		});
		if ((frm.doc.invoices || []).some((r) => r.ok)) {
			frm.add_custom_button(__("Generate Coretax File"), () => {
				frm.call("generate").then((r) => {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Generated for {0} invoices", [r.message.invoices]),
						indicator: "green",
					});
				});
			}).addClass("btn-primary");
		}
	},
});
