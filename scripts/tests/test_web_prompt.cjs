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
  setAttribute() {}
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
function client() {
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
    document, WebSocket:Socket, location:{}, setInterval:(fn, ms) => intervals.push({fn,ms}),
    setTimeout:() => 1, clearTimeout:() => {},
  });
  const receive = (kind, payload) => socket.fire("message", {data:JSON.stringify([kind,[payload],{}])});
  const state = segments => receive("pz_state", {
    resource_prompt:{kind:"prompt",segments}, currency:{formatted:"20칩",name:"보급칩"},
    exits:[], enemies:[], corpses:[], ground_loot:[], interactables:[], inventory:[],
    growth:{attributes:[],skills:[],attribute_points:0,skill_points:0},
  });
  const prompt = segments => receive("pz_log", {kind:"prompt",segments});
  const event = text => receive("pz_log", {kind:"event",segments:[{role:"text",text}]});
  const submit = text => { byId("command").value = text; byId("command-form").fire("submit"); };
  const click = command => document.fire("click", {target:{closest:() => ({dataset:{command}})}});
  const arrow = key => { byId("command").fire("keydown", {key}); return byId("command").value; };
  state(full); prompt(full);
  return {byId, log:byId("log"), socket, state, prompt, event, submit, click, arrow, intervals};
}

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
