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
  const timeouts = new Map();
  let timerId = 0;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../game/web/static/webclient/js/primal.js"), "utf8"), {
    document, WebSocket:Socket, location:{}, Date:class extends Date { static now() { return localNow; } },
    setInterval:(fn, ms) => intervals.push({fn,ms}),
    setTimeout:(fn, ms) => { timeouts.set(++timerId, {fn,ms}); return timerId; },
    clearTimeout:id => timeouts.delete(id),
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
  return {byId, log:byId("log"), get socket() { return socket; }, state, prompt, event, submit, click, arrow, intervals, timeouts, receive, document};
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
  const grid = c.byId("exits"), buttons = c.byId("other-exit-buttons");
  assert.equal(grid.firstElementChild.textContent, "X");
  assert.equal(grid.firstElementChild.firstElementChild.className, "semantic-warning");
  assert.equal(grid.childElementCount, 1);
  assert.deepEqual(buttons.children.map(b => [b.textContent, b.disabled, b.dataset.command]), [["위",false,"위"],["아래",true,"아래"],["나가기",false,"나가기"]]);
  c.state(full, ["1층","2층","3층","4층","5층","옥상"].map(n => entry(n)));
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
  const target = {variant:"adapter",roles:{subject:[{kind:"actor",identity:"42",scope_id:"room:7"}]},
    arguments:{generation:9}};
  const attack = {...target,action_id:"global.attack"};
  const partyAttack = {...target,action_id:"global.party_attack"};
  c.receive("pz_state",partyState(party,{enemies:[{label:"어린청소룡 2",name:"어린청소룡",can_attack:true,hp:20,max_hp:20,
    attack_action:attack,party_attack_action:partyAttack}]}));
  const partyAttackButton = c.byId("party-actions").children.find(el => el.dataset?.actionInvocation);
  c.document.fire("click",{target:partyAttackButton});
  const [event, [payload]] = c.socket.sent.at(-1);
  assert.equal(event,"pz_action");
  assert.deepEqual({...payload,request_id:null},{...partyAttack,request_id:null});
  assert.match(c.byId("party-state").textContent,/일행 #42/);
  assert.match(c.byId("party-tactics").textContent,/2\/4.*오프라인.*효과 비활성.*지정 유지/);
  assert.match(c.byId("party-members").textContent,/<b>철수<\/b>/);
  const commands = ["party-actions","party-members","party-pending"].flatMap(id => commandButtons(c.byId(id)));
  for (const command of ["일행","일행탈퇴","일행방어","일행공격","해제 일행방어","순번 일행분배","일행해체","철수 2 일행리더","철수 2 일행제외","철수 2 일행방어","민수 1 일행허락","민수 1 일행거절"]) assert.ok(commands.includes(command), command);
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
  const move = c.byId("exits").children.find(row => row.dataset?.command === "동");
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


test("전리품 버튼은 Source와 Entry 안정 참조를 보존하고 문자열 명령을 실행하지 않는다", () => {
  const c = client();
  const action = (source, identity, quantity = 0) => ({action_id:"loot.take",variant:"take",
    roles:{provider:[{kind:"object",identity:source,scope_id:"room:7"}],
      source:[{kind:"object",identity:source,scope_id:"room:7"}],
      subject:[{kind:"loot",identity,scope_id:"source:"+source}]},
    arguments:{quantity,snapshot:"server-signed-"+identity}});
  const entry = (source, identity) => ({display_label:"회수부품 3 ×2",protected:false,
    can_take:true,take_command:"대체하면 안 되는 문자열 가져",action:action(source,identity)});
  const corpse = (id, identity) => ({id,label:"시체 "+id,name:"사체",look_command:"시체 "+id+" 봐",
    loot:[entry(String(id),identity)],take_command:"구형 전체 가져",take_action:action(String(id),identity)});
  const corpses = [corpse(3,"original-corpse-entry"),corpse(4,"other-corpse-entry")];
  const all = {corpses:action("3","original-corpse-entry"),ground:action("8","original-ground-entry")};
  c.receive("pz_state",partyState(null,{corpses,
    ground_loot:[{id:8,loot:[entry("8","original-ground-entry")]}],loot_actions:all}));
  const buttons = c.byId("context-actions").children.filter(row => row.dataset?.actionInvocation);
  assert.equal(buttons.length,7); // 여러 시체 전체, 출처별 전체/개별, 바닥 전체/개별
  for (const button of buttons) {
    const expected = JSON.parse(button.dataset.actionInvocation);
    c.document.fire("click",{target:button});
    const [kind,args] = c.socket.sent.at(-1);
    assert.equal(kind,"pz_action");
    assert.deepEqual(args[0].roles,expected.roles);
    assert.deepEqual(args[0].arguments,expected.arguments);
  }
  assert.ok(commandButtons(c.byId("context-actions")).every(command => command.endsWith(" 봐")));
  const stale = buttons.at(-1);
  c.receive("pz_state",partyState(null,{ground_loot:[{id:8,loot:[entry("8","replacement")]}],
    loot_actions:{ground:action("8","replacement")}}));
  // 지연된 DOM 클릭도 원래 참조 그대로 보낸다. 현재 번호로 새 항목을 찾지 않는다.
  c.document.fire("click",{target:stale});
  assert.equal(c.socket.sent.at(-1)[1][0].roles.subject[0].identity,"original-ground-entry");
  assert.equal(c.socket.sent.at(-1)[1][0].arguments.snapshot,"server-signed-original-ground-entry");
});

test("전체 회수가 차단되어도 유효한 개별 전리품을 빈 전리품으로 표시하지 않는다", () => {
  const c = client();
  const action = {action_id:"loot.take",variant:"take",roles:{
    provider:[{kind:"object",identity:"corpse-original",scope_id:"room:7"}],
    source:[{kind:"object",identity:"corpse-original",scope_id:"room:7"}],
    subject:[{kind:"loot",identity:"entry-original",scope_id:"source:corpse-original"}]},
    arguments:{quantity:0,snapshot:"server-signed-original"}};
  const entry = {display_label:"회수부품 2 ×1",protected:false,can_take:true,action};
  const render = (loot, loot_obscured = false) => c.receive("pz_state",partyState(null,{corpses:[{
    id:"corpse-original",label:"시체 2",name:"사체",look_command:"시체 2 봐",
    loot,take_action:null,loot_obscured}]}));
  const context = c.byId("context-actions");
  render([entry]);
  assert.ok(!context.textContent.includes("회수 가능한 전리품 없음"));
  assert.ok(!context.textContent.includes("전리품을 식별하기 어려움"));
  assert.ok(!context.textContent.includes("시체 2 전리품 회수"));
  const buttons = context.children.filter(row => row.dataset?.actionInvocation);
  assert.equal(buttons.length,1);
  assert.equal(buttons[0].disabled,false);
  c.document.fire("click",{target:buttons[0]});
  const [kind,args] = c.socket.sent.at(-1);
  assert.equal(kind,"pz_action");
  assert.deepEqual(args[0].roles,action.roles);
  assert.deepEqual(args[0].arguments,action.arguments);
  assert.equal(c.socket.sent.filter(frame => frame[0] === "text").length,0);

  render([]);
  assert.ok(context.textContent.includes("회수 가능한 전리품 없음"));
  render([],true);
  assert.ok(context.textContent.includes("전리품을 식별하기 어려움"));
  render([{...entry,action:null,can_take:false}]);
  assert.ok(context.textContent.includes("회수 가능한 전리품 없음"));
  assert.equal(JSON.parse(context.lastElementChild.dataset.actionInvocation),null);
  assert.equal(context.lastElementChild.disabled,true);
});

function mapState(c, revision, owner = "explorer-a", state = {}) {
  c.receive("pz_state", partyState(null, {minimap_revision:revision, minimap_owner:owner, ...state}));
}
function mapFrames(socket) {
  return socket.sent.filter(frame => frame[0] === "pz_map").map(frame => frame[1][0]);
}
function mapReply(c, revision, request, label, sheet = "본부") {
  c.receive("pz_map", {id:request.id, revision, owner:"explorer-a", sheet, sheets:["본부", "전초구역"], centers:["중앙 복도"],
    summary:"현재 위치 중앙 복도. 동쪽은 다른 지도 경계입니다.", messages:[
      {kind:"sheet", segments:[{role:"title", text:label}]},
      {kind:"map", segments:[{role:"player", text:"@"}, {role:"text", text:"─+"}]},
      {kind:"event", segments:[{role:"dialogue_action", dialogue_selection:"ignored", text:"<문>"}]},
    ]});
}

test("미니맵은 지도가 필요한 공개 revision에서만 요청하고 Semantic Text를 조작 없이 표시", () => {
  const c = client();
  c.receive("pz_map_state", {revision:"r0", owner:"explorer-a"});
  assert.deepEqual(mapFrames(c.socket), []);
  assert.equal(c.byId("minimap-panel").hidden, true);
  mapState(c, "r1");
  const [first] = mapFrames(c.socket);
  assert.deepEqual(first, {id:1});
  assert.equal(c.byId("minimap-panel").hidden, false);
  for (let i=1; i<=20; i++) mapState(c, "r1", "explorer-a", {hp:60-i, mental:20+i, player_round:i});
  assert.equal(mapFrames(c.socket).length, 1);
  mapReply(c, "r1", first, "본부 지도");
  const content = c.byId("minimap-content");
  assert.equal(content.textContent, "본부 지도@─+<문>");
  const grid = content.children[1];
  assert.equal(grid.attributes["aria-hidden"], "true");
  assert.equal(grid.firstElementChild.className, "semantic-player");
  assert.equal(content.children[2].firstElementChild.tagName, "span");
  assert.equal(content.children[2].firstElementChild.dataset.dialogueSelection, undefined);
  assert.match(c.byId("minimap-description").textContent, /현재 위치 중앙 복도/);
  for (let i=1; i<=20; i++) mapState(c, "r1", "explorer-a", {hp:i, xp:i, player_round:i});
  assert.equal(mapFrames(c.socket).length, 1);
  assert.equal(content.children[1], grid);
});

test("현재 위치 지도에서 다른 시트와 같은 이름의 중심을 현재 응답 시트로 한정", () => {
  const c = client();
  mapState(c, "r1");
  const last = () => mapFrames(c.socket).at(-1);
  mapReply(c, "r1", last(), "본부 지도");
  assert.equal(c.byId("minimap-sheet").value, "");
  c.byId("minimap-center").value = "중앙 복도";
  c.byId("minimap-center-form").fire("submit");
  assert.deepEqual(last(), {id:2, sheet:"본부", center:"중앙 복도"});
  mapReply(c, "r1", last(), "복도 중심");
  c.byId("minimap-center").value = "다음 장소";
  c.byId("minimap-center-form").fire("submit");
  assert.deepEqual(last(), {id:3, sheet:"본부", center:"다음 장소"});
  c.byId("minimap-current").fire("click");
  assert.deepEqual(last(), {id:4});
  mapReply(c, "r1", last(), "현재 위치 지도", "전초구역");
  assert.equal(c.byId("minimap-sheet").value, "");
  c.byId("minimap-center").value = "중앙 복도";
  c.byId("minimap-center-form").fire("submit");
  assert.deepEqual(last(), {id:5, sheet:"전초구역", center:"중앙 복도"});
});

test("자동 추적 갱신 중 입력을 유지하고 최신 공개 Sheet가 확정된 뒤에만 중심을 전송", () => {
  const c = client();
  const last = () => mapFrames(c.socket).at(-1);
  const input = c.byId("minimap-center"), form = c.byId("minimap-center-form");
  const button = c.byId("minimap-center-submit");
  mapState(c, "r1");
  input.value = "중앙 복도";
  form.fire("submit");
  assert.deepEqual(mapFrames(c.socket), [{id:1}]);
  assert.equal(button.disabled, true);
  mapReply(c, "r1", last(), "연구소 1층", "본부");
  assert.equal(button.disabled, false);
  mapState(c, "r2");
  form.fire("submit");
  assert.deepEqual(mapFrames(c.socket), [{id:1}, {id:2}]);
  assert.equal(input.value, "중앙 복도");
  mapReply(c, "r1", last(), "오래된 지도");
  assert.equal(button.disabled, true);
  form.fire("submit");
  assert.equal(mapFrames(c.socket).length, 2);
  mapReply(c, "r2", last(), "최신 지도", "전초구역");
  assert.equal(button.disabled, false);
  assert.equal(mapFrames(c.socket).length, 2);
  form.fire("submit");
  assert.deepEqual(last(), {id:3, sheet:"전초구역", center:"중앙 복도"});
  input.value = "다른 복도";
  form.fire("submit");
  assert.equal(mapFrames(c.socket).length, 3);
  assert.equal(input.value, "다른 복도");
});

test("전역 중심 검색으로 확인한 지도는 다음 중심 이름의 범위에 사용", () => {
  const c = client();
  mapState(c, "r1");
  const last = () => mapFrames(c.socket).at(-1);
  c.receive("pz_map", {id:last().id, revision:"r1", owner:"explorer-a",
    sheet:"", sheets:["전초구역"], centers:[],
    messages:[{kind:"sheet", segments:[{text:"승강기", role:"text"}]}]});
  assert.equal(c.byId("minimap-center-submit").disabled, false);
  c.byId("minimap-center").value = "탐사대 부두";
  c.byId("minimap-center-form").fire("submit");
  assert.deepEqual(last(), {id:2, center:"탐사대 부두"});
  c.receive("pz_map", {id:last().id, revision:"r1", owner:"explorer-a",
    sheet:"전초구역", sheets:["본부", "전초구역"], centers:["부두"],
    messages:[{kind:"map", segments:[{text:"o", role:"text"}]}], summary:"탐사대 부두"});
  assert.equal(c.byId("minimap-sheet").value, "전초구역");
  const receivedId = last().id;
  mapState(c, "r1");
  assert.equal(last().id, receivedId);
  mapState(c, "r2");
  assert.deepEqual(last(), {id:receivedId + 1, sheet:"전초구역", center:"탐사대 부두"});
  mapReply(c, "r2", last(), "부두 중심", "전초구역");
  c.byId("minimap-center").value = "다음 장소";
  c.byId("minimap-center-form").fire("submit");
  assert.equal(last().sheet, "전초구역");
});

test("시트·중심 전환의 늦은 응답을 폐기하고 revision이 바뀌면 이전 공개 지도를 먼저 숨김", () => {
  const c = client();
  const requests = () => mapFrames(c.socket);
  const last = () => requests().at(-1);
  mapState(c, "r1");
  mapReply(c, "r1", last(), "첫 지도");
  c.byId("minimap-sheet").value = "전초구역";
  c.byId("minimap-sheet").fire("change");
  const switched = last();
  assert.equal(switched.sheet, "전초구역");
  c.byId("minimap-center").value = "화면 밖 부두";
  c.byId("minimap-center-form").fire("submit");
  assert.equal(last(), switched);
  assert.equal(c.byId("minimap-center").value, "화면 밖 부두");
  mapReply(c, "r1", switched, "시트 응답", "전초구역");
  c.byId("minimap-center-form").fire("submit");
  const centered = last();
  assert.deepEqual(centered, {id:3, sheet:"전초구역", center:"화면 밖 부두"});
  mapReply(c, "r1", centered, "부두 중심", "전초구역");
  mapReply(c, "r1", switched, "늦은 시트");
  assert.match(c.byId("minimap-content").textContent, /^부두 중심/);
  c.byId("minimap-center").value = "입력 중";
  c.receive("pz_map_state", {revision:"r2", owner:"explorer-a"});
  assert.equal(c.byId("minimap-content").textContent, "");
  assert.equal(c.byId("minimap-content").attributes["aria-busy"], "true");
  assert.equal(c.byId("minimap-center").value, "입력 중");
  assert.deepEqual(c.byId("minimap-centers").children, []);
  assert.equal(c.byId("minimap-description").textContent, "");
  assert.deepEqual(c.byId("minimap-sheet").children.map(e=>e.value), [""]);
  const changed = last();
  mapReply(c, "r1", changed, "권한 철회 전 응답");
  assert.equal(c.byId("minimap-content").textContent, "");
  c.receive("pz_map", {id:changed.id, revision:"r2", owner:"explorer-a", messages:[{kind:"error",
    segments:[{role:"warning", text:"조회할 수 있는 지도가 없습니다."}]}], sheets:[], centers:[], summary:""});
  mapState(c, "r2");
  assert.equal(last(), changed);
  assert.equal(c.byId("minimap-status").textContent, "조회할 수 있는 지도가 없습니다.");
  c.byId("minimap-center-form").fire("submit");
  assert.equal(last(), changed);
  c.byId("minimap-current").fire("click");
  assert.deepEqual(last(), {id:5});
  c.byId("minimap-refresh").fire("click");
  assert.deepEqual(last(), {id:6});
});

test("지도 시간 초과와 유효하지 않은 응답은 제출을 막고 현재 위치에서 복구", () => {
  const c = client();
  const last = () => mapFrames(c.socket).at(-1);
  const input = c.byId("minimap-center"), form = c.byId("minimap-center-form");
  const button = c.byId("minimap-center-submit");
  mapState(c, "r1");
  input.value = "중앙 복도";
  [...c.timeouts.values()].find(timer => timer.ms === 10000).fn();
  mapReply(c, "r1", last(), "시간 초과 후 응답");
  form.fire("submit");
  assert.deepEqual(mapFrames(c.socket), [{id:1}]);
  assert.equal(button.disabled, true);
  c.byId("minimap-current").fire("click");
  c.receive("pz_map", {id:last().id, revision:"r1", owner:"explorer-a", sheet:"",
    sheets:[], centers:[], messages:[{kind:"map", segments:[]}]});
  assert.equal(button.disabled, true);
  form.fire("submit");
  assert.deepEqual(mapFrames(c.socket), [{id:1}, {id:2}]);
  c.byId("minimap-refresh").fire("click");
  mapReply(c, "r1", last(), "복구된 지도");
  assert.equal(button.disabled, false);
  assert.equal(input.value, "중앙 복도");
  form.fire("submit");
  assert.deepEqual(last(), {id:4, sheet:"본부", center:"중앙 복도"});
});

test("실패한 중심 조회를 새로고침하면 명시적으로 선택한 지도만 다시 조회", () => {
  const c = client();
  const last = () => mapFrames(c.socket).at(-1);
  mapState(c, "r1");
  mapReply(c, "r1", last(), "본부");
  c.byId("minimap-sheet").value = "전초구역";
  c.byId("minimap-sheet").fire("change");
  mapReply(c, "r1", last(), "전초구역", "전초구역");
  c.byId("minimap-center").value = "잘못된 중심";
  c.byId("minimap-center-form").fire("submit");
  assert.deepEqual(last(), {id:3, sheet:"전초구역", center:"잘못된 중심"});
  c.receive("pz_map", {id:3, revision:"r1", owner:"explorer-a", sheet:"", sheets:[], centers:[],
    messages:[{kind:"error", segments:[{role:"warning",text:"조회할 수 있는 지도가 없습니다."}]}]});
  assert.equal(c.byId("minimap-center-submit").disabled, true);
  c.byId("minimap-refresh").fire("click");
  assert.deepEqual(last(), {id:4, sheet:"전초구역"});
  mapReply(c, "r1", last(), "복구된 전초구역", "전초구역");
  assert.equal(c.byId("minimap-center-submit").disabled, false);
});

test("미니맵 닫기·제어 해제·다른 캐릭터·재접속에서 지난 요청과 선택을 폐기", () => {
  const c = client();
  const panel = c.byId("minimap-panel"), output = c.byId("minimap-content");
  mapState(c, "r1");
  const first = mapFrames(c.socket).at(-1);
  panel.open = false; panel.fire("toggle");
  assert.deepEqual(mapFrames(c.socket).at(-1), {subscribe:false});
  mapReply(c, "r1", first, "이미 닫은 지도");
  mapState(c, "r2");
  c.byId("minimap-center").value = "닫힌 지도 제출";
  c.byId("minimap-center-form").fire("submit");
  assert.equal(output.textContent, "");
  assert.equal(mapFrames(c.socket).length, 2);
  panel.open = true; panel.fire("toggle");
  const reopened = mapFrames(c.socket).at(-1);
  assert.deepEqual(reopened, {id:2});
  mapReply(c, "r2", reopened, "기존 캐릭터 지도");
  c.byId("minimap-sheet").value = "전초구역";
  c.byId("minimap-sheet").fire("change");
  const previousOwner = mapFrames(c.socket).at(-1);
  c.receive("pz_map_reset", {});
  c.receive("pz_map_state", {revision:"r3", owner:"explorer-a"});
  assert.equal(panel.hidden, true);
  assert.equal(output.textContent, "");
  mapState(c, "r3", "explorer-b");
  const secondOwner = mapFrames(c.socket).at(-1);
  assert.deepEqual(secondOwner, {id:4});
  mapReply(c, "r3", previousOwner, "이전 캐릭터의 늦은 응답");
  assert.equal(output.textContent, "");
  c.byId("minimap-center").value = "새 캐릭터의 입력";
  c.byId("minimap-center-form").fire("submit");
  assert.equal(mapFrames(c.socket).at(-1), secondOwner);
  mapReply(c, "r3", secondOwner, "새 캐릭터 지도");
  const oldSocket = c.socket;
  oldSocket.readyState = 3; oldSocket.fire("close");
  assert.equal(panel.hidden, true);
  c.byId("reconnect").fire("click");
  const newSocket = c.socket;
  assert.notEqual(oldSocket, newSocket);
  oldSocket.fire("message", {data:JSON.stringify(["pz_state", [
    partyState(null,{minimap_revision:"late", minimap_owner:"explorer-b"}),
  ], {}])});
  assert.equal(panel.hidden, true);
  assert.deepEqual(mapFrames(newSocket), []);
  mapState(c,"r4","explorer-c");
  assert.deepEqual(mapFrames(newSocket), [{id:5}]);
});

test("지도 중심 입력의 한글 조합 Enter는 제출과 분리", () => {
  const c = client();
  mapState(c, "r1");
  mapReply(c, "r1", mapFrames(c.socket)[0], "본부 지도");
  c.byId("minimap-center").value = "중앙 복도";
  let blocked = 0;
  const event = {key:"Enter", preventDefault() { blocked++; }};
  c.byId("minimap-center").fire("keydown", {...event,isComposing:true});
  c.byId("minimap-center").fire("keydown", {...event,keyCode:229});
  c.byId("minimap-center").fire("keydown", event);
  assert.equal(blocked, 2);
  assert.equal(mapFrames(c.socket).length, 1);
  c.byId("minimap-center-form").fire("submit");
  assert.deepEqual(mapFrames(c.socket).at(-1), {id:2, sheet:"본부", center:"중앙 복도"});
});
