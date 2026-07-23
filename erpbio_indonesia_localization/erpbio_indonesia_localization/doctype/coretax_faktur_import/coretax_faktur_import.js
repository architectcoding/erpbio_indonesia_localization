frappe.ui.form.on("Coretax Faktur Import", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.import_file) return;
		if (frm.doc.status !== "Applied") {
			frm.add_custom_button(__("Preview"), () => {
				frm.call("preview").then((r) => {
					frm.reload_doc();
					const d = r.message || {};
					frappe.show_alert({
						message: __("{0} rows, {1} matched", [d.total, d.matched]),
						indicator: d.matched ? "green" : "orange",
					});
				});
			});
		}
		if (frm.doc.status === "Previewed" && (frm.doc.rows || []).some((r) => r.ok)) {
			frm.add_custom_button(__("Apply to Sales Invoices"), () => {
				frappe.confirm(
					__("Write the faktur numbers onto the matched Sales Invoices?"),
					() => {
						frm.call("apply").then((r) => {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Applied to {0} invoices", [r.message.applied]),
								indicator: "green",
							});
						});
					}
				);
			}).addClass("btn-primary");
		}
	},
});
