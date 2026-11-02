const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const app = path.join(__dirname, '../companyenrich_crm');

test('CRM script exposes an action only after role access and safely encodes record names', async () => {
  const opened = [];
  const context = {call: async () => true, URLSearchParams, window: {open: (...args) => opened.push(args)}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(app, 'public/js/crm_form_script.js'), 'utf8') + '; globalThis.Controller = CE_CONTROLLER;', context);
  const controller = new context.Controller();
  controller.doc = {name: 'lead & other=<script>'};
  await controller.onLoad();
  assert.equal(controller.actions.length, 1);
  controller.actions[0].onClick();
  const url = new URL(opened[0][0], 'https://crm.example');
  assert.equal(url.searchParams.get('name'), controller.doc.name);
  assert.equal(opened[0][2], 'noopener,noreferrer');
  context.call = async () => false;
  const unauthorized = new context.Controller();
  await unauthorized.onLoad();
  assert.equal(unauthorized.actions, undefined);
});

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.style = {}; this.value = ''; this.textContent = ''; }
  appendChild(child) { this.children.push(child); if (this.tag === 'select' && this.children.length === 1) Object.defineProperty(this, 'value', {get: () => this.children[0].value, configurable: true}); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  addEventListener(event, handler) { this.listeners[event] = handler; }
  dispatchEvent(event) { return this.listeners[event.type]?.(); }
  querySelectorAll(tag) { return this.children.filter((child) => child.tag === tag); }
}

test('research page makes no paid request on load and renders provider data as text', async () => {
  const elements = [];
  const calls = [];
  const main = new Element('div');
  const operations = Object.entries(JSON.parse(fs.readFileSync(path.join(app, 'contract.json'))).operations).map(([id, value]) => ({id, ...value}));
  const frappe = {
    pages: {'companyenrich-research': {}},
    ui: {make_app_page: () => ({main: [main]})},
    call: async ({method, args}) => {
      calls.push({method, args});
      return {message: method.endsWith('get_context') ? {operations} : {data: {name: '<img src=x onerror=alert(1)>', id: '9007199254740993'}, credits_consumed: 0}};
    },
  };
  const context = {frappe, URLSearchParams, Event, window: {location: {search: ''}}, document: {createElement: (tag) => { const element = new Element(tag); elements.push(element); return element; }}, __: (text, args = []) => text.replace(/\{(\d+)\}/g, (_, index) => args[index])};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(app, 'companyenrich/page/companyenrich_research/companyenrich_research.js'), 'utf8'), context);
  const wrapper = {};
  frappe.pages['companyenrich-research'].on_page_load(wrapper);
  await wrapper.companyenrichLoad();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'companyenrich_crm.api.get_context');
  assert.equal(elements.find((element) => element.tag === 'select').children.length, 12);
  const params = elements.find((element) => element.tag === 'textarea');
  params.value = '{"query":{"id":"9007199254740993"}}';
  await elements.find((element) => element.textContent === 'Run request').listeners.click();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].args.parameters, params.value);
  const output = elements.find((element) => element.tag === 'pre');
  assert.match(output.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(output.innerHTML, undefined);
  assert.ok(elements.some((element) => element.textContent === 'Reported credits: 0'));
});
