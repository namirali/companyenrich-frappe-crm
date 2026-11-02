frappe.ui.form.on("CompanyEnrich Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Check saved API key (free)"), async () => {
      if (frm.is_dirty()) return frappe.msgprint(__("Save settings first."));
      const result = await frappe.call({ method: "companyenrich_crm.api.check_connection", type: "POST" });
      frappe.msgprint({ title: __("CompanyEnrich"), message: __("API key works. Remaining credits: {0}", [String(result.message.remaining_credits ?? "unknown")]) });
    });
  },
});
