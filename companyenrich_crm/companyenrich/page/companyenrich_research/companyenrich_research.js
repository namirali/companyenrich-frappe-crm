frappe.pages['companyenrich-research'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: __('CompanyEnrich Research'), single_column: true});
  const root = document.createElement('div');
  root.className = 'p-4';
  page.main[0].appendChild(root);
  const add = (tag, text, parent = root) => {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    parent.appendChild(element);
    return element;
  };
  add('p', __('Research companies and people with CompanyEnrich. Requests use your site’s API key and may consume credits. Nothing runs automatically.'));
  const docs = add('a', __('API documentation'));
  docs.href = 'https://docs.companyenrich.com';
  docs.target = '_blank';
  docs.rel = 'noopener noreferrer';
  const referenceLabel = add('p');
  const profileButtons = add('div');
  const selectorId = 'companyenrich-operation';
  const label = add('label', __('Operation'));
  label.htmlFor = selectorId;
  const select = add('select');
  select.id = selectorId;
  select.className = 'form-control mb-3';
  const cost = add('p');
  const parametersLabel = add('label', __('Parameters (JSON)'));
  parametersLabel.htmlFor = 'companyenrich-parameters';
  const parameters = add('textarea');
  parameters.id = 'companyenrich-parameters';
  parameters.className = 'form-control mb-3';
  parameters.rows = 12;
  parameters.spellcheck = false;
  add('p', __('Review the example before running. Use quoted strings for large person IDs. People search returns professional profiles, not email addresses.'));
  const run = add('button', __('Run request'));
  run.type = 'button';
  run.className = 'btn btn-primary';
  const status = add('p');
  status.setAttribute('aria-live', 'polite');
  const result = add('pre');
  result.style.whiteSpace = 'pre-wrap';
  result.style.overflowWrap = 'anywhere';
  let context = null;
  let busy = false;
  const call = async (method, args) => (await frappe.call({method: 'companyenrich_crm.api.' + method, type: 'POST', args})).message;
  const display = (response) => {
    result.textContent = JSON.stringify(response.data, null, 2);
    status.textContent = response.credits_consumed == null
      ? __('Credit usage was not reported by the API.')
      : __('Reported credits: {0}', [response.credits_consumed]);
    if (response.updated_fields) {
      status.textContent += ' ' + (response.updated_fields.length
        ? __('Filled fields: {0}. Reload the CRM record to see changes.', [response.updated_fields.join(', ')])
        : __('No missing supported fields were available to fill.'));
      context.reference.modified = response.modified;
    }
  };
  const execute = async (action) => {
    if (busy) return;
    busy = true;
    run.disabled = true;
    select.disabled = true;
    parameters.disabled = true;
    profileButtons.querySelectorAll('button').forEach((button) => button.disabled = true);
    status.textContent = __('Request in progress…');
    result.textContent = '';
    try { display(await action()); }
    catch (error) {
      let detail = '';
      try {
        const messages = JSON.parse(error.responseJSON?._server_messages || '[]');
        detail = messages.map((entry) => JSON.parse(entry).message).filter((message) => typeof message === 'string').join(' ');
      } catch (_) { /* Never display raw exceptions or response bodies. */ }
      status.textContent = (detail ? detail + ' ' : '') + __('Request did not complete; requests are never automatically retried.');
    }
    finally {
      busy = false;
      run.disabled = false;
      select.disabled = false;
      parameters.disabled = false;
      profileButtons.querySelectorAll('button').forEach((button) => button.disabled = false);
    }
  };
  const fill = (kind) => {
    frappe.confirm(__('Fill only missing profile fields on this saved record? This performs a CompanyEnrich lookup and may consume credits.'), () => execute(() => call('enrich_document', {doctype: context.reference.doctype, name: context.reference.name, modified: context.reference.modified, kind})));
  };
  select.addEventListener('change', () => {
    const operation = context.operations.find((entry) => entry.id === select.value);
    const example = JSON.parse(JSON.stringify(operation.example));
    if (context.reference?.domain && example.query?.domain) example.query.domain = context.reference.domain;
    if (context.reference?.email && example.body?.email) example.body.email = context.reference.email;
    parameters.value = JSON.stringify(example, null, 2);
    cost.textContent = operation.cost;
  });
  run.addEventListener('click', () => execute(() => call('query', {operation: select.value, parameters: parameters.value, doctype: context.reference?.doctype, name: context.reference?.name})));
  wrapper.companyenrichLoad = async () => {
    if (busy) return;
    const query = new URLSearchParams(window.location.search);
    context = null;
    result.textContent = '';
    referenceLabel.textContent = '';
    parameters.value = '';
    run.disabled = true;
    select.replaceChildren();
    profileButtons.replaceChildren();
    try {
      context = await call('get_context', {doctype: query.get('doctype') || undefined, name: query.get('name') || undefined});
      for (const operation of context.operations) {
        const option = add('option', operation.label, select);
        option.value = operation.id;
      }
      const ref = context.reference;
      referenceLabel.textContent = ref ? __('Saved record: {0} / {1}', [ref.doctype, ref.name]) : __('Research results are not automatically saved to CRM.');
      if (ref?.can_write) {
        for (const kind of ['company', ...(ref.doctype === 'CRM Lead' ? ['person'] : [])]) {
          const button = add('button', kind === 'company' ? __('Fill missing company fields') : __('Fill missing person fields'), profileButtons);
          button.className = 'btn btn-default mr-2 mb-3';
          button.type = 'button';
          button.addEventListener('click', () => fill(kind));
        }
      }
      select.dispatchEvent(new Event('change'));
      run.disabled = false;
      status.textContent = '';
    } catch (_) { status.textContent = __('Access unavailable. Ask your System Manager for the CompanyEnrich User role.'); }
  };
};
frappe.pages['companyenrich-research'].on_page_show = function (wrapper) {
  wrapper.companyenrichLoad?.();
};
