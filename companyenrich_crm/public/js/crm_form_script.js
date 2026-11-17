class CE_CONTROLLER {
  async onLoad() {
    try {
      if (!await call('companyenrich_crm.api.can_access', {})) return;
      this.actions = [{
        label: 'CompanyEnrich',
        onClick: () => {
          const params = new URLSearchParams({doctype: 'CE_DOCTYPE', name: this.doc.name});
          window.open('/app/companyenrich-research?' + params.toString(), '_blank', 'noopener,noreferrer');
        },
      }];
    } catch (_) {
      // The server restricts spending to the administrator-granted role.
      this.actions = [];
    }
  }
}
