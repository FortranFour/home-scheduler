/* Home Scheduler & Simulator 0.4.0 — vanilla custom card, no build step. */
const HS_ESCAPE = value => String(value ?? "").replace(/[&<>"']/g, ch =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const HS_BIT = (mask, slot) => !!(parseInt(mask[slot >> 2] || "0",16) & (8 >> (slot % 4)));
const HS_PUT = (mask, slot, value) => {
  const chars=mask.split(""), flag=8>>(slot%4), at=slot>>2, nibble=parseInt(chars[at],16);
  chars[at]=(value?nibble|flag:nibble&~flag).toString(16);return chars.join("");
};
const HS_TIME = minutes => {
  const hour = Math.floor(minutes / 60), minute = minutes % 60;
  return (hour % 12 || 12) + ":" + String(minute).padStart(2,"0") + (hour < 12 ? " AM" : " PM");
};
const HS_DAY = iso => (new Date(iso + "T12:00:00Z").getUTCDay() + 6) % 7;
const HS_DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

class HomeSchedulerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.sourceStarted = false;
    this.lastPlan = this.lastFrame = this.lastSlot = this.localMinute = null;
    this.disposed = false;
    this.renderJob = 0;
    this.sourceJob = 0;
    this.modelChoices = [{id:"demo",name:"Demo home",kind:"demo",url:"/home_scheduler/demo-home.json?v=0.4.0"}];
  }

  setConfig(config) {
    this.config = config; this.showModel=config.show_model !== false;
    if(!this.showModel) {
      this.sourceJob++; this.renderJob++; this.sourceStarted=false;
      clearTimeout(this.rendererTimer);
    }
    this.update();
  }
  getCardSize() { return 12; }
  connectedCallback() {
    const reconnect=this.disposed;
    this.disposed = false;
    if(this.editor && this.editorVisible) this.claimEditor();
    if(this._hass) this.update();
    if(reconnect && this.renderer) {
      if(this.rendererDirty && !this.rendererInvalid)
        this.renderRenderer(this.rendererDraft).catch(error=>this.updateEditorControls(error.message||String(error),true));
      if(this.editorVisible && !this.editor && !this.editorLoading) this.loadEditor();
    }
  }
  disconnectedCallback() {
    this.leaveLearningPreview();
    this.disposed = true; clearTimeout(this.scrubTimer); clearTimeout(this.rendererTimer);
    this.renderJob++; this.finishPaint(false);
    this.sourceJob++;
    if(!this.renderer) this.sourceStarted=false;
    if(HomeSchedulerCard.editorOwner === this) HomeSchedulerCard.editorOwner=null;
  }
  set hass(hass) { this._hass = hass; this.update(); }

  async send(op, values = {}) {
    try {
      await this._hass.callService("home_scheduler","command",{op,...values});
      this.updateFrame();
    } catch(error) {
      this.updatePlan();
      this.shadowRoot.getElementById("error").textContent = error.message || String(error);
    }
  }

  update() {
    if(!this._hass || !this.config || this.disposed) return;
    const plan = this._hass.states["sensor.home_scheduler"];
    const frame = this._hass.states["sensor.home_scheduler_frame"];
    if(!plan) {
      if(!this.built) this.shadowRoot.innerHTML =
        "<ha-card style='padding:20px'>Add Home Scheduler &amp; Simulator in Settings → Devices &amp; services after installing and restarting Home Assistant.</ha-card>";
      return;
    }
    this.plan = plan.attributes;
    this.frame = frame?.attributes;
    if(!this.built) this.build();
    if(plan !== this.lastPlan) { this.updatePlan(); this.lastPlan = plan; }
    if(frame !== this.lastFrame || this.frame?.physical) { this.updateFrame(); this.lastFrame = frame; }
    for(const id of ["model-toolbar","model-status","model-workspace"]) this.shadowRoot.getElementById(id).hidden=!this.showModel;
    if(this.showModel) {
      if(!this.sourceStarted) { this.sourceStarted = true; this.loadRenderer(); }
      if(!this.modelsStarted) { this.modelsStarted=true; this.discoverModels(); }
      this.updateModelSelector();
      this.syncSavedRenderer();
      this.updateModel();
      if(this.editor) this.editor.hass=this.editorHass();
    } else if(this.renderer) {
      this.editor?.remove();this.editor=null;
      this.renderer.remove();this.renderer=null;this.sourceStarted=false;
      this.renderJob++;this.sourceJob++;
      if(HomeSchedulerCard.editorOwner===this) HomeSchedulerCard.editorOwner=null;
    }
  }

  build() {
    this.built = true;
    this.editorVisible=this.config.model_editor !== false;
    const E = HS_ESCAPE;
    let heading = "", quarters = "";
    for(let hour=0;hour<12;hour++) heading += "<th colspan='4'>" +
      String(hour).padStart(2,"0") + " / " + String(hour+12).padStart(2,"0") + " h</th>";
    for(let slot=0;slot<48;slot++) quarters += "<th>"+["00","15","30","45"][slot%4]+"</th>";
    const body = this.deviceRows();
    this.shadowRoot.innerHTML = "<style>"+this.styles()+this.learningStyles()+"</style><ha-card>"+
      "<div class='title'><img class='brand-icon' src='/home_scheduler/icon.svg' alt=''>Home Scheduler &amp; Simulator</div><div id='summary'><strong id='primary'></strong><div id='secondary'></div></div>"+
      "<div class='model-toolbar' id='model-toolbar'><label class='model-choice'>Model<select id='model-select' aria-label='Select home model'></select></label><button id='refresh-models'>Find models</button><button id='import-model-file'>Import configuration…</button><input id='model-file' type='file' accept='.json,.yaml,.yml,.txt' hidden><button id='toggle-editor' aria-controls='editor-pane'></button></div><div id='model-status' class='hint' role='status'>Selecting a model imports its devices and object bindings automatically. Use its floor3dx configuration; the GLB/OBJ file contains geometry only.</div>"+
      "<div id='learn-preview-banner' role='status' hidden></div>"+
      "<div id='model-workspace'><section id='editor-pane' aria-label='House model editor'>"+
      "<div class='editor-heading'><strong>Model editor</strong><div class='editor-actions'>"+
      "<button id='save-model' disabled>Save model</button><button id='discard-model' disabled>Discard</button></div></div>"+
      "<div id='editor-body'>Loading the floor3dx editor…</div>"+
      "<div id='editor-status' role='status'>Edits preview here. Save model to keep them.</div></section>"+
      "<div id='model'><div id='model-message'>Loading the house model…</div></div></div>"+
      "<div class='controls'><button id='play'>Play</button><div class='time'><output id='time'></output>"+
      "<input id='scrubber' type='range' min='0' max='1435' step='5' aria-label='Time of day'></div>"+
      "<label>Speed<select id='speed'><option value='0.25'>¼×</option><option value='0.5'>½×</option>"+
      "<option value='1'>1×</option><option value='2'>2×</option><option value='4'>4×</option></select></label>"+
      "<label class='check'><input id='physical' type='checkbox'>Physical devices</label>"+
      "<label class='check'><input id='clock' type='checkbox'>Follow clock</label>"+
      "<label class='check'><input id='repeat' type='checkbox'>Repeat preview</label></div>"+
      "<div class='edit-controls'><label>Schedule<select id='profile'></select></label>"+
      "<label>Preview date<input id='date' type='date'></label><div id='days'></div>"+
      "<button id='copy'>Copy day to week</button><button id='clone'>Duplicate schedule</button><button id='learn-open' aria-controls='learning-panel' aria-expanded='false'>Learn from actual use…</button></div>"+
      "<details><summary>Names, conditions & presence variation</summary><div class='advanced'>"+
      "<label>Name<input id='name' maxlength='100'></label>"+
      "<label>Activate when entity<input id='condition_entity' placeholder='input_select.scene'></label>"+
      "<label>Equals<input id='condition_state' placeholder='Guest'></label>"+
      "<label>Scene on activation<input id='scene' placeholder='scene.guest'></label>"+
      "<label class='check'><input id='auto' type='checkbox'>Conditional schedules</label>"+
      "<label>Variation ± minutes<input id='jitter' type='number' min='0' max='60' step='1'></label>"+
      "<button id='seed'>New variation</button></div></details>"+
      this.learningHTML()+
      "<div class='type-filters' id='type-filters'></div><details id='device-manager'><summary>Devices, connections &amp; row visibility</summary><div id='device-list'></div><div class='add-device'><label>Type<select id='new-kind'><option value='light'>Light</option><option value='switch'>Switch</option><option value='fan'>Fan</option><option value='cover'>Cover</option><option value='scene'>Scene</option></select></label><label>Name<input id='new-name' maxlength='100' placeholder='My device'></label><label>Real entity (optional)<input id='new-target' list='hs-real-entities' placeholder='Leave blank for simulation'></label><button id='add-device'>Add device</button></div><div class='hint'>New devices appear in the grid; map them to an object using the model editor.</div></details><datalist id='hs-real-entities'></datalist><div id='visibility-hint' class='hint'></div><div class='hint'>Midnight–noon above, noon–midnight below. 1× = one simulated hour per second. A checked scene cell activates once at its start; other cells specify a 15-minute state.</div>"+
      "<div class='bulk-controls'><strong>Visible rows · <span id='bulk-day'></span></strong>"+
      "<button id='select-all'>Select all blocks</button><button id='clear-all'>Clear all</button>"+
      "<label class='check'><input id='touch-paint' type='checkbox'>Touch paint</label></div>"+
      "<div class='hint'>Drag across a device’s boxes to select or clear a range. Start on a checked box to clear. On a phone, enable Touch paint to draw; turn it off to scroll.</div>"+
      "<div id='grid'><table><thead><tr><th rowspan='2' class='label'>Device · <span id='weekday'></span></th>"+
      heading+"<th rowspan='2'>Watts</th><th rowspan='2'>kWh/day</th></tr><tr>"+quarters+
      "</tr></thead><tbody>"+body+"</tbody></table></div><div class='total' id='total'></div>"+
      "<div id='error' role='alert'></div></ha-card>";
    const root=this.shadowRoot, byId=id=>root.getElementById(id);
    const settings=(key,value)=>this.send("settings",{[key]:value});
    byId("toggle-editor").onclick=()=>this.toggleEditor();
    byId("save-model").onclick=()=>this.saveRenderer();
    byId("discard-model").onclick=()=>this.discardRenderer();
    byId("model-select").onchange=event=>{
      const choice=this.modelChoices.find(x=>x.id===event.target.value);
      if(choice) this.selectModel(choice);
    };
    byId("refresh-models").onclick=()=>this.discoverModels();
    byId("import-model-file").onclick=()=>byId("model-file").click();
    byId("model-file").onchange=async event=>{
      const file=event.target.files[0];
      event.target.value="";
      if(!file) return;
      if(file.size>524288) {this.modelStatus("Choose a configuration smaller than 512 KiB.",true);return;}
      try {await this.selectModel({id:"file",name:file.name,source:await file.text()});}
      catch(error) {this.modelStatus(error.message||String(error),true);}
    };
    this.buildDeviceManager();
    this.bindLearning();
    this.updateEditorControls();
    byId("play").onclick=()=>this.send("play");
    for(const key of ["physical","clock","auto","repeat"])
      byId(key).onchange=event=>settings(key,event.target.checked);
    byId("speed").onchange=event=>settings("speed",Number(event.target.value));
    byId("profile").onchange=event=>settings("profile",event.target.value);
    byId("date").onchange=event=>{if(event.target.value) settings("date",event.target.value);};
    byId("jitter").onchange=event=>settings("jitter",Number(event.target.value));
    byId("seed").onclick=()=>settings("seed",this.plan.seed+1);
    byId("copy").onclick=()=>this.send("copy_day",{profile:this.plan.profile,day:HS_DAY(this.plan.date)});
    byId("clone").onclick=()=>this.send("clone",{profile:this.plan.profile});
    byId("select-all").onclick=()=>this.fillDay(true);
    byId("clear-all").onclick=()=>this.fillDay(false);
    byId("touch-paint").onchange=event=>{
      this.finishPaint(false);
      byId("grid").classList.toggle("touch-paint",event.target.checked);
    };
    for(const key of ["name","condition_entity","condition_state","scene"])
      byId(key).onchange=event=>this.send("profile",{profile:this.plan.profile,[key]:event.target.value});
    byId("scrubber").oninput=event=>{
      this.localMinute=Number(event.target.value);
      byId("time").textContent=HS_TIME(this.localMinute);
      clearTimeout(this.scrubTimer);
      this.scrubTimer=setTimeout(()=>{
        const value=this.localMinute; this.localMinute=null; settings("minute",value);
      },150);
    };
    byId("days").innerHTML=HS_DAYS.map((label,day)=>"<button data-day='"+day+"'>"+label+"</button>").join("");
    byId("add-device").onclick=()=>this.send("add_device",{kind:byId("new-kind").value,name:byId("new-name").value,target:byId("new-target").value});
    root.addEventListener("change",event=>{
      const input=event.target;
      let index=input.dataset.row;
      if(index !== undefined) this.send("cell",{
        entity:this.plan.devices[Number(index)].entity,profile:this.plan.profile,
        day:HS_DAY(this.plan.date),slot:Number(input.dataset.slot),value:input.checked});
      else if((index=input.dataset.use) !== undefined) this.send("row",{
        entity:this.plan.devices[Number(index)].entity,profile:this.plan.profile,use:input.checked});
      else if((index=input.dataset.random) !== undefined) this.send("row",{
        entity:this.plan.devices[Number(index)].entity,random:input.checked});
      else if((index=input.dataset.watts) !== undefined) this.send("row",{
        entity:this.plan.devices[Number(index)].entity,watts:Number(input.value)});
      else if(input.dataset.kind !== undefined) this.send("view",{shown_types:Array.from(root.querySelectorAll("[data-kind]:checked"),x=>x.dataset.kind)});
      else if(input.dataset.visible !== undefined) this.send("view",{hidden_devices:Array.from(root.querySelectorAll("[data-visible]"),x=>x).filter(x=>!x.checked).map(x=>x.dataset.visible)});
      else if((index=input.dataset.target) !== undefined) this.send("device",{entity:this.plan.devices[Number(index)].entity,target:input.value});
      else if((index=input.dataset.rename) !== undefined) this.send("device",{entity:this.plan.devices[Number(index)].entity,name:input.value});
      else if((index=input.dataset.travel) !== undefined) this.send("device",{entity:this.plan.devices[Number(index)].entity,travel_seconds:Number(input.value)});
      else if((index=input.dataset.outside) !== undefined) this.send("row",{entity:this.plan.devices[Number(index)].entity,profile:this.plan.profile,outside:input.value});
      else if((index=input.dataset.offPosition) !== undefined) this.send("row",{entity:this.plan.devices[Number(index)].entity,profile:this.plan.profile,off_position:Number(input.value)});
      else if((index=input.dataset.settingRow) !== undefined) this.send("row",{entity:this.plan.devices[Number(index)].entity,profile:this.plan.profile,on:{[input.dataset.setting]:input.type==="color"?input.value:Number(input.value)}});
    });
    root.addEventListener("click",event=>{
      const button=event.target.closest("[data-save-effects]");
      if(button) {
        const index=Number(button.dataset.saveEffects);
        try {this.send("device",{entity:this.plan.devices[index].entity,effects:JSON.parse(root.querySelector("[data-effects='"+index+"']").value)});}
        catch {byId("error").textContent="Preview scene effects must be valid JSON.";}
      }
      const remove=event.target.closest("[data-remove-device]");
      if(remove) this.send("remove_device",{entity:remove.dataset.removeDevice});
    });
    byId("days").onclick=event=>{
      const day=event.target.dataset.day;
      if(day === undefined) return;
      const date=new Date(this.plan.date+"T12:00:00Z");
      date.setUTCDate(date.getUTCDate()+Number(day)-HS_DAY(this.plan.date));
      settings("date",date.toISOString().slice(0,10));
    };
    const grid=byId("grid");
    grid.addEventListener("pointerdown",event=>this.startPaint(event));
    grid.addEventListener("pointermove",event=>{
      if(this.paint?.pointerId !== event.pointerId) return;
      this.paint.x=event.clientX; this.paint.y=event.clientY;
      this.paintAt(event.clientX,event.clientY);
    });
    grid.addEventListener("pointerup",event=>{
      if(this.paint?.pointerId === event.pointerId) this.finishPaint(true);
    });
    for(const type of ["pointercancel","lostpointercapture"])
      grid.addEventListener(type,event=>{
        if(this.paint?.pointerId === event.pointerId) this.finishPaint(false);
      });
    grid.addEventListener("click",event=>{
      if(event.detail && this.suppressPaintClick) {
        this.suppressPaintClick=false; event.preventDefault(); return;
      }
      const button=event.target.closest("[data-fill-row]");
      if(button) { this.fillDay(button.dataset.value==="true",Number(button.dataset.fillRow)); return; }
      const cell=event.target.closest("[data-paint-slot]");
      if(cell && event.target.tagName !== "INPUT") {
        const input=cell.querySelector("input"); input.checked=!input.checked;
        input.dispatchEvent(new Event("change",{bubbles:true}));
      }
    });
  }

  learningHTML() {
    return "<section id='learning-panel' hidden aria-label='Learn from actual use'>"+
      "<div class='learning-heading'><strong>Learn from actual use</strong><button id='learn-close'>Close</button></div>"+
      "<p class='hint'>Observe linked real devices, then review a weekly proposal. Lights are selected by default; switches and fans are optional. Each block needs at least three usable matching weekdays. Unknown blocks keep the existing schedule.</p>"+
      "<div id='learn-scope' class='learn-scope'></div><div class='advanced'>"+
      "<label class='check'><input id='learn-enabled' type='checkbox'>Observe actual use</label>"+
      "<label>Household mode entity (optional)<input id='learn-mode-entity' placeholder='input_select.household_mode' maxlength='100'></label>"+
      "<button id='learn-configure'>Save observation settings</button><button id='learn-history'>Read available Recorder history</button><button id='learn-clear'>Clear learning data</button></div>"+
      "<div class='hint'>Observation pauses for a row while Home Scheduler physically controls it. Clear learning data pauses observation and leaves saved schedules unchanged.</div>"+
      "<div id='learn-status' class='hint' role='status'></div><div class='advanced'>"+
      "<label>Look back<select id='learn-lookback'><option value='28'>4 weeks</option><option value='42' selected>6 weeks</option><option value='56'>8 weeks</option></select></label>"+
      "<label>Consensus %<input id='learn-threshold' type='number' min='50' max='100' value='60'></label>"+
      "<label>Only household mode<input id='learn-mode-state' placeholder='All observed modes' maxlength='64'></label>"+
      "<label class='check'><input id='learn-include-history' type='checkbox'>Include older activity with uncertain source</label>"+
      "<button id='learn-propose'>Generate proposal</button></div>"+
      "<div class='hint'>An ON vote means at least 7½ minutes on in a 15-minute block with at least 90% known coverage. Recorder backfill may include past scheduled activity; it is excluded unless you tick the box above.</div>"+
      "<div id='learn-review' hidden><div id='learn-evidence-summary' class='hint'></div><div class='advanced'>"+
      "<div id='learn-days'></div><button id='learn-preview'>Preview in model</button><button id='learn-play'>Play proposal</button><button id='learn-return'>Return to running view</button>"+
      "<label>Proposal time<output id='learn-time'></output><input id='learn-scrubber' type='range' min='0' max='1425' step='15' value='1080'></label></div>"+
      "<div class='hint'>Shade shows how often the block was ON. Gray = Still learning; existing blocks are retained. Hover or focus a box for counts. You can edit the proposal here. Preview stays virtual even with Physical devices enabled.</div>"+
      "<div id='learn-grid'></div><div class='advanced'><label>New schedule name<input id='learn-name' maxlength='100' value='Learned routine'></label><button id='learn-save'>Save as new schedule</button></div>"+
      "<div class='hint'>Saving keeps the running schedule selected. The new schedule has no automatic condition or activation scene; only the chosen devices are enabled. Select it later when ready to use it.</div></div>"+
      "<div id='learn-message' role='status'></div></section>";
  }

  learningStyles() {
    return "#learning-panel{padding:14px;margin:12px 0;border:1px solid var(--divider-color);border-radius:12px;background:var(--secondary-background-color)}"+
      ".learning-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.learn-scope{display:flex;flex-wrap:wrap;gap:8px 18px;margin:8px 0}"+
      ".learn-scope .check{max-width:280px;align-items:center}#learn-threshold{width:75px}#learn-status,#learn-message{white-space:pre-line}#learn-message{font-size:13px;margin-top:8px}.learn-error{color:var(--error-color)}"+
      "#learn-grid{overflow:auto;max-height:45vh;border:1px solid var(--divider-color);border-radius:8px;margin:8px 0}#learn-grid .label{width:220px}"+
      "#learn-grid td{height:27px}#learn-grid td.learn-known{background:rgba(var(--rgb-primary-color,3,169,244),var(--frequency));box-shadow:inset 0 -2px rgba(var(--rgb-primary-color,3,169,244),.45)}"+
      "#learn-grid td.learn-unknown{background:repeating-linear-gradient(135deg,transparent,transparent 4px,rgba(120,130,140,.14) 4px,rgba(120,130,140,.14) 7px)}"+
      "#learn-grid input{cursor:pointer}#learn-days{display:flex;gap:4px;flex-wrap:wrap}#learn-days .selected{background:var(--primary-color);color:var(--text-primary-color,#fff)}"+
      "#learn-preview-banner{background:rgba(var(--rgb-primary-color,3,169,244),.15);padding:9px;border-radius:8px;font-size:13px;margin:8px 0}";
  }

  bindLearning() {
    const root=this.shadowRoot, by=id=>root.getElementById(id);
    by("learn-open").onclick=()=>{
      by("learning-panel").hidden=!by("learning-panel").hidden;
      by("learn-open").setAttribute("aria-expanded",String(!by("learning-panel").hidden));
      if(by("learning-panel").hidden) this.leaveLearningPreview();
      else this.updateLearningStatus();
    };
    by("learn-close").onclick=()=>{by("learning-panel").hidden=true;by("learn-open").setAttribute("aria-expanded","false");this.leaveLearningPreview();};
    by("learn-enabled").onchange=()=>this.learningAction(()=>this.configureLearning(by("learn-enabled").checked));
    by("learn-configure").onclick=()=>this.learningAction(()=>this.configureLearning(by("learn-enabled").checked));
    by("learn-clear").onclick=()=>this.learningAction(async()=>{
      await this.learningAPI("clear");this.learningProposal=null;this.leaveLearningPreview();
      by("learn-review").hidden=true;this.learnMessage("Learning data cleared. Saved schedules are unchanged.");
    });
    by("learn-history").onclick=()=>this.learningAction(async()=>{
      await this.configureLearning(by("learn-enabled").checked);await this.learningAPI("history");
      this.learnMessage("Backfill status appears above. Generate a proposal after it completes.");
    });
    by("learn-propose").onclick=()=>this.learningAction(async()=>{
      this.leaveLearningPreview();
      const result=await this.learningAPI("propose",{entities:this.learningSelection(),profile:this.plan.profile,
        lookback:Number(by("learn-lookback").value),threshold:Number(by("learn-threshold").value),
        include_history:by("learn-include-history").checked,mode_state:by("learn-mode-state").value});
      this.learningProposal=result;this.learningDay=HS_DAY(result.date);this.learningMinute=1080;
      this.learningMapping=JSON.stringify(this.plan.devices.map(d=>[d.entity,d.target,d.kind]));
      by("learn-review").hidden=false;this.renderLearningReview();
      this.learnMessage("Proposal ready. Review, edit and preview it, then save a new named schedule.");
    });
    by("learn-save").onclick=()=>this.learningAction(async()=>{
      const result=await this.learningAPI("save",{...this.learningDraft(),name:by("learn-name").value});
      this.leaveLearningPreview();this.learningProposal=null;by("learn-review").hidden=true;
      this.learnMessage("Saved “"+result.name+"”. The running schedule is unchanged. Choose it from Schedule when ready.");
    });
    by("learn-grid").onchange=event=>{
      const input=event.target, index=input.dataset.learnCell;
      if(index===undefined || !this.learningProposal) return;
      const entity=this.learningRows()[Number(index)].entity, row=this.learningProposal.profile.rows[entity];
      row.days[this.learningDay]=HS_PUT(row.days[this.learningDay],Number(input.dataset.learnSlot),input.checked);
      if(this.learningFrame) this.learningAction(()=>this.previewLearning());
    };
    by("learn-days").onclick=event=>{
      const day=event.target.dataset.learnDay;
      if(day===undefined) return;
      this.learningDay=Number(day);this.renderLearningReview();
      if(this.learningFrame) this.learningAction(()=>this.previewLearning());
    };
    by("learn-preview").onclick=()=>this.learningAction(()=>this.previewLearning());
    by("learn-return").onclick=()=>this.leaveLearningPreview();
    by("learn-play").onclick=()=>{
      if(this.learningPlaying) {this.pauseLearning();return;}
      this.learningPlaying=true;by("learn-play").textContent="Pause proposal";
      const playJob=this.learningPlayJob=(this.learningPlayJob||0)+1;
      const tick=async()=>{
        if(!this.learningPlaying || this.disposed || playJob!==this.learningPlayJob) return;
        try {await this.previewLearning();}
        catch(error) {this.pauseLearning();this.learnMessage(error.message||String(error),true);return;}
        if(this.learningPlaying && playJob===this.learningPlayJob) {
          this.learningMinute=(this.learningMinute+15)%1440;
          this.learningTimer=setTimeout(tick,250);
        }
      };
      tick();
    };
    by("learn-scrubber").oninput=event=>{
      this.pauseLearning();this.learningMinute=Number(event.target.value);
      by("learn-time").textContent=HS_TIME(this.learningMinute);
      clearTimeout(this.learningScrubTimer);
      this.learningScrubTimer=setTimeout(()=>this.learningAction(()=>this.previewLearning()),120);
    };
  }

  async learningAPI(op, values={}) {
    const result=await this._hass.callWS({type:"call_service",domain:"home_scheduler",service:"learning",
      service_data:{op,...values},return_response:true});
    return result.response;
  }

  async learningAction(action) {
    try {await action();}
    catch(error) {this.learnMessage(error.message||String(error),true);this.updateLearningStatus();}
  }

  learnMessage(message, error=false) {
    const element=this.shadowRoot.getElementById("learn-message");
    if(element) {element.textContent=message;element.classList.toggle("learn-error",error);}
  }

  learningSelection() {
    return Array.from(this.shadowRoot.querySelectorAll("[data-learn-select]:checked"),input=>input.dataset.learnSelect);
  }

  async configureLearning(enabled) {
    await this.learningAPI("configure",{enabled,entities:this.learningSelection(),
      mode_entity:this.shadowRoot.getElementById("learn-mode-entity").value});
    this.learnMessage(enabled?"Observing actual use. Continue using your devices normally.":"Observation paused. Existing learning data is retained.");
  }

  updateLearningStatus() {
    const root=this.shadowRoot, status=this.plan.learning||{}, scope=root.getElementById("learn-scope");
    if(!scope) return;
    if(this.learningProposal && this.learningMapping!==JSON.stringify(this.plan.devices.map(d=>[d.entity,d.target,d.kind]))) {
      this.learningProposal=null;this.leaveLearningPreview();root.getElementById("learn-review").hidden=true;
      this.learnMessage("Device connections changed; generate a new proposal.");
    }
    const devices=this.plan.devices.filter(d=>["light","switch","fan"].includes(d.kind));
    const key=JSON.stringify(devices.map(d=>[d.entity,d.target,d.name]));
    if(key!==this.learningScopeKey) {
      const selected=this.learningScopeKey?this.learningSelection():status.entities||[];
      scope.innerHTML=devices.map(d=>"<label class='check'><input type='checkbox' data-learn-select='"+HS_ESCAPE(d.entity)+"' "+
        (!d.target?"disabled ":selected.includes(d.entity)||(!selected.length&&d.kind==="light")?"checked ":"")+">"+
        HS_ESCAPE(d.name)+(d.target?"":" · connect a real entity")+"</label>").join("");
      this.learningScopeKey=key;
    }
    root.getElementById("learn-enabled").checked=!!status.enabled;
    const mode=root.getElementById("learn-mode-entity");
    if(root.activeElement!==mode) mode.value=status.mode_entity||"";
    const paused=(status.paused_targets||[]).length;
    root.getElementById("learn-status").textContent=(status.enabled?"Observing":"Observation paused")+
      (paused?" · "+paused+" device(s) excluded during physical control":"")+" · up to 8 weeks retained locally\n"+
      (status.history_state==="reading"?"Reading history: "+status.history_progress+"%":status.history_message||"");
    root.getElementById("learn-history").disabled=status.history_state==="reading";
  }

  learningRows() {
    return this.plan.devices.filter(d=>this.learningProposal?.evidence[d.entity]);
  }

  learningDraft() {
    if(!this.learningProposal) throw new Error("Generate a proposal first.");
    return {proposal:this.learningProposal.proposal,days:Object.fromEntries(this.learningRows().map(d=>
      [d.entity,this.learningProposal.profile.rows[d.entity].days]))};
  }

  renderLearningReview() {
    const root=this.shadowRoot, proposal=this.learningProposal, day=this.learningDay;
    if(!proposal) return;
    const rows=this.learningRows();let heading="", quarters="", body="";
    for(let hour=0;hour<12;hour++) heading+="<th colspan='4'>"+String(hour).padStart(2,"0")+" / "+String(hour+12).padStart(2,"0")+" h</th>";
    for(let slot=0;slot<48;slot++) quarters+="<th>"+["00","15","30","45"][slot%4]+"</th>";
    rows.forEach((d,index)=>{
      const evidence=proposal.evidence[d.entity], row=proposal.profile.rows[d.entity];
      for(let band=0;band<2;band++) {
        body+="<tr>";
        if(!band) body+="<th class='label' rowspan='2'>"+HS_ESCAPE(d.name)+"<div class='hint'>"+HS_ESCAPE(d.target)+"</div><span class='lamp' data-learn-lamp='"+index+"'>Preview</span></th>";
        for(let col=0;col<48;col++) {
          const slot=band*48+col, samples=parseInt(evidence.samples[day][slot],16),votes=parseInt(evidence.votes[day][slot],16);
          const known=HS_BIT(evidence.known[day],slot),frequency=samples?votes/samples:0;
          const label=d.name+" · "+HS_DAYS[day]+" "+HS_TIME(slot*15)+" · "+
            (known?"On on "+votes+" of "+samples+" matching weekdays ("+Math.round(100*frequency)+"%).":"Still learning: "+samples+" usable sample(s); needs 3. Existing block retained.");
          body+="<td class='"+(known?"learn-known":"learn-unknown")+"' style='--frequency:"+(frequency*.3).toFixed(2)+"' title='"+HS_ESCAPE(label)+"'>"+
            "<input type='checkbox' data-learn-cell='"+index+"' data-learn-slot='"+slot+"' aria-label='"+HS_ESCAPE(label)+"' title='"+HS_ESCAPE(label)+"' "+(HS_BIT(row.days[day],slot)?"checked":"")+"></td>";
        }
        body+="</tr>";
      }
    });
    root.getElementById("learn-grid").innerHTML="<table><thead><tr><th rowspan='2' class='label'>Proposal · "+HS_DAYS[day]+"</th>"+heading+"</tr><tr>"+quarters+"</tr></thead><tbody>"+body+"</tbody></table>";
    root.getElementById("learn-days").innerHTML=HS_DAYS.map((label,i)=>"<button data-learn-day='"+i+"' class='"+(i===day?"selected":"")+"'>"+label+"</button>").join("");
    const evidence=Object.values(proposal.evidence), usable=evidence.reduce((sum,x)=>sum+x.usable_cells,0);
    root.getElementById("learn-evidence-summary").textContent=usable+" of "+(rows.length*7*96)+" weekly device blocks have consensus · "+
      proposal.threshold+"% threshold · "+proposal.lookback/7+" weeks · based on “"+proposal.base_name+"”"+
      (proposal.include_history?" · includes older activity with uncertain source":" · live observations only")+
      (proposal.mode_state?" · household mode: "+proposal.mode_state:"")+"\n"+
      evidence.reduce((sum,x)=>sum+x.brief_samples,0)+" usable samples contained activity below the 7½-minute vote; "+
      evidence.reduce((sum,x)=>sum+x.excluded_samples,0)+" samples excluded during physical control.";
    root.getElementById("learn-time").textContent=HS_TIME(this.learningMinute);
    root.getElementById("learn-scrubber").value=this.learningMinute;
    this.updateLearningIndicators();
  }

  async previewLearning() {
    if(!this.learningProposal) return;
    const job=this.learningPreviewJob=(this.learningPreviewJob||0)+1;
    const date=new Date(this.learningProposal.date+"T12:00:00Z");
    date.setUTCDate(date.getUTCDate()+this.learningDay-HS_DAY(this.learningProposal.date));
    const frame=await this.learningAPI("preview",{...this.learningDraft(),date:date.toISOString().slice(0,10),minute:this.learningMinute});
    if(job!==this.learningPreviewJob || this.disposed) return;
    this.learningFrame=frame;
    this.shadowRoot.getElementById("learn-scrubber").value=frame.minute;
    this.shadowRoot.getElementById("learn-time").textContent=HS_TIME(frame.minute);
    const banner=this.shadowRoot.getElementById("learn-preview-banner");
    banner.hidden=false;banner.textContent="Learned proposal · virtual preview · "+HS_DAYS[this.learningDay]+" "+HS_TIME(frame.minute)+" · running schedule unchanged";
    this.updateModel();
    this.updateLearningIndicators();
  }

  updateLearningIndicators() {
    this.learningRows().forEach((device,index)=>{
      const badge=this.shadowRoot.querySelector("[data-learn-lamp='"+index+"']");
      if(!badge) return;
      const state=this.learningFrame?.states?.[device.entity]?.state;
      badge.textContent=state==="on"?"On":state==="off"?"Off":"Preview";
      badge.classList.toggle("on",state==="on");
    });
  }

  pauseLearning() {
    this.learningPlayJob=(this.learningPlayJob||0)+1;
    this.learningPlaying=false;clearTimeout(this.learningTimer);
    const button=this.shadowRoot.getElementById("learn-play");
    if(button) button.textContent="Play proposal";
  }

  leaveLearningPreview() {
    this.pauseLearning();clearTimeout(this.learningScrubTimer);
    this.learningPreviewJob=(this.learningPreviewJob||0)+1;this.learningFrame=null;
    const banner=this.shadowRoot.getElementById("learn-preview-banner");
    if(banner) banner.hidden=true;
    if(this.plan) this.updateLearningIndicators();
    if(this.renderer && this._hass) this.updateModel();
  }

  visibleIndices() {
    const types=new Set(this.plan.shown_types||["light"]), hidden=new Set(this.plan.hidden_devices||[]);
    return this.plan.devices.map((d,i)=>types.has(d.kind)&&!hidden.has(d.entity)?i:-1).filter(i=>i>=0);
  }

  fillDay(value, index) {
    this.finishPaint(false);
    const root=this.shadowRoot, rows=(index===undefined?this.visibleIndices():[index]).filter(i=>!value||this.plan.devices[i].kind!=="scene");
    if(!rows.length) return;
    for(const row of rows) {
      root.querySelectorAll("[data-row='"+row+"']").forEach(input=>input.checked=value);
      if(value) root.querySelector("[data-use='"+row+"']").checked=true;
    }
    this.send("fill",{profile:this.plan.profile,day:HS_DAY(this.plan.date),value,entities:rows.map(i=>this.plan.devices[i].entity)});
  }

  startPaint(event) {
    if(this.paint || !event.isPrimary || event.button !== 0) return;
    this.suppressPaintClick=false;
    const grid=this.shadowRoot.getElementById("grid");
    if(event.pointerType==="touch" && !grid.classList.contains("touch-paint")) return;
    const cell=event.target.closest("[data-paint-slot]");
    if(!cell) return;
    event.preventDefault();
    const index=Number(cell.dataset.paintRow), start=Number(cell.dataset.paintSlot);
    const inputs=Array.from(this.shadowRoot.querySelectorAll("[data-row='"+index+"']"));
    const input=inputs[start];
    input.focus({preventScroll:true});
    this.paint={index,start,end:start,value:!input.checked,inputs,original:inputs.map(x=>x.checked),
      profile:this.plan.profile,date:this.plan.date,day:HS_DAY(this.plan.date),
      entity:this.plan.devices[index].entity,pointerId:event.pointerId,x:event.clientX,y:event.clientY};
    this.suppressPaintClick=true;
    grid.setPointerCapture(event.pointerId);
    this.drawPaint();
    this.paintScrollFrame=requestAnimationFrame(()=>this.scrollPaint());
  }

  paintAt(x,y) {
    const cell=this.shadowRoot.elementFromPoint(x,y)?.closest("[data-paint-slot]");
    if(!this.paint || !cell || Number(cell.dataset.paintRow) !== this.paint.index) return;
    const end=Number(cell.dataset.paintSlot);
    if(this.paint.end !== end) { this.paint.end=end; this.drawPaint(); }
  }

  drawPaint() {
    const p=this.paint, lo=Math.min(p.start,p.end), hi=Math.max(p.start,p.end);
    p.inputs.forEach((input,slot)=>{
      const inside=lo <= slot && slot <= hi;
      input.checked=inside?p.value:p.original[slot];
      input.parentElement.classList.toggle("painting",inside);
    });
  }

  scrollPaint() {
    const p=this.paint;
    if(!p) return;
    const grid=this.shadowRoot.getElementById("grid"), bounds=grid.getBoundingClientRect();
    const label=grid.querySelector(".label").getBoundingClientRect().width;
    if(p.y > bounds.top && p.y < bounds.bottom) {
      const delta=p.x > bounds.right-28?14:p.x < bounds.left+label+28?-14:0;
      if(delta) { grid.scrollLeft+=delta; this.paintAt(p.x,p.y); }
    }
    this.paintScrollFrame=requestAnimationFrame(()=>this.scrollPaint());
  }

  finishPaint(commit) {
    const p=this.paint;
    if(!p) return;
    this.paint=null;
    cancelAnimationFrame(this.paintScrollFrame);
    p.inputs.forEach((input,slot)=>{
      if(!commit) input.checked=p.original[slot];
      input.parentElement.classList.remove("painting");
    });
    const grid=this.shadowRoot.getElementById("grid");
    if(grid.hasPointerCapture(p.pointerId)) grid.releasePointerCapture(p.pointerId);
    if(commit) {
      if(p.value) this.shadowRoot.querySelector("[data-use='"+p.index+"']").checked=true;
      this.send("range",{profile:p.profile,entity:p.entity,day:p.day,start:p.start,end:p.end,value:p.value});
    }
  }

  deviceRows() {
    const E=HS_ESCAPE;
    return this.plan.devices.map((d,index)=>{
      let options="";
      const numeric=(key,label,min,max)=>"<label>"+label+"<input type='number' data-setting-row='"+index+"' data-setting='"+key+"' min='"+min+"' max='"+max+"'></label>";
      if(d.kind==="light") options=numeric("brightness","Brightness %",1,100)+"<label>Color<input type='color' data-setting-row='"+index+"' data-setting='color'></label>";
      if(d.kind==="fan") options=numeric("percentage","Inside speed %",1,100);
      if(d.kind==="cover") options=numeric("position","Inside position %",0,100)+"<label>Outside position %<input type='number' min='0' max='100' data-off-position='"+index+"'></label><label>Full travel seconds<input type='number' min='1' max='600' data-travel='"+index+"'></label>";
      if(d.kind!=="scene") options+="<label>Outside periods<select data-outside='"+index+"'><option value='off'>"+(d.kind==="cover"?"Outside position":"Off")+"</option><option value='unchanged'>Leave unchanged</option><option value='restore'>Restore previous state</option></select></label>";
      else options="<label>Preview effects (JSON)<textarea data-effects='"+index+"' rows='5' spellcheck='false'></textarea></label><button data-save-effects='"+index+"'>Save preview effects</button><div class='hint'>Preview effects stay virtual. Real scenes activate only in Physical devices + Follow clock mode.</div>";
      options+="<label>Real entity (optional)<input data-target='"+index+"' list='hs-real-entities' placeholder='Unlinked demo'></label><div class='preview-id'>Preview ID: "+E(d.entity)+"</div>";
      let html="";
      for(let band=0;band<2;band++) {
        html+="<tr data-device-row='"+index+"'>";
        if(!band) html+="<th class='label' rowspan='2'><div data-device-name='"+index+"'>"+E(d.name)+"</div><div class='kind-name'>"+E(d.kind==="scene"?"Scene activation markers":d.kind==="cover"?"Cover · "+(d.device_class||"generic"):d.kind)+"</div><div class='row-options'><label><input type='checkbox' data-use='"+index+"'>Enabled</label><label><input type='checkbox' data-random='"+index+"'>Random</label><span data-lamp='"+index+"' class='lamp'></span></div><div class='row-buttons'><button data-fill-row='"+index+"' data-value='true' "+(d.kind==="scene"?"disabled ":"")+">Select all</button><button data-fill-row='"+index+"' data-value='false'>Clear all</button></div><details class='row-settings'><summary>Settings &amp; connection</summary><div>"+options+"</div></details></th>";
        for(let col=0;col<48;col++) {
          const slot=band*48+col, label=d.name+" "+(d.kind==="scene"?"activate at ":"")+HS_TIME(slot*15)+(d.kind==="scene"?"":" to "+HS_TIME((slot*15+15)%1440));
          html+="<td data-paint-row='"+index+"' data-paint-slot='"+slot+"' class='"+(d.kind==="scene"?"event-cell":"")+"'><input type='checkbox' data-row='"+index+"' data-slot='"+slot+"' aria-label='"+E(label)+"' title='"+E(label)+"'></td>";
        }
        if(!band) html+="<td rowspan='2' class='watts'>"+(d.kind==="scene"?"—":"<input type='number' min='0' max='20000' step='0.1' data-watts='"+index+"' aria-label='"+E(d.name+" "+(d.kind==="cover"?"motor watts":"watts while on"))+"'>")+"</td><td rowspan='2' data-energy='"+index+"' class='energy'></td>";
        html+="</tr>";
      }
      return html;
    }).join("");
  }

  buildDeviceManager() {
    const root=this.shadowRoot, E=HS_ESCAPE;
    const kinds={light:"Lights",switch:"Switches / plugs",fan:"Fans",cover:"Covers",scene:"Scenes"};
    root.getElementById("type-filters").innerHTML=Object.entries(kinds).map(([key,name])=>"<label class='check'><input type='checkbox' data-kind='"+key+"'>"+name+"</label>").join("");
    root.getElementById("device-list").innerHTML=this.plan.devices.map((d,i)=>"<div class='manage-device'><label class='check'><input type='checkbox' data-visible='"+E(d.entity)+"'>Include row</label><input data-rename='"+i+"' aria-label='Device name' value='"+E(d.name)+"'><span>"+E(d.kind)+"</span><button data-remove-device='"+E(d.entity)+"'>Remove</button></div>").join("");
    this.catalogKey=JSON.stringify(this.plan.devices.map(d=>[d.entity,d.kind,d.name]));
  }

  updateVisibility() {
    const root=this.shadowRoot, visible=new Set(this.visibleIndices()), types=new Set(this.plan.shown_types||["light"]),hidden=new Set(this.plan.hidden_devices||[]);
    root.querySelectorAll("[data-kind]").forEach(x=>x.checked=types.has(x.dataset.kind));
    root.querySelectorAll("[data-visible]").forEach(x=>x.checked=!hidden.has(x.dataset.visible));
    root.querySelectorAll("[data-device-row]").forEach(x=>x.hidden=!visible.has(Number(x.dataset.deviceRow)));
    root.getElementById("visibility-hint").textContent=visible.size+" of "+this.plan.devices.length+" rows shown. Filters and Include row affect display only; enabled schedules still run. Select all changes visible non-scene rows only.";
    root.getElementById("select-all").disabled=!this.visibleIndices().some(i=>this.plan.devices[i].kind!=="scene");
    root.getElementById("clear-all").disabled=!visible.size;
  }

  styles() {
    return ":host{display:block}[hidden]{display:none!important}.type-filters{display:flex;flex-wrap:wrap;gap:14px;padding:12px 0}.kind-name,.preview-id{font-size:11px;color:var(--secondary-text-color);margin-top:4px}.preview-id{overflow-wrap:anywhere}.row-settings{margin-top:7px;font-size:11px}.row-settings>div{display:flex;flex-wrap:wrap;gap:6px;padding-top:7px}.row-settings label{font-size:11px;max-width:100%}.row-settings input:not([type=checkbox]),.row-settings select{width:180px;max-width:100%}.row-settings input[type=color]{width:60px;height:30px}.row-settings textarea{width:195px;max-width:100%;box-sizing:border-box;font:11px monospace;background:var(--card-background-color);color:var(--primary-text-color)}.row-options{flex-wrap:wrap}.lamp{font-size:11px}.manage-device{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}.manage-device>input{flex:1;min-width:140px}.manage-device>span{font-size:12px;color:var(--secondary-text-color)}.add-device{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;align-items:flex-end}.event-cell input{accent-color:#9c6ade}.event-cell.current{background:rgba(156,106,222,.15)}ha-card{padding:12px;overflow:hidden;box-sizing:border-box;border-radius:18px}"+
      ".title{font-size:20px;font-weight:500;padding:2px 4px 8px;display:flex;align-items:center;gap:10px}.brand-icon{width:36px;height:36px}"+
      "#summary{background:rgba(var(--rgb-primary-color,3,169,244),.08);border:1px solid rgba(var(--rgb-primary-color,3,169,244),.13);border-radius:14px;padding:10px 12px;margin-bottom:8px}"+
      "#primary{font-size:15px}#secondary{font-size:13px;margin-top:3px;color:var(--secondary-text-color)}"+
      "#model-workspace{--ls-model-height:clamp(360px,44vh,650px);display:grid;grid-template-columns:minmax(320px,400px) minmax(0,1fr);gap:12px}"+
      "#model-workspace.editor-closed{grid-template-columns:minmax(0,1fr)}.editor-closed #editor-pane{display:none}"+
      ".model-toolbar{display:flex;flex-wrap:wrap;align-items:flex-end;gap:8px;margin:0 0 6px}.model-toolbar button{font-size:12px}.model-choice{flex:1;min-width:180px}.model-choice select{width:100%}#model-status.error{color:var(--error-color)}"+
      "#editor-pane{height:var(--ls-model-height);min-width:0;box-sizing:border-box;border:1px solid var(--divider-color);border-radius:12px;display:flex;flex-direction:column;overflow:hidden}"+
      ".editor-heading{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px;border-bottom:1px solid var(--divider-color);font-size:13px}.editor-actions{display:flex;gap:5px;margin-left:auto}.editor-actions button{font-size:12px}"+
      "#editor-body{flex:1;min-height:0;min-width:0;overflow:auto;padding:8px}#editor-body>*{display:block;min-width:0}#editor-status{font-size:12px;padding:8px;border-top:1px solid var(--divider-color);color:var(--secondary-text-color)}#editor-status.error{color:var(--error-color)}"+
      "#model{height:var(--ls-model-height);min-width:0;width:100%;overflow:hidden;border-radius:12px;position:relative}"+
      "#model-message{padding:16px;color:var(--secondary-text-color)}"+
      ".controls,.edit-controls,.advanced,.bulk-controls{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding:10px 0}"+
      ".bulk-controls{padding:4px 0}.bulk-controls strong{font-size:13px}.bulk-controls .check{margin-left:auto}"+
      ".time{flex:1;min-width:220px;display:flex;flex-direction:column;gap:4px}#time{font-weight:600}"+
      "label{display:flex;flex-direction:column;gap:4px;font-size:13px}.check{flex-direction:row;align-items:center;white-space:nowrap}"+
      "input,select,button{font:inherit;color:var(--primary-text-color);accent-color:var(--primary-color)}"+
      "input:not([type=checkbox]):not([type=range]),select,button{border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);padding:6px;box-sizing:border-box}"+
      "input[type=checkbox]{width:15px;height:15px;margin:0;cursor:pointer}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}"+
      "#days{display:flex;gap:3px}#days button{padding:5px 7px}#days .selected{background:var(--primary-color);color:var(--text-primary-color,#fff)}"+
      ".hint{font-size:12px;color:var(--secondary-text-color);margin:5px 0 8px}details{font-size:13px}summary{cursor:pointer}"+
      ".advanced input{max-width:230px}.advanced #name{width:150px}"+
      "#grid{overflow:auto;max-height:46vh;border:1px solid var(--divider-color);border-radius:10px}"+
      "#grid.touch-paint{touch-action:none}td[data-paint-slot]{cursor:crosshair;user-select:none}td.painting{background:rgba(var(--rgb-primary-color,3,169,244),.3);box-shadow:inset 0 0 0 1px var(--primary-color)}"+
      "table{border-collapse:separate;border-spacing:0;min-width:1240px;width:100%;font-size:12px;table-layout:fixed}"+
      "thead th{position:sticky;top:0;background:var(--card-background-color);z-index:3;font-weight:500;height:23px}"+
      "thead tr:nth-child(2) th{top:25px;font-size:10px}th,td{border-right:1px solid var(--divider-color);border-bottom:1px solid var(--divider-color);text-align:center;padding:1px}"+
      ".label{width:230px;text-align:left;position:sticky;left:0;z-index:2;background:var(--card-background-color);padding:7px 8px;font-weight:500}"+
      "thead .label{z-index:5}.row-options{display:flex;gap:9px;align-items:center;margin-top:6px;color:var(--secondary-text-color)}.row-options label{flex-direction:row;align-items:center;font-size:11px}"+
      ".row-buttons{display:flex;gap:6px;margin-top:6px}.row-buttons button{font-size:11px;padding:4px 6px}"+
      ".lamp{margin-left:auto}.lamp.on{color:var(--primary-color);font-weight:600}.watts{width:65px}.watts input{width:60px;padding:4px!important}"+
      ".energy{width:80px}thead tr:first-child th:last-child{width:80px}thead tr:first-child th:nth-last-child(2){width:65px}"+
      "tbody td{height:21px}td.current{background:rgba(var(--rgb-primary-color,3,169,244),.2)}"+
      ".total{padding-top:9px;font-size:13px;color:var(--secondary-text-color)}#error{font-size:13px;color:var(--error-color);white-space:pre-line;margin-top:6px}"+
      "@media(max-width:850px){#model-workspace{grid-template-columns:minmax(0,1fr)}#editor-pane{height:clamp(240px,34vh,360px)}}"+
      "@media(max-width:700px){ha-card{padding:8px}.controls{gap:8px}.time{min-width:160px}#model{height:30vh;min-height:210px}#days{flex-wrap:wrap}.label{width:200px}.advanced{align-items:stretch}}";
  }

  updatePlan() {
    const p=this.plan, root=this.shadowRoot, profile=p.profiles.find(x=>x.id===p.profile), day=HS_DAY(p.date);
    if(!profile) return;
    if(this.catalogKey!==JSON.stringify(p.devices.map(d=>[d.entity,d.kind,d.name]))) {
      this.finishPaint(false);
      root.querySelector("#grid tbody").innerHTML=this.deviceRows();
      this.buildDeviceManager();
      this.lastSlot=null;
    }
    this.updateVisibility();
    const entityOptions=Object.entries(this._hass.states).filter(([id])=>/^(light|switch|fan|cover|scene)\./.test(id)).map(([id,state])=>"<option value='"+HS_ESCAPE(id)+"'>"+HS_ESCAPE(state.attributes?.friendly_name||id)+"</option>").join("");
    root.getElementById("hs-real-entities").innerHTML=entityOptions;
    if(this.paint && (this.paint.profile !== p.profile || this.paint.date !== p.date)) this.finishPaint(false);
    const options=p.profiles.map(x=>"<option value='"+HS_ESCAPE(x.id)+"'>"+HS_ESCAPE(x.name)+"</option>").join("");
    const select=root.getElementById("profile");
    if(select.innerHTML !== options) select.innerHTML=options;
    select.value=p.profile;
    for(const key of ["physical","clock","auto","repeat"]) root.getElementById(key).checked=p[key];
    for(const key of ["speed","date","jitter"]) {
      const input=root.getElementById(key); if(root.activeElement !== input) input.value=p[key];
    }
    for(const key of ["name","condition_entity","condition_state","scene"]) {
      const input=root.getElementById(key); if(root.activeElement !== input) input.value=profile[key];
    }
    root.getElementById("weekday").textContent=HS_DAYS[day];
    root.getElementById("bulk-day").textContent=HS_DAYS[day];
    root.querySelectorAll("[data-day]").forEach(button=>button.classList.toggle("selected",Number(button.dataset.day)===day));
    p.devices.forEach((light,index)=>{
      const row=profile.rows[light.entity];
      root.querySelector("[data-use='"+index+"']").checked=row.use;
      root.querySelector("[data-random='"+index+"']").checked=p.random[light.entity];
      const watts=root.querySelector("[data-watts='"+index+"']");
      if(watts && root.activeElement !== watts) watts.value=p.watts[light.entity];
      const energy=p.energy[light.entity];
      root.querySelector("[data-energy='"+index+"']").textContent=light.kind==="scene"?(energy?.events||0)+" events":(energy?.kwh||0).toFixed(4);
      for(const input of root.querySelectorAll("[data-setting-row='"+index+"']"))
        if(root.activeElement!==input) input.value=row.on[input.dataset.setting];
      for(const [attr,value] of [["outside",row.outside],["off-position",row.off_position],["travel",light.travel_seconds],["target",light.target]]) {
        const input=root.querySelector("[data-"+attr+"='"+index+"']");
        if(input && root.activeElement!==input) input.value=value;
      }
      const effects=root.querySelector("[data-effects='"+index+"']");
      if(effects && root.activeElement!==effects) effects.value=JSON.stringify(light.effects||{},null,2);
      if(this.paint?.index !== index)
        root.querySelectorAll("[data-row='"+index+"']").forEach(input=>input.checked=HS_BIT(row.days[day],Number(input.dataset.slot)));
    });
    const total=Object.values(p.energy).reduce((sum,x)=>sum+(x.kwh||0),0);
    root.getElementById("total").textContent=profile.name+" · "+HS_DAYS[day]+" · "+total.toFixed(3)+" kWh/day estimated"+
      (p.jitter && Object.values(p.random).some(Boolean) ? " · randomized rows include boundary variation" : "");
    root.getElementById("scrubber").disabled=!!p.clock;
    this.updateLearningStatus();
    this.updateFrame();
  }

  updateFrame() {
    const f=this.frame, root=this.shadowRoot;
    if(!f) return;
    const editing=this.plan.profiles.find(x=>x.id===this.plan.profile);
    root.getElementById("primary").textContent=(f.physical?"Physical devices":"Simulation")+" · "+
      (f.clock?"Daily schedule":f.playing?"Playing":"Paused");
    root.getElementById("secondary").textContent=f.profile_name+" · "+HS_TIME(f.minute)+" · "+
      f.on.length+" scheduled active · "+f.watts+" W estimated"+(editing && editing.id!==f.profile?" · Editing "+editing.name:"");
    root.getElementById("play").textContent=f.playing?"Pause":"Play";
    root.getElementById("play").disabled=!!f.clock;
    if(this.localMinute===null) {
      root.getElementById("time").textContent=HS_TIME(f.minute);
      root.getElementById("scrubber").value=f.minute;
    }
    this.plan.devices.forEach((device,index)=>{
      const badge=root.querySelector("[data-lamp='"+index+"']");
      const value=f.physical && device.target?this._hass.states[device.target]:f.states?.[device.entity];
      const state=value?.state;
      if(device.kind==="scene") {
        const past=(f.events||[]).filter(x=>x.entity===device.entity&&x.minute<=f.minute);
        badge.textContent=past.length?"At "+HS_TIME(past.at(-1).minute):"Ready";
      } else if(device.kind==="cover") badge.textContent=value?.attributes?.current_position!==undefined?value.attributes.current_position+"%":state||"Unavailable";
      else badge.textContent=state==="on"?(device.kind==="fan"&&value.attributes?.percentage?"On "+value.attributes.percentage+"%":"On"):state==="off"?"Off":"Unavailable";
      badge.classList.toggle("on",state==="on"||state==="open");
    });
    const slot=f.date===this.plan.date && f.profile===this.plan.profile?Math.floor(f.minute/15):-1;
    if(slot !== this.lastSlot) {
      root.querySelectorAll("td.current").forEach(td=>td.classList.remove("current"));
      if(slot>=0) root.querySelectorAll("[data-slot='"+slot+"']").forEach(input=>input.parentElement.classList.add("current"));
      this.lastSlot=slot;
    }
    root.getElementById("error").textContent=(f.errors||[]).join("\n");
  }

  async loadRenderer() {
    const job=++this.sourceJob;
    try {
      let source=this.plan.renderer||this.config.renderer;
      if(!source) {
        const response=await fetch(this.config.renderer_url||"/home_scheduler/demo-home.json?v=0.4.0");
        if(!response.ok) throw new Error("House configuration unavailable ("+response.status+"). Check the installed JSON file.");
        source=await response.json();
      }
      if(this.disposed || job !== this.sourceJob) return;
      source=this.plan.renderer||source;
      this.validateRenderer(source);
      this.savedRenderer=JSON.parse(JSON.stringify(source));
      this.rendererDraft=JSON.parse(JSON.stringify(source));
      this.baseRendererRevision=this.seenRendererRevision=this.plan.renderer_revision||0;
      this.helpers=await window.loadCardHelpers();
      if(this.disposed || job !== this.sourceJob) return;
      await this.renderRenderer(source);
      if(this.editorVisible) await this.loadEditor();
    } catch(error) {
      if(this.disposed || job !== this.sourceJob) return;
      this.renderer=null;
      this.shadowRoot.getElementById("model").textContent=error.message||String(error);
    }
  }

  modelStatus(message,error=false) {
    const status=this.shadowRoot.getElementById("model-status");
    if(status) {status.textContent=message;status.classList.toggle("error",error);}
  }

  updateModelSelector() {
    const root=this.shadowRoot,select=root.getElementById("model-select");
    if(!select) return;
    const current=this.plan.renderer||this.savedRenderer||this.config.renderer;
    const options=[{id:"current",name:"Current model"+(current?.name?" · "+current.name:"")},...this.modelChoices];
    const markup=options.map(x=>"<option value='"+HS_ESCAPE(x.id)+"'>"+HS_ESCAPE(x.name)+"</option>").join("");
    const chosen=select.value;
    if(select.innerHTML!==markup) {
      select.innerHTML=markup;
      select.value=options.some(x=>x.id===chosen)?chosen:"current";
    }
    if(!this.modelImporting && !this.modelSelected) {
      select.value=current?.objfile==="demo-home.glb"&&["/home_scheduler/","/local/home-scheduler/"].includes(current?.path)?"demo":"current";
    }
    for(const id of ["model-select","refresh-models","import-model-file"])
      root.getElementById(id).disabled=!!this.modelImporting||!!this.modelsLoading;
  }

  async discoverModels() {
    if(this.modelsLoading) return;
    this.modelsLoading=true;this.updateModelSelector();
    const choices=[this.modelChoices[0]],seen=new Set();
    const add=(choice)=>{if(!seen.has(choice.id)) {seen.add(choice.id);choices.push(choice);}};
    const legacy=this._hass.states["sensor.lighting_scheduler"]?.attributes;
    if(legacy) add({id:"legacy",name:"My house · existing Lighting Scheduler",kind:"legacy"});
    if(this.config.renderer) add({id:"card",name:this.config.renderer.name||"Configured model",source:this.config.renderer});
    const bounded=promise=>new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error("Model discovery timed out")),6000);
      promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});
    });
    const query=message=>this._hass.callWS?this._hass.callWS(message):this._hass.connection?.sendMessagePromise(message);
    const reads=await Promise.allSettled([
      bounded(Promise.all(["/home_scheduler/models.json?v=0.4.0",this.plan.model_presets_url].filter(Boolean).map(url=>
        fetch(url,{cache:"no-store"}).then(async response=>response.ok?response.json():null))).then(indices=>({models:indices.flatMap(x=>Array.isArray(x?.models)?x.models:[])}))),
      bounded(Promise.resolve().then(()=>query({type:"lovelace/dashboards/list"})))
    ]);
    if(this.disposed) {this.modelsLoading=false;this.modelsStarted=false;return;}
    if(reads[0].status==="fulfilled") for(const [index,item] of (reads[0].value?.models||[]).entries()) {
      if(item&&typeof item.url==="string"&&["/local/","/home_scheduler/"].some(prefix=>item.url.startsWith(prefix)))
        add({id:"preset-"+index,name:String(item.name||"Saved model"),url:item.url,kind:"preset"});
    }
    const paths=new Map([[null,"Overview"]]);
    const current=location.pathname.split("/")[1];
    if(current&&current!=="lovelace") paths.set(current,"Current dashboard");
    if(reads[1].status==="fulfilled"&&Array.isArray(reads[1].value))
      for(const dashboard of reads[1].value.slice(0,32)) if(dashboard.url_path) paths.set(dashboard.url_path,dashboard.title||dashboard.url_path);
    const dashboards=await Promise.allSettled(Array.from(paths,async([url_path,title])=>{
      const config=await bounded(Promise.resolve().then(()=>query({type:"lovelace/config",url_path,force:false})));
      return {config,title,url_path};
    }));
    for(const result of dashboards) if(result.status==="fulfilled") {
      const {config,title,url_path}=result.value;
      let count=0;
      const visit=(value)=>{
        if(!value||typeof value!=="object") return;
        if(["custom:floor3dx-card","custom:floor3d-card"].includes(value.type)) {
          add({id:"dashboard-"+(url_path||"overview")+"-"+(count++),name:(value.name||value.objfile||"House")+" · "+title,source:value,kind:"dashboard"});return;
        }
        for(const child of Object.values(value)) visit(child);
      };
      visit(config);
    }
    if(!this.disposed) {
      this.modelChoices=choices;this.modelsLoading=false;this.updateModelSelector();
    } else {this.modelsLoading=false;this.modelsStarted=false;}
  }

  async selectModel(choice) {
    if(this.modelImporting||this.modelSaving) return;
    // Preserve a valid current draft before switching houses.
    if(this.rendererDirty) {
      if(this.rendererInvalid) {this.modelStatus("Fix the model draft or discard it before selecting another model.",true);return;}
      await this.saveRenderer();
      if(this.rendererDirty) {this.modelStatus("The current draft could not be saved. Your model was kept.",true);return;}
    }
    this.modelImporting=true;this.finishPaint(false);clearTimeout(this.rendererTimer);this.sourceJob++;
    this.shadowRoot.getElementById("grid").inert=true;
    this.updateModelSelector();this.updateEditorControls();this.modelStatus("Loading "+choice.name+" and populating devices…");
    try {
      let source=choice.source;
      if(choice.url) {
        const response=await fetch(choice.url,{cache:"no-store"});
        if(!response.ok) throw new Error("Model configuration unavailable ("+response.status+").");
        source=await response.json();
      }
      const legacy=this._hass.states["sensor.lighting_scheduler"]?.attributes;
      let sourcePlan;
      if(choice.kind==="legacy"||source?.legacy_domain==="lighting_scheduler") {
        if(choice.kind==="legacy") {
          const preset=this.modelChoices.find(x=>x.kind==="preset");
          if(preset) {const response=await fetch(preset.url,{cache:"no-store"});if(response.ok) source=await response.json();}
        }
        let renderer=legacy?.renderer||source?.renderer;
        if(!renderer) {
          const response=await fetch("/local/lighting-scheduler-house.json",{cache:"no-store"});
          if(!response.ok) throw new Error("Existing house configuration unavailable. Import its floor3dx JSON/YAML instead.");
          renderer=await response.json();
        }
        source={...(source&&typeof source==="object"?source:{}),renderer,
          devices:(legacy?.lights||source?.devices||[]).map(d=>({...d,kind:"light"}))};
        if(legacy?.profiles) sourcePlan=Object.fromEntries(["profiles","watts","random","profile","date","jitter","seed"].filter(k=>legacy[k]!==undefined).map(k=>[k,legacy[k]]));
      }
      const revision=this.plan.renderer_revision||0;
      await this._hass.callService("home_scheduler","command",{op:"import_model",source,expected_revision:revision,
        ...(choice.kind==="demo"?{demo:true}:{}),...(sourcePlan?{source_plan:sourcePlan}:{})});
      this.modelSelected=choice.id;
      this.rendererDirty=false;this.rendererInvalid=null;
      if(!this.helpers||!this.savedRenderer) await this.loadRenderer();
      this.syncSavedRenderer();this.update();
      const report=this.plan.last_import;
      this.modelStatus((this.plan.renderer_revision>revision&&report)?
        report.name+" · "+report.devices+" device rows populated"+(report.readonly?" · "+report.readonly+" read-only bindings retained":"")+
        (report.schedule_rows_copied?" · existing schedules copied":"")+" · Physical control reset on import":"Model selected · device rows will appear automatically · Physical control reset on import");
    } catch(error) {
      this.modelSelected=null;this.modelStatus(error.message||String(error),true);
    } finally {
      this.modelImporting=false;this.shadowRoot.getElementById("grid").inert=false;
      this.updateModelSelector();this.updateEditorControls();
    }
  }

  validateRenderer(config) {
    if(!["custom:floor3dx-card","custom:floor3d-card"].includes(config?.type))
      throw new Error("Expected a floor3dx renderer configuration.");
    if(["path","objfile"].some(key=>typeof config[key]!=="string" || !config[key].trim()))
      throw new Error("Model path and file are required.");
  }

  async renderRenderer(source) {
    this.validateRenderer(source);
    const job=++this.renderJob, config=JSON.parse(JSON.stringify(source));
    config.style="height:100%;width:100%;";
    config.card_mod={style:"ha-card{height:100%!important;width:100%!important;margin:0!important;padding:0!important;border:0!important;border-radius:0!important;overflow:hidden}"};
    config.click="no";
    config.selectionMode="no";
    config.editModeNotifications="no";
    const renderer=await this.helpers.createCardElement(config);
    if(this.disposed || !this.showModel || job !== this.renderJob) return;
    renderer.preview=this.editorVisible;
    renderer.style.cssText="display:block;width:100%;height:100%";
    this.timeEntity=config.daylight?.time_entity||"input_number.hs_demo_hour";
    this.renderer=renderer;
    this.shadowRoot.getElementById("model").replaceChildren(renderer);
    this.updateModel();
  }

  editorHass() {
    // HA selectors may read registries through WebSocket. Device actions are
    // blocked; the editor changes model configuration through config-changed.
    const hass=this._hass, blocked=async()=>{throw new Error("Use the scheduler controls to operate devices.");};
    const query=(method,args)=>args[0]?.type==="call_service"?blocked():method(...args);
    const readonly={...hass,states:this.modelStates(),callService:blocked};
    if(hass.callWS) readonly.callWS=(...args)=>query(hass.callWS.bind(hass),args);
    if(hass.connection) readonly.connection=new Proxy(hass.connection,{
      get:(connection,key)=>["sendMessage","sendMessagePromise"].includes(key)?
        (...args)=>query(connection[key].bind(connection),args):
        (typeof connection[key]==="function"?connection[key].bind(connection):connection[key]),
    });
    return readonly;
  }

  async loadEditor() {
    if(this.editor || this.editorLoading || !this.renderer || !this.showModel) return;
    this.editorLoading=true;
    try {
      const cardClass=customElements.get(this.rendererDraft.type.slice(7))||this.renderer.constructor;
      const factory=cardClass.getConfigElement;
      if(typeof factory !== "function") throw new Error("Update floor3dx-card to 1.4.0 or later and reload to use the visual editor.");
      const editor=await factory.call(cardClass);
      if(this.disposed || !this.showModel) return;
      editor.hass=this.editorHass();
      editor.setConfig(JSON.parse(JSON.stringify(this.rendererDraft)));
      editor.addEventListener("config-changed",event=>{
        // Keep the inner floor3dx config out of the outer HA dashboard editor.
        event.stopPropagation();
        this.stageRenderer(event.detail?.config);
      });
      this.editor=editor;
      if(this.editorVisible) {
        this.claimEditor();
        this.shadowRoot.getElementById("editor-body").replaceChildren(editor);
      }
    } catch(error) {
      this.shadowRoot.getElementById("editor-body").textContent=error.message||String(error);
    } finally { this.editorLoading=false; this.updateEditorControls(); }
  }

  toggleEditor() {
    this.editorVisible=!this.editorVisible;
    if(this.editorVisible) {
      this.claimEditor();
      if(this.renderer) this.renderer.preview=true;
      if(this.editor) this.shadowRoot.getElementById("editor-body").replaceChildren(this.editor);
      else this.loadEditor();
    } else {
      // Disconnect first so floor3dx clears its picker and outlines while the
      // model still accepts preview controls; then leave normal camera navigation.
      this.editor?.remove();
      if(this.renderer) this.renderer.preview=false;
      if(HomeSchedulerCard.editorOwner === this) HomeSchedulerCard.editorOwner=null;
    }
    this.updateEditorControls();
  }

  claimEditor() {
    // floor3dx 1.4 uses window events. Only one embedded editor participates at
    // a time, so picking in one scheduler cannot fill a field in another.
    const other=HomeSchedulerCard.editorOwner;
    if(other && other !== this && other.editorVisible) other.toggleEditor();
    HomeSchedulerCard.editorOwner=this;
  }

  updateEditorControls(message, error=false) {
    const root=this.shadowRoot, toggle=root.getElementById("toggle-editor");
    if(!toggle) return;
    root.getElementById("model-workspace").classList.toggle("editor-closed",!this.editorVisible);
    toggle.textContent=this.editorVisible?"Hide model editor":"Show model editor";
    toggle.setAttribute("aria-expanded",String(this.editorVisible));
    root.getElementById("save-model").disabled=!this.rendererDirty || !!this.rendererInvalid || !!this.modelSaving || !!this.modelImporting;
    root.getElementById("discard-model").disabled=!this.rendererDirty || !!this.modelSaving || !!this.modelImporting;
    root.getElementById("editor-body").inert=!!this.modelSaving||!!this.modelImporting;
    if(message !== undefined) {
      root.getElementById("editor-status").textContent=message;
      root.getElementById("editor-status").classList.toggle("error",error);
    }
  }

  stageRenderer(source) {
    if(this.modelSaving || this.modelImporting || !source || typeof source !== "object") return;
    this.rendererDraft=JSON.parse(JSON.stringify(source));
    this.rendererDirty=JSON.stringify(this.rendererDraft)!==JSON.stringify(this.savedRenderer);
    clearTimeout(this.rendererTimer);
    try {
      this.validateRenderer(this.rendererDraft);
      this.rendererInvalid=null;
      this.editor?.setConfig(JSON.parse(JSON.stringify(this.rendererDraft)));
      this.rendererTimer=setTimeout(()=>this.renderRenderer(this.rendererDraft).catch(error=>
        this.updateEditorControls(error.message||String(error),true)),250);
      this.updateEditorControls(this.rendererDirty?"Unsaved model edits · previewing here":"Edits preview here. Save model to keep them.");
    } catch(error) {
      this.rendererInvalid=error.message||String(error);
      this.updateEditorControls(this.rendererInvalid,true);
    }
  }

  async saveRenderer() {
    if(!this.rendererDirty || this.rendererInvalid || this.modelSaving) return;
    const config=JSON.parse(JSON.stringify(this.rendererDraft)), revision=this.baseRendererRevision;
    this.modelSaving=true;
    this.updateEditorControls("Saving model…");
    try {
      await this._hass.callService("home_scheduler","command",{op:"renderer",config,expected_revision:revision});
      this.savedRenderer=config;
      this.baseRendererRevision=revision+1;
      this.rendererDirty=false;
      this.updateEditorControls("Model saved · shared with your other scheduler views");
    } catch(error) {
      this.updateEditorControls(error.message||String(error),true);
    } finally {
      this.modelSaving=false;
      this.updateEditorControls();
      this.syncSavedRenderer();
    }
  }

  discardRenderer() {
    clearTimeout(this.rendererTimer);
    const revision=this.plan.renderer_revision||0;
    if(revision >= this.seenRendererRevision && this.plan.renderer) {
      this.savedRenderer=JSON.parse(JSON.stringify(this.plan.renderer));
      this.baseRendererRevision=this.seenRendererRevision=revision;
    }
    this.rendererDraft=JSON.parse(JSON.stringify(this.savedRenderer));
    this.rendererDirty=false; this.rendererInvalid=null;
    this.editor?.setConfig(JSON.parse(JSON.stringify(this.rendererDraft)));
    this.renderRenderer(this.rendererDraft).catch(error=>this.updateEditorControls(error.message||String(error),true));
    this.updateEditorControls("Draft discarded · using the saved model");
  }

  syncSavedRenderer() {
    if(!this.savedRenderer || this.modelSaving) return;
    const revision=this.plan.renderer_revision||0;
    if(revision <= this.seenRendererRevision || !this.plan.renderer) return;
    this.seenRendererRevision=revision;
    if(this.rendererDirty) {
      this.updateEditorControls("Model changed in another card. Discard this draft to load it.",true);
      return;
    }
    this.savedRenderer=JSON.parse(JSON.stringify(this.plan.renderer));
    this.baseRendererRevision=revision;
    this.rendererDraft=JSON.parse(JSON.stringify(this.savedRenderer));
    this.editor?.setConfig(JSON.parse(JSON.stringify(this.rendererDraft)));
    this.renderRenderer(this.rendererDraft).catch(error=>this.updateEditorControls(error.message||String(error),true));
    this.updateEditorControls("Loaded the model saved in another scheduler view");
  }

  modelStates() {
    const f=this.learningFrame||this.frame;
    if(!f) return {...this._hass.states};
    // Keep the outgoing model's virtual states until its replacement mounts.
    // HA can deliver the new frame before the catalog/configuration update.
    const now=new Date().toISOString(), states={...this._hass.states,...this.previewStateCache};
    for(const device of this.plan.devices) {
      const current=f.physical&&device.target?this._hass.states[device.target]:f.states?.[device.entity];
      states[device.entity]={entity_id:device.entity,state:current?.state||"unavailable",
        attributes:{...(current?.attributes||{}),friendly_name:device.name},last_changed:now,last_updated:now,
        context:{id:"home-preview",parent_id:null,user_id:null}};
      (this.previewStateCache??={})[device.entity]=states[device.entity];
    }
    const timeEntity=this.timeEntity||"input_number.hs_demo_hour";
    states[timeEntity]={entity_id:timeEntity,state:String(f.minute/60),attributes:{friendly_name:"Preview time"},last_changed:now,last_updated:now};
    const elevation=45*Math.sin((f.minute-360)/1440*Math.PI*2);
    states["sun.hs_demo_sun"]={entity_id:"sun.hs_demo_sun",state:elevation>0?"above_horizon":"below_horizon",attributes:{elevation,azimuth:(f.minute/4+90)%360},last_changed:now,last_updated:now};
    states["weather.hs_demo_weather"]={entity_id:"weather.hs_demo_weather",state:"sunny",attributes:{friendly_name:"Demo weather"},last_changed:now,last_updated:now};
    return states;
  }

  updateModel() {
    if(!this.renderer || !this.frame) return;
    const states=this.modelStates();
    const blocked=async()=>{throw new Error("Use the scheduler controls to operate devices.");};
    const readonly={...this._hass,states,callService:async()=>null,callWS:blocked};
    if(this._hass.connection) readonly.connection=new Proxy(this._hass.connection,{
      get:(connection,key)=>["sendMessage","sendMessagePromise"].includes(key)?blocked:
        (typeof connection[key]==="function"?connection[key].bind(connection):connection[key]),
    });
    this.renderer.hass=readonly;
  }

}

if(!customElements.get("home-scheduler-card")) customElements.define("home-scheduler-card",HomeSchedulerCard);
window.customCards=window.customCards||[];
window.customCards.push({type:"home-scheduler-card",name:"Home Scheduler & Simulator",description:"Weekly home schedules and isolated 3D simulation"});
