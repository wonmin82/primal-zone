"use strict";
(() => {
  const byId = (id) => document.getElementById(id);
  const log = byId("log"), dialog = byId("auth-dialog"), input = byId("command");
  let socket, playing = false, history = [], historyIndex = 0, authTimer, growthKey = "", exitsKey = "";
  function append(text, kind = "", segments = null) {
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 70;
    const entry = document.createElement("article");
    entry.className = "log-entry " + kind;
    if (segments) {
      const roles = new Set(["text", "muted", "title", "hostile", "npc", "player", "object", "remains", "item", "command", "direction", "reward", "warning", "success", "error"]);
      for (const part of segments) {
        if (!part || typeof part.text !== "string") continue;
        const span = document.createElement("span");
        span.textContent = part.text;
        if (roles.has(part.role)) span.className = "semantic-" + part.role;
        entry.append(span);
      }
    } else entry.textContent = text;
    log.append(entry);
    while (log.children.length > 400) log.firstElementChild.remove();
    if (nearBottom || kind === "command") log.scrollTop = log.scrollHeight;
    else byId("latest").hidden = false;
  }
  function plainText(html) {
    // Inert template content is never inserted into the live document.
    const template = document.createElement("template");
    template.innerHTML = String(html).replace(/<br\s*\/?\s*>/gi, "\n");
    return template.content.textContent;
  }
  function send(name, args) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify([name, args, {}]));
    return true;
  }
  function command(text) {
    if (!playing) { if (!dialog.open) dialog.showModal(); return; }
    if (send("text", [text])) append("› " + text, "command");
  }
  function semantic(role, text) {
    const span = document.createElement("span");
    span.className = "semantic-" + role;
    span.textContent = text;
    return span;
  }
  function button(label, cmd) {
    const el = document.createElement("button");
    el.textContent = label;
    el.dataset.command = cmd;
    return el;
  }
  function renderExits(exits) {
    const key = JSON.stringify(exits);
    if (key === exitsKey) return;
    exitsKey = key;
    const grid = document.createElement("div"), center = document.createElement("span");
    grid.className = "direction-grid";
    center.className = "direction-center";
    center.textContent = "[현재]";
    grid.append(center);
    const positions = new Map([["북", "north"], ["남", "south"], ["동", "east"], ["서", "west"]]);
    const other = document.createElement("div");
    other.className = "other-exits";
    for (const direction of exits) {
      const el = button(direction, direction), position = positions.get(direction);
      el.replaceChildren(semantic("direction", direction));
      if (position) {
        grid.classList.add("has-" + position);
        el.className = "direction-" + position;
        const line = document.createElement("span");
        line.className = "direction-line line-" + position;
        line.setAttribute("aria-hidden", "true");
        grid.append(el, line);
      } else other.append(el);
    }
    const children = [grid];
    if (other.childElementCount) {
      const label = document.createElement("p");
      label.textContent = "기타 출구";
      children.push(label, other);
    }
    byId("exits").replaceChildren(...children);
  }
  function authBusy(busy) {
    byId("auth-form").querySelectorAll("button").forEach((el) => { el.disabled = busy; });
    clearTimeout(authTimer);
    if (busy) authTimer = setTimeout(() => {
      authBusy(false);
      byId("auth-error").textContent = "응답이 지연되고 있습니다. 연결 상태를 확인한 뒤 다시 시도하세요.";
    }, 15000);
  }
  function renderGrowth(state) {
    // Keep focused training controls stable during unchanged world lifecycle updates.
    const nextKey = JSON.stringify([state.growth, state.training_available]);
    if (nextKey === growthKey) return;
    growthKey = nextKey;
    const growth = state.growth, available = state.training_available;
    byId("training-location").textContent = available ? "탐사대 훈련관 · 훈련 가능" : "학습·배분·재훈련은 비전투 상태로 부두 교관에게서 이용하세요.";
    byId("attribute-points").textContent = "· 남은 포인트 " + growth.attribute_points;
    byId("skill-points").textContent = "· 남은 점수 " + growth.skill_points;
    byId("attributes").replaceChildren(...growth.attributes.map((attribute) => {
      const row = document.createElement("div"), text = document.createElement("span");
      row.className = "growth-row";
      text.textContent = attribute.name + " " + attribute.value + " (기본 " + attribute.base + " + " + attribute.allocated + ")";
      text.title = attribute.description;
      const add = button("+1", attribute.name + " 1 배분");
      add.setAttribute("aria-label", attribute.name + " 1 포인트 배분");
      add.disabled = !available || growth.attribute_points < 1;
      row.append(text, add); return row;
    }));
    byId("proficiencies").replaceChildren(...growth.proficiencies.map((proficiency) => {
      const row = document.createElement("p");
      row.textContent = proficiency.name + " Rank " + proficiency.rank + "/" + proficiency.max_rank + " · XP " + proficiency.xp;
      return row;
    }));
    byId("skills").replaceChildren(...growth.skills.map((skill) => {
      const row = document.createElement("div"), title = document.createElement("p"), detail = document.createElement("p");
      row.className = "skill-row";
      title.textContent = skill.name + " Rank " + skill.rank + "/" + skill.max_rank;
      detail.className = "muted";
      detail.textContent = skill.description + (skill.rank === skill.max_rank ? " · 최고 Rank" : " · 다음: Lv." + skill.required_level + " / " + skill.next_points + "점 / " + skill.next_credits + " 크레딧");
      const learn = button(skill.name + " 배워", skill.name + " 배워");
      learn.disabled = !available || !skill.can_learn;
      row.append(title, detail, learn); return row;
    }));
    ["reset-attributes", "reset-skills", "reset-all"].forEach((id) => { byId(id).disabled = !available; });
  }
  function render(state) {
    playing = true;
    authBusy(false);
    if (dialog.open) dialog.close();
    input.disabled = false;
    byId("send-command").disabled = false;
    byId("logout").hidden = false;
    const fields = {"player-name": state.name, level: "Lv. " + state.level,
      credits: state.credits + " 크레딧", "hp-label": state.hp + " / " + state.max_hp,
      "xp-label": state.level >= 10 ? "최고 레벨" : (state.xp - state.xp_floor) + " / " + (state.xp_next - state.xp_floor),
      attack: state.attack, defense: state.defense, "room-name": state.room,
      "zone-tag": state.safe ? "안전 지대" : "탐사 구역", quest: state.quest, "room-hint": state.hint};
    Object.entries(fields).forEach(([key, value]) => { byId(key).textContent = value; });
    byId("hp").max = state.max_hp; byId("hp").value = state.hp;
    byId("xp").max = state.xp_next - state.xp_floor;
    byId("xp").value = state.level >= 10 ? byId("xp").max : state.xp - state.xp_floor;
    renderExits(state.exits);
    const actions = state.enemies.map((enemy) => {
      const el = button(enemy.name + " " + enemy.hp + "/" + enemy.max_hp + (enemy.can_attack ? " 사냥" : " · 다른 그룹 교전 중"), enemy.name + " 사냥");
      el.replaceChildren(semantic("hostile", enemy.name), " " + enemy.hp + "/" + enemy.max_hp + (enemy.can_attack ? " 사냥" : " · 다른 그룹 교전 중"));
      el.disabled = !enemy.can_attack;
      return el;
    });
    for (const corpse of state.corpses) {
      const title = document.createElement("p"); title.className = "loot-label";
      title.replaceChildren(semantic("remains", corpse.name));
      actions.push(title);
      if (corpse.loot.length) {
        const all = button("시체에서 모두 가져", "시체에서 모두 가져");
        all.disabled = !corpse.loot.some((item) => item.can_take); actions.push(all);
      } else { const empty = document.createElement("small"); empty.textContent = "남은 전리품 없음"; actions.push(empty); }
      for (const item of corpse.loot) {
        const el = button(item.name + " ×" + item.quantity + " → " + (item.protected ? item.assigned_name : "자유 획득"), "시체에서 " + item.name + " 가져");
        el.replaceChildren(semantic("item", item.name), " ×" + item.quantity + " → ", semantic(item.protected ? "player" : "muted", item.protected ? item.assigned_name : "자유 획득"));
        el.disabled = !item.can_take; actions.push(el);
      }
    }
    if (state.ground_loot.length) {
      const all = button("바닥에서 모두 가져", "모두 가져");
      all.disabled = !state.ground_loot.some((source) => source.loot.some((item) => item.can_take));
      actions.push(all);
    }
    for (const source of state.ground_loot) for (const item of source.loot) {
      const el = button("바닥 · " + item.name + " ×" + item.quantity + " → " + (item.protected ? item.assigned_name : "자유 획득"), item.name + " 가져");
      el.replaceChildren("바닥 · ", semantic("item", item.name), " ×" + item.quantity + " → ", semantic(item.protected ? "player" : "muted", item.protected ? item.assigned_name : "자유 획득"));
      el.disabled = !item.can_take; actions.push(el);
    }
    renderGrowth(state);
    const party = state.party;
    byId("party-state").textContent = party ? "파티장: " + party.leader_name + (party.is_leader ? " (나)" : "") + " · 전리품: 순번 분배" : "소속 파티 없음";
    byId("party-members").replaceChildren(...(party?.members || []).map((member) => {
      const row = document.createElement("li"); row.append(semantic("player", member.name), member.id === party.leader ? " · 파티장" : ""); return row;
    }));
    byId("party-leave").hidden = !party;
    byId("party-invite-form").hidden = !!party && !party.is_leader;
    const invitation = state.invitation;
    byId("party-invitation").hidden = !invitation;
    byId("party-inviter").textContent = invitation ? invitation.inviter + "의 파티 초대 (60초 이내 수락)" : "";
    if (state.zone === "dock") actions.push(button("윤대장과 대화", "윤대장 대화"), button("훈련관과 대화", "탐사대 훈련관 대화"), button("의무실에서 휴식", "휴식"), button("보급소 보기", "상점"));
    if (state.zone === "wreck") actions.push(button("보급상자 조사", "보급상자 조사"));
    if (state.zone === "office") actions.push(button("정비기록 조사", "정비기록 조사"));
    if (state.zone === "generator") actions.push(button("발전기 수리", "발전기 수리"));
    byId("context-actions").replaceChildren(...actions);
    const rows = state.inventory.map((item) => {
      const row = document.createElement("li"), name = document.createElement("span");
      name.append(semantic("item", item.name), " ×" + item.count);
      row.append(name);
      if (item.equipped) {
        const mark = document.createElement("small"); mark.textContent = "착용 중"; row.append(mark);
      } else if (["weapon", "armor"].includes(item.slot)) row.append(button("착용", item.name + " 착용"));
      else if (item.id === "bandage") row.append(button("사용", "회복"));
      return row;
    });
    byId("inventory").replaceChildren(...rows);
    const encounter = state.combat_target;
    byId("encounter").hidden = !encounter;
    if (encounter) byId("encounter").replaceChildren(semantic("hostile", encounter.name), " · 공유 체력 " + encounter.hp + "/" + encounter.max_hp + " · 적 " + encounter.round + "차례" + (encounter.telegraph ? " · 다음 돌진! 방어를 준비하세요." : " · 강타 / 방어 / 회복"));
  }
  function connect() {
    if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
    byId("connection-label").textContent = "연결 중";
    byId("reconnect").hidden = true;
    const configured = document.body.dataset.wsUrl;
    const url = configured || ((location.protocol === "https:" ? "wss://" : "ws://") + location.hostname + ":" + document.body.dataset.wsPort);
    socket = new WebSocket(url, "v1.evennia.com");
    socket.addEventListener("open", () => {
      byId("connection-label").textContent = "연결됨";
      byId("connection-dot").classList.add("connected");
      byId("auth-error").textContent = "";
      if (!playing && !dialog.open) dialog.showModal();
    });
    socket.addEventListener("message", (event) => {
      let frame;
      try { frame = JSON.parse(event.data); } catch { return; }
      if (!Array.isArray(frame)) return;
      const [kind, args] = frame;
      if (kind === "text" || kind === "prompt") {
        const text = plainText(args?.[0] ?? "");
        if (text.trim()) append(text);
      } else if (kind === "pz_log" && Array.isArray(args?.[0]?.segments)) {
        const message = args[0];
        append("", ["sheet", "event", "error", "chat"].includes(message.kind) ? message.kind : "", message.segments);
      } else if (kind === "pz_state" && args?.[0]) render(args[0]);
      else if (kind === "pz_auth") {
        authBusy(false);
        byId("auth-error").textContent = args?.[0]?.ok ? "" : (args?.[0]?.message || "접속에 실패했습니다.");
        if (args?.[0]?.ok) byId("password").value = "";
      }
    });
    socket.addEventListener("close", () => {
      playing = false; authBusy(false);
      input.disabled = true; byId("send-command").disabled = true;
      byId("connection-label").textContent = "연결 끊김";
      byId("connection-dot").classList.remove("connected");
      byId("reconnect").hidden = false; byId("logout").hidden = true;
      append("연결이 종료되었습니다. 재연결 후 같은 계정으로 접속하면 저장된 탐사를 이어갑니다.", "event");
    });
    socket.addEventListener("error", () => { byId("auth-error").textContent = "서버에 연결할 수 없습니다. 서버 실행 상태를 확인하세요."; });
  }
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-command]");
    if (target) command(target.dataset.command);
  });
  byId("auth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    byId("auth-error").textContent = "";
    const sent = send("pz_auth", [{mode: event.submitter?.value || "login", username: byId("username").value, password: byId("password").value}]);
    if (sent) authBusy(true);
    else { byId("auth-error").textContent = "연결이 끊겨 있습니다. 재연결 중입니다."; connect(); }
  });
  byId("party-invite-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const name = byId("party-target").value.trim();
    if (name) command(name + " 파티초대");
  });
  dialog.addEventListener("cancel", (event) => event.preventDefault());
  byId("command-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || !playing) return;
    // Credentials belong in the password form, never in the visible log/history.
    const chat = text.startsWith("'") || /(?:^|\s)(말|say)$/i.test(text);
    if (!chat && /^(connect|create|접속|가입)\s/i.test(text)) { append("계정 접속은 전용 접속창을 사용하세요.", "event"); input.value = ""; return; }
    command(text); history.push(text); history = history.slice(-100);
    historyIndex = history.length; input.value = ""; input.focus();
  });
  input.addEventListener("keydown", (event) => {
    if (event.isComposing || event.keyCode === 229) { if (event.key === "Enter") event.preventDefault(); return; }
    if (event.key === "ArrowUp" && historyIndex > 0) { event.preventDefault(); input.value = history[--historyIndex]; }
    if (event.key === "ArrowDown") { event.preventDefault(); historyIndex = Math.min(history.length, historyIndex + 1); input.value = history[historyIndex] || ""; }
  });
  byId("latest").addEventListener("click", () => { log.scrollTop = log.scrollHeight; byId("latest").hidden = true; });
  byId("reconnect").addEventListener("click", connect);
  setInterval(() => { if (playing) send("text", ["idle"]); }, 60000);
  connect();
})();
