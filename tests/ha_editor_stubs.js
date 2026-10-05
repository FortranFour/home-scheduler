/* Minimal HA form components for the real floor3dx editor integration test.
 * These stand-ins exercise the editor's events; they are not production HA UI. */
customElements.define('home-assistant', class extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:'open'}); }
});
const ha=document.querySelector('home-assistant');
const main=document.createElement('home-assistant-main');main.attachShadow({mode:'open'});ha.shadowRoot.append(main);
let cursor=document.createElement('ha-drawer');main.shadowRoot.append(cursor);
for(const name of ['partial-panel-resolver','ha-panel-lovelace','hui-root','hui-view']) {
  const next=document.createElement(name);cursor.append(next);cursor=next;
}
class EditorForm extends HTMLElement {
  constructor() { super();this.attachShadow({mode:'open'}); }
  set schema(value) { this._schema=value;this.render(); }
  set data(value) { this._data=value;this.render(); }
  set computeLabel(value) { this._label=value;this.render(); }
  render() {
    if(!this._schema || !this._data) return;
    this.shadowRoot.innerHTML='<style>:host{display:block;min-width:0}label{display:flex;flex-direction:column;gap:4px;font:13px Arial;margin:6px 0}input,select{font:inherit;padding:7px;border:1px solid #ccd3da;border-radius:6px;min-width:0;max-width:100%;box-sizing:border-box}fieldset{border:0;padding:0;min-width:0}</style>';
    const fields=(schema,data,container,path=[])=>schema.forEach(field=>{
      const name=field.name, keys=[...path,name];
      if(field.schema) {
        const group=document.createElement('fieldset');container.append(group);
        fields(field.schema,name?(data[name]||{}):data,group,name?keys:path);return;
      }
      const label=document.createElement('label');label.append(this._label?.(field)||name);
      const selector=field.selector||{}, select=selector.select;
      const input=document.createElement(select?'select':'input');
      input.dataset.field=keys.join('.');
      if(select) {
        input.append(new Option('',''));
        for(const item of select.options||[]) input.append(new Option(typeof item==='string'?item:item.label,typeof item==='string'?item:item.value));
        if(data[name] && !Array.from(input.options).some(o=>o.value===String(data[name]))) input.append(new Option(data[name],data[name]));
      } else input.type=selector.boolean?'checkbox':selector.number?'number':'text';
      if(input.type==='checkbox') input.checked=!!data[name];
      else input.value=data[name]??'';
      input.onchange=()=>{
        const value=structuredClone(this._data);let target=value;
        for(const key of keys.slice(0,-1)) target=target[key]??=(typeof key==='number'?[]:{});
        target[name]=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?undefined:Number(input.value)):input.value;
        this.dispatchEvent(new CustomEvent('value-changed',{detail:{value},bubbles:true,composed:true}));
      };
      label.append(input);container.append(label);
    });
    fields(this._schema,this._data,this.shadowRoot);
  }
}
customElements.define('ha-form',EditorForm);
customElements.define('ha-expansion-panel',class extends HTMLElement {
  constructor() {
    super();this.attachShadow({mode:'open'});
    this.shadowRoot.innerHTML='<style>:host{display:block;border:1px solid #d5dce2;border-radius:6px}button{font:14px Arial;background:transparent;border:0;padding:10px;width:100%;text-align:left;cursor:pointer}</style><button></button><div><slot></slot></div>';
    this.shadowRoot.querySelector('button').onclick=()=>{
      this.expanded=!this.expanded;
      this.dispatchEvent(new CustomEvent('expanded-changed',{detail:{expanded:this.expanded}}));
    };
  }
  set header(value) { this.shadowRoot.querySelector('button').textContent=value; }
  get expanded() { return !!this._expanded; }
  set expanded(value) { this._expanded=value;this.shadowRoot.querySelector('div').hidden=!value; }
  connectedCallback() { this.expanded=this._expanded; }
});
for(const name of ['ha-button','ha-icon-button']) customElements.define(name,class extends HTMLElement {
  constructor() { super();this.attachShadow({mode:'open'});this.shadowRoot.innerHTML='<style>:host{display:inline-flex;align-items:center;justify-content:center;cursor:pointer;border:1px solid #d5dce2;border-radius:5px;padding:5px;font:12px Arial;box-sizing:border-box}svg{width:18px;height:18px;fill:currentColor}</style><slot></slot>'; }
  connectedCallback() { this.setAttribute('role','button');this.tabIndex=0; }
  set label(value) { this.setAttribute('aria-label',value); }
  set path(value) {
    let svg=this.shadowRoot.querySelector('svg');
    if(!svg) {svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.innerHTML='<path></path>';this.shadowRoot.append(svg);}
    svg.firstChild.setAttribute('d',value);
  }
});
for(const name of ['ha-icon','ha-svg-icon']) customElements.define(name,class extends HTMLElement {
  constructor() { super();this.attachShadow({mode:'open'});this.shadowRoot.innerHTML='<style>:host{display:inline-block;width:20px;height:20px}svg{width:20px;height:20px;fill:currentColor}</style><svg viewBox="0 0 24 24"><path></path></svg>'; }
  set path(value) { this.shadowRoot.querySelector('path').setAttribute('d',value); }
});
customElements.define('ha-sortable',class extends HTMLElement {});
customElements.define('ha-card',class extends HTMLElement {
  connectedCallback() { this.style.display='block';this.style.background='var(--card-background-color,white)'; }
});
