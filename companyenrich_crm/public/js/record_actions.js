for (const doctype of ['CRM Lead', 'CRM Organization']) {
  frappe.ui.form.on(doctype, {
    refresh(frm) {
      if (frm.is_new() || !frappe.user.has_role(['CompanyEnrich User', 'System Manager'])) return;
      frm.add_custom_button(__('CompanyEnrich'), () => {
        if (frm.is_dirty()) {
          frappe.msgprint(__('Save your changes before opening CompanyEnrich.'));
          return;
        }
        const params = new URLSearchParams({doctype: frm.doctype, name: frm.doc.name});
        window.open('/app/companyenrich-research?' + params.toString(), '_blank', 'noopener,noreferrer');
      });
    },
  });
}
