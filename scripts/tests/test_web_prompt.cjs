// 실제 client 전체를 실행한다. DOM/WS 경계만 대체하며 별도 JS 의존성은 없다.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag; this.children = []; this.dataset = {}; this.events = {};
    this.className = ""; this.value = ""; this.scrollTop = 0; this.clientHeight = 100;
    this.classList = {
      contains: (name) => this.className.split(" ").includes(name),
      add: (name) => { this.className += " " + name; },
      remove: (name) => { this.className = this.className.split(" ").filter(x => x !== name).join(" "); },
    };
  }
  get textContent() { return this.children.map(c => typeof c === "string" ? c : c.textContent).join(""); }
  set textContent(text) { this.children = [String(text)]; }
  get firstElementChild() { return this.children.find(c => typeof c !== "string"); }
  get lastElementChild() { return this.children.findLast(c => typeof c !== "string"); }
  get childElementCount() { return this.children.filter(c => typeof c !== "string").length; }
  get scrollHeight() { return this.childElementCount * 100; }
  append(...children) { for (const c of children) { if (typeof c !== "string") c.parent = this; this.children.push(c); } }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { this.parent.children = this.parent.children.filter(c => c !== this); }
  addEventListener(name, callback) { this.events[name] = callback; }
  fire(name, event = {}) { this.events[name]?.({ preventDefault() {}, ...event }); }
  querySelectorAll() { return []; }
  setAttribute(name, value) { (this.attributes ||= {})[name] = value; }
  closest(selector) {
    if (selector === "[data-action-invocation]" && this.dataset.actionInvocation) return this;
    if (selector === "[data-dialogue-selection]" && this.dataset.dialogueSelection) return this;
    if (selector === "[data-command]" && this.dataset.command) return this;
    return this.parent?.closest(selector) || null;
  }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
}

// 숫자/색은 테스트 wire fixture다. client는 이 opaque semantic을 그대로 사용해야 한다.
const full = [{role:"text",text:"[ "}, {role:"success",text:"60"}, {role:"text",text:"/60 · "},
  {role:"success",text:"40"}, {role:"text",text:"/40 ] >"}];
const damaged = full.map(p => ({...p, text: p.text === "60" ? "52" : p.text}));
const beforeRecovery = [{role:"text",text:"[ 40/60 · 25/40 ] >"}];
const recovered = [{role:"text",text:"[ 41/60 · 26/40 ] >"}];
function client(localNow = 0) {
  const elements = new Map();
  const byId = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const document = new Element();
  document.getElementById = byId;
  document.createElement = tag => new Element(tag);
  document.body = {dataset:{wsUrl:"ws://fixture"}};
  let socket;
  class Socket extends Element {
    static OPEN = 1; static CONNECTING = 0;
    constructor() { super(); this.readyState = 1; this.sent = []; socket = this; }
    send(text) { this.sent.push(JSON.parse(text)); }
  }
  const intervals = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../game/web/static/webclient/js/primal.js"), "utf8"), {
    document, WebSocket:Socket, location:{}, Date:class extends Date { static now() { return localNow; } },
    setInterval:(fn, ms) => intervals.push({fn,ms}),
    setTimeout:() => 1, clearTimeout:() => {},
  });
  const receive = (kind, payload) => socket.fire("message", {data:JSON.stringify([kind,[payload],{}])});
  const state = (segments, exit_details = []) => receive("pz_state", {
    resource_prompt:{kind:"prompt",segments}, currency:{formatted:"20칩",name:"보급칩"},
    exits:exit_details.filter(e => e.exists).map(e => e.name), exit_details, enemies:[], corpses:[], ground_loot:[], interactables:[], inventory:[],
    growth:{attributes:[],skills:[],attribute_points:0,skill_points:0},
  });
  const prompt = segments => receive("pz_log", {kind:"prompt",segments});
  const event = text => receive("pz_log", {kind:"event",segments:[{role:"text",text}]});
  const submit = text => { byId("command").value = text; byId("command-form").fire("submit"); };
  const click = command => document.fire("click", {target:{closest:selector => selector === "[data-command]" ? ({dataset:{command}}) : null}});
  const arrow = key => { byId("command").fire("keydown", {key}); return byId("command").value; };
  state(full); prompt(full);
  return {byId, log:byId("log"), socket, state, prompt, event, submit, click, arrow, intervals, receive, document};
}

test("Action 버튼은 표시 문자열을 재파싱하지 않고 안정 참조를 구조화 전송", () => {
  const c = client();
  const invocation = {action_id:"fixture.inspect",variant:"normal",
    roles:{provider:[{kind:"object",identity:"42",scope_id:"room:7"}]},arguments:{}};
  c.receive("pz_action_result", {action:invocation});
  const button = c.byId("context-actions").lastElementChild;
  c.document.fire("click", {target:button});
  const [kind, args, options] = c.socket.sent.at(-1);
  assert.equal(kind, "pz_action"); assert.deepEqual(options, {});
  assert.deepEqual({...args[0],request_id:undefined}, {...invocation,request_id:undefined});
  assert.equal(typeof args[0].request_id, "string");
  assert.equal(c.socket.sent.filter(frame => frame[0] === "text").length, 0);
  const first = args[0].request_id;
  c.document.fire("click", {target:button});
  assert.notEqual(c.socket.sent.at(-1)[1][0].request_id, first);
});

test("NPC 키워드는 승인된 토큰만 버튼으로 렌더링하고 원문을 DOM text로 보존", () => {
  const c = client();
  c.receive("pz_log", {kind:"chat", segments:[
    {role:"npc",text:"윤대장: "},
    {role:"dialogue_topic",text:"〈임무〉",dialogue_selection:"opaque-topic"},
    {role:"dialogue_action",text:"〈수락〉",dialogue_selection:"opaque-action"},
    {role:"text",text:"〈보고〉",dialogue_selection:"unapproved"},
    {role:"dialogue_topic",text:"〈만료〉"},
    {role:"text",text:"<img src=x onerror=alert(1)>"},
  ]});
  const row = c.log.lastElementChild;
  const topic = row.children[1], action = row.children[2];
  assert.equal(topic.tagName, "button"); assert.equal(action.type, "button");
  assert.equal(topic.attributes["aria-label"], "NPC 화제 질문: 〈임무〉");
  assert.equal(action.attributes["aria-label"], "NPC 행동 실행: 〈수락〉");
  assert.equal(row.children[3].tagName, "span"); assert.equal(row.children[4].tagName, "span");
  assert.equal(row.children[3].dataset.dialogueSelection, undefined);
  assert.equal(row.children[5].textContent, "<img src=x onerror=alert(1)>");
  c.document.fire("click", {target:topic});
  assert.deepEqual(c.socket.sent.at(-1), ["pz_dialogue",["opaque-topic"],{}]);
  for (const key of ["Enter", " "]) {
    let prevented = false;
    c.document.fire("keydown", {target:action,key,preventDefault:()=>{prevented=true;}});
    assert.equal(prevented, true);
    assert.deepEqual(c.socket.sent.at(-1), ["pz_dialogue",["opaque-action"],{}]);
  }
  const sent = c.socket.sent.length;
  c.document.fire("click", {target:row.children[3]});
  c.document.fire("keydown", {target:row.children[4],key:"Enter"});
  c.document.fire("keydown", {target:action,key:"Enter",isComposing:true});
  assert.equal(c.socket.sent.length, sent);
  const segments = [
    {role:"muted",text:"현재 사용 가능: "},
    {role:"command",text:"'윤대장에게 임무"},
    {role:"text",text:" · "},
    {role:"command",text:"'윤대장에게 <img src=x> |r진행|n"},
  ];
  c.receive("pz_log", {kind:"event", segments});
  const guide = c.log.lastElementChild;
  assert.equal(guide.className, "log-entry event");
  assert.equal(guide.textContent, segments.map(part => part.text).join(""));
  assert.deepEqual(guide.children.map(part => part.className),
    ["semantic-muted", "semantic-command", "semantic-text", "semantic-command"]);
  assert.ok(guide.children.every(part => part.tagName === "span"));
  assert.equal(guide.children[3].textContent, segments[3].text);
  c.document.fire("click", {target:guide.children[1]});
  assert.equal(c.socket.sent.length, sent); // 명령 예시는 별도 NPC 선택 버튼이 아니다.
});

test("NPC 키워드 팔레트는 로그 배경과 4.5:1 이상 대비하고 포커스 표시 유지", () => {
  const css = fs.readFileSync(path.join(__dirname, "../../game/web/static/webclient/css/primal.css"), "utf8");
  const luminance = hex => {
    const channels = hex.match(/\w\w/g).map(v => parseInt(v,16)/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4);
    return channels[0]*.2126 + channels[1]*.7152 + channels[2]*.0722;
  };
  const background = luminance(css.match(/--bg:#([0-9a-f]{6})/)[1]);
  for (const role of ["topic", "action"]) {
    const foreground = luminance(css.match(new RegExp(`\\.semantic-dialogue_${role}\\{color:#([0-9a-f]{6})`))[1]);
    assert.ok((foreground+.05)/(background+.05) >= 4.5);
  }
  assert.match(css, /button:focus-visible\{outline:2px/);
});

test("일반 명령은 마지막 대기 prompt와 같은 행, command semantic 유지", () => {
  const c = client(); const row = c.log.lastElementChild;
  c.submit("상태");
  assert.equal(c.log.children.length, 1);
  assert.equal(row.textContent, "[ 60/60 · 40/40 ] > 상태");
  assert.equal(row.dataset.awaitingInput, "false");
  assert.equal(row.children.at(-1).className, "semantic-command");
  assert.equal(row.children[1].className, "semantic-success");
  c.event("상태 결과"); c.prompt(full);
  assert.equal(c.log.lastElementChild.dataset.awaitingInput, "true");
  assert.equal(row.textContent, "[ 60/60 · 40/40 ] > 상태");
  const dialogue = client();
  dialogue.submit("'윤대장에게 임무");
  dialogue.receive("pz_log", {kind:"chat", segments:[
    {role:"player",text:"탐사자"}, {role:"text",text:": "}, {role:"text",text:"윤대장에게 임무"},
  ]});
  dialogue.receive("pz_log", {kind:"chat", segments:[
    {role:"npc",text:"윤대장"}, {role:"text",text:": "}, {role:"text",text:"임무를 안내합니다."},
  ]});
  assert.deepEqual(dialogue.log.children.map(entry => entry.textContent), [
    "[ 60/60 · 40/40 ] > '윤대장에게 임무", "탐사자: 윤대장에게 임무", "윤대장: 임무를 안내합니다.",
  ]);
  assert.deepEqual(dialogue.log.children.slice(1).map(entry => entry.className), ["log-entry chat", "log-entry chat"]);
  assert.deepEqual(dialogue.log.children.slice(1).map(entry => entry.children.map(part => part.className)),
    [["semantic-player", "semantic-text", "semantic-text"], ["semantic-npc", "semantic-text", "semantic-text"]]);
});
test("자동 피해 메시지 뒤에는 과거 prompt 대신 최신 서버 state로 새 입력 행", () => {
  const c = client(); const old = c.log.lastElementChild;
  c.state(damaged); c.event("갈퀴사냥룡이 달려들어 8의 피해를 입혔다."); c.submit("상태");
  assert.deepEqual(c.log.children.map(e=>e.textContent), [
    "[ 60/60 · 40/40 ] >", "갈퀴사냥룡이 달려들어 8의 피해를 입혔다.", "[ 52/60 · 40/40 ] > 상태",
  ]);
  assert.equal(old.textContent, "[ 60/60 · 40/40 ] >");
});
test("회복 뒤 최신 prompt에 입력하며 과거 행은 그대로", () => {
  const c = client(); c.log.replaceChildren(); c.prompt(beforeRecovery); c.prompt(recovered); c.submit("상태");
  assert.deepEqual(c.log.children.map(e=>e.textContent), ["[ 40/60 · 25/40 ] >", "[ 41/60 · 26/40 ] > 상태"]);
});
test("빈·공백 입력은 command span/history 없이 서버의 새 prompt만", () => {
  const c = client();
  for (const blank of ["", " ", "   "]) {
    const previous = c.log.lastElementChild; c.submit(blank);
    assert.equal(previous.children.some(e=>e.className === "semantic-command"), false);
    c.prompt(full);
    assert.equal(c.arrow("ArrowUp"), "");
  }
  assert.deepEqual(c.log.children.map(e=>e.textContent), Array(4).fill("[ 60/60 · 40/40 ] >"));
});
test("버튼과 직접 입력은 같은 행 및 실제 명령 history", () => {
  const c = client(); c.submit("상태"); c.prompt(full); c.click("북"); c.prompt(full); c.submit("공격");
  assert.deepEqual(c.log.children.map(e=>e.textContent), ["[ 60/60 · 40/40 ] > 상태", "[ 60/60 · 40/40 ] > 북", "[ 60/60 · 40/40 ] > 공격"]);
  assert.equal(c.arrow("ArrowUp"), "공격"); assert.equal(c.arrow("ArrowUp"), "북");
  assert.equal(c.arrow("ArrowUp"), "상태"); assert.equal(c.arrow("ArrowDown"), "북");
});
test("60초 keepalive는 send만 하며 echo/prompt/history가 없다", () => {
  const c = client(); const keepalive = c.intervals.find(t=>t.ms === 60000); keepalive.fn();
  assert.deepEqual(c.socket.sent.at(-1), ["text",["idle"],{}]);
  assert.equal(c.log.children.length, 1); assert.equal(c.arrow("ArrowUp"), "");
  c.submit("idle"); assert.equal(c.log.children.length, 1); assert.equal(c.arrow("ArrowUp"), "");
});
test("연속 제출은 완료 input row를 다시 고치지 않는다", () => {
  const c = client(); c.submit("상태"); c.submit("북");
  assert.deepEqual(c.log.children.map(e=>e.textContent), ["[ 60/60 · 40/40 ] > 상태", "[ 60/60 · 40/40 ] > 북"]);
});
test("위로 읽는 비동기 출력은 scroll-lock, 직접 제출은 bottom", () => {
  const c = client(); for (let i=0;i<10;i++) c.event("과거 출력");
  c.log.scrollTop = 0; c.prompt(full);
  assert.equal(c.log.scrollTop, 0); assert.equal(c.byId("latest").hidden, false);
  c.submit("상태"); assert.equal(c.log.scrollTop, c.log.scrollHeight); assert.equal(c.byId("latest").hidden, true);
});
test("채팅/실패/Account/입력 대기 응답도 literal command span이며 별도 echo 없음", () => {
  const c = client();
  for (const text of ["안녕하세요 말", "'안녕하세요", "날아", "접속자", "대기시험", "<응답>", "종료"]) {
    c.prompt(full); c.submit(text);
    assert.equal(c.log.lastElementChild.textContent, "[ 60/60 · 40/40 ] > " + text);
    assert.equal(c.log.lastElementChild.children.at(-1).tagName, "span");
  }
  assert.equal(c.log.children.some(e=>e.classList.contains("command")), false);
});


test("실제 출구 상태로 중앙 기호·제한 버튼·층 명령을 표시하며 기호는 보내지 않음", () => {
  const c = client();
  const entry = (name, can_move = true) => ({name, exists:true, can_move, status:can_move ? "이동 가능" : "전투 중 이동 불가", destination_name:"미탐사", reason:""});
  c.state(full, [entry("위"), entry("아래", false), entry("나가기")]);
  let [grid, label, buttons] = c.byId("exits").children;
  assert.equal(grid.firstElementChild.textContent, "X");
  assert.equal(grid.firstElementChild.firstElementChild.className, "semantic-warning");
  assert.equal(label.textContent, "출구");
  assert.deepEqual(buttons.children.map(b => [b.textContent, b.disabled, b.dataset.command]), [["위",false,"위"],["아래",true,"아래"],["나가기",false,"나가기"]]);
  c.state(full, ["1층","2층","3층","4층","5층","옥상"].map(n => entry(n)));
  [grid, label, buttons] = c.byId("exits").children;
  assert.equal(grid.firstElementChild.textContent, "o");
  assert.equal(buttons.children.length, 6);
  c.click(buttons.children[4].dataset.command);
  assert.deepEqual(c.socket.sent.at(-1), ["text",["5층"],{}]);
});
const partyState = (party, extra = {}) => ({
  resource_prompt:{kind:"prompt",segments:full}, currency:{formatted:"20칩",name:"보급칩"},
  exits:[],exit_details:[],enemies:[],corpses:[],ground_loot:[],interactables:[],inventory:[],
  growth:{attributes:[],skills:[],attribute_points:0,skill_points:0}, party, ...extra,
});
const commandButtons = element => element.children.flatMap(child => typeof child === "string" ? [] :
  [...(child.dataset.command ? [child.dataset.command] : []), ...commandButtons(child)]);

test("일행 패널은 영속 담당·현재 효과·승계를 표시하고 서버 명령만 전송", () => {
  const c = client();
  const party = {id:42,leader:1,leader_name:"탐사자",is_leader:true,leader_online:true,max_size:4,
    members:[{id:1,name:"탐사자",label:"탐사자 1",online:true},{id:2,name:"<b>철수</b>",label:"철수 2",online:false}],
    defender:{id:2,name:"<b>철수</b>",online:false,active:false},can_succeed:false,
    join_requests:[{id:3,name:"민수",label:"민수 1"}],invitations:[{id:4,name:"영희"}],confirm_dissolve:false};
  c.receive("pz_state",partyState(party,{enemies:[{label:"어린청소룡 2",name:"어린청소룡",can_attack:true,hp:20,max_hp:20}]}));
  assert.match(c.byId("party-state").textContent,/일행 #42/);
  assert.match(c.byId("party-tactics").textContent,/2\/4.*오프라인.*효과 비활성.*지정 유지/);
  assert.match(c.byId("party-members").textContent,/<b>철수<\/b>/);
  const commands = ["party-actions","party-members","party-pending"].flatMap(id => commandButtons(c.byId(id)));
  for (const command of ["일행","일행탈퇴","일행방어","일행공격","어린청소룡 2 일행공격","해제 일행방어","순번 일행분배","일행해체","철수 2 일행리더","철수 2 일행제외","철수 2 일행방어","민수 1 일행허락","민수 1 일행거절"]) assert.ok(commands.includes(command), command);
  c.receive("pz_state",partyState({...party,confirm_dissolve:true}));
  assert.ok(commandButtons(c.byId("party-actions")).includes("확인 일행해체"));
  c.receive("pz_state",partyState({...party,is_leader:false,leader_online:false,can_succeed:true}));
  const ordinary = commandButtons(c.byId("party-actions"));
  assert.ok(ordinary.includes("일행승계"));
  assert.ok(!ordinary.includes("일행해체"));
  assert.ok(!commandButtons(c.byId("party-members")).some(command => command.endsWith("일행제외")));
  c.byId("party-chat-body").value = "모여 주세요";
  c.byId("party-chat-form").fire("submit");
  assert.equal(c.socket.sent.at(-1)[1][0],"모여 주세요 일행대화");
  c.receive("pz_state",partyState(null,{invitation:{inviter:"영희"},join_request:{party_id:99}}));
  assert.ok(commandButtons(c.byId("party-actions")).includes("일행모으기"));
  assert.equal(c.byId("party-invitation").hidden,false);
  assert.match(c.byId("party-outgoing").textContent,/#99/);
  c.byId("party-target").value = "철수 2";
  c.byId("party-invite-form").fire("submit",{submitter:{value:"일행요청"}});
  assert.equal(c.socket.sent.at(-1)[1][0],"철수 2 일행요청");
  c.byId("party-invite-form").fire("submit",{submitter:{value:"일행초청"}});
  assert.equal(c.socket.sent.at(-1)[1][0],"철수 2 일행초청");
});

test("일행 TTL은 서버 수신 시각 스냅샷이며 만료·새 상태를 안전하게 반영", () => {
  for (const localNow of [-1000000000000, 9999999999999]) {
    const c = client(localNow);
    const pending = {id:3,name:"민수",label:"민수",expires_at:160};
    const party = {id:42,leader:1,leader_name:"리더",is_leader:true,leader_online:true,
      members:[],join_requests:[pending],invitations:[{...pending,name:"영희"}]};
    const extra = {server_now:100,invitation:{inviter:"영희",expires_at:160},
      join_request:{party_id:99,expires_at:160}};
    const intervalCount = c.intervals.length;
    for (const [now, seconds] of [[100,60],[118,42],[151,9],[159.999,1]]) {
      c.receive("pz_state",partyState(party,{...extra,server_now:now}));
      for (const id of ["party-pending","party-outgoing","party-inviter"])
        assert.ok(c.byId(id).textContent.includes(seconds + "초 남음 (수신 기준)"), id);
      assert.ok(commandButtons(c.byId("party-pending")).includes("민수 일행허락"));
      assert.equal(c.byId("party-invitation").hidden,false);
    }
    for (const now of [160,161,999]) {
      c.receive("pz_state",partyState(party,{...extra,server_now:now}));
      for (const id of ["party-pending","party-outgoing","party-inviter"])
        assert.ok(c.byId(id).textContent.includes("만료됨"));
      assert.deepEqual(commandButtons(c.byId("party-pending")),[]);
      assert.equal(c.byId("party-invitation").hidden,true);
    }
    // 새 서버 상태의 만료 시각을 사용하며 동일 서버 시각이면 로컬 시계는 영향이 없다.
    c.receive("pz_state",partyState({...party,join_requests:[{...pending,expires_at:220}],invitations:[]},
      {server_now:170,invitation:null,join_request:null}));
    assert.match(c.byId("party-pending").textContent,/50초 남음/);
    assert.equal(c.byId("party-outgoing").textContent,"");
    assert.equal(c.byId("party-invitation").hidden,true);
    c.receive("pz_state",partyState({...party,join_requests:[],invitations:[]},{server_now:171}));
    assert.equal(c.byId("party-pending").textContent,"");
    assert.equal(c.intervals.length,intervalCount);
  }
});

test("재바인딩 중 승계 불가 스냅샷은 버튼과 상태 설명을 일치시킨다", () => {
  const c = client();
  const party = {id:42,leader:1,leader_name:"리더",is_leader:false,leader_online:false,
    members:[],can_succeed:false};
  c.receive("pz_state",partyState(party));
  assert.ok(!commandButtons(c.byId("party-actions")).includes("일행승계"));
  assert.match(c.byId("party-state").textContent,/승계 불가/);
  c.receive("pz_state",partyState({...party,can_succeed:true}));
  assert.ok(commandButtons(c.byId("party-actions")).includes("일행승계"));
  assert.match(c.byId("party-state").textContent,/승계 가능/);
});

test("문 조작은 안정 Endpoint Action이고 이동은 기존 text 경로를 유지", () => {
  const c = client();
  const door = actions => ({name:"관리실 문",label:"동 관리실 문",role:"object",look_command:"동 문 봐",actions});
  const exit = can_move => ({name:"동",exists:true,can_move,status:can_move ? "이동 가능" : "문 닫힘",destination_name:"미탐사",reason:""});
  const action = operation => ({action_id:"door." + operation,variant:"normal",roles:{provider:[{kind:"door",identity:"42",scope_id:"room:7"}]},arguments:{}});
  c.receive("pz_state",partyState(null,{interactables:[door([{label:"열어",action:action("open")}])],exit_details:[exit(false)],exits:["동"]}));
  const open = c.byId("context-actions").children.find(row => row.dataset.actionInvocation);
  assert.ok(open);
  assert.equal(open.firstElementChild.className,"semantic-object");
  c.document.fire("click",{target:open});
  assert.equal(c.socket.sent.at(-1)[0],"pz_action");
  assert.deepEqual(c.socket.sent.at(-1)[1][0].roles,action("open").roles);
  c.receive("pz_state",partyState(null,{interactables:[door([{label:"닫아",action:action("close")}])],exit_details:[exit(true)],exits:["동"]}));
  const close = c.byId("context-actions").children.find(row => row.dataset.actionInvocation);
  assert.equal(JSON.parse(close.dataset.actionInvocation).action_id,"door.close");
  c.receive("pz_state",partyState(null,{interactables:[door([])],exit_details:[exit(false)],exits:["동"]}));
  assert.equal(c.byId("context-actions").children.filter(row => row.dataset.actionInvocation).length,0);
  const move = c.byId("exits").firstElementChild.children.find(row => row.dataset?.command === "동");
  assert.equal(move.disabled,true);
});

test("재분배 버튼은 서버 배열 순서와 무관하게 선언된 scope의 Action만 전송", () => {
  const c = client();
  const reset = ["all","attributes","skills"].map(scope => ({action:{action_id:"training.reset."+scope,
    variant:"normal",roles:{provider:[{kind:"object",identity:"42",scope_id:"room:7"}]},arguments:{value:scope}}}));
  c.receive("pz_state",partyState(null,{training_controls:{reset}}));
  for (const scope of ["attributes","skills","all"]) {
    const button = c.byId("reset-"+scope);
    assert.equal(button.disabled,false);
    c.document.fire("click",{target:button});
    const frame = c.socket.sent.at(-1);
    assert.equal(frame[0],"pz_action");
    assert.equal(frame[1][0].arguments.value,scope);
    assert.equal(frame[1][0].action_id,"training.reset."+scope);
  }
});

test("아이템 버튼은 같은 표시 이름에서도 해당 UUID의 구조화 Action만 전송", () => {
  const c = client();
  const item = identity => ({id:"bandage",identity,name:"붕대",selector:"붕대 2",count:3});
  const action = identity => ({action_id:"item.bandage.use",variant:"normal",
    roles:{provider:[{kind:"item",identity,scope_id:"character:7"}],
      subject:[{kind:"item",identity,scope_id:"character:7"}]},arguments:{count:"1"}});
  c.receive("pz_state",partyState(null,{inventory:[item("original"),item("other")],
    action_controls:[{label:"사용",action:action("original")},{label:"사용",action:action("other")}]}));
  const rows = c.byId("inventory").children;
  for (const [index, identity] of ["original","other"].entries()) {
    const buttons = rows[index].children.filter(child => child.dataset?.actionInvocation);
    assert.equal(buttons.length,1);
    c.document.fire("click",{target:buttons[0]});
    assert.equal(c.socket.sent.at(-1)[0],"pz_action");
    assert.equal(c.socket.sent.at(-1)[1][0].roles.subject[0].identity,identity);
    assert.equal(commandButtons(rows[index]).length,0);
  }
  assert.equal(c.byId("context-actions").children.filter(child => child.dataset?.actionInvocation).length,0);
  c.receive("pz_state",partyState(null,{inventory:[item("replacement")],action_controls:[]}));
  assert.equal(c.byId("inventory").firstElementChild.children.filter(child => child.dataset?.actionInvocation).length,0);
});
