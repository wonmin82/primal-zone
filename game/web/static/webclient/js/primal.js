"use strict";
(() => {
  const byId = (id) => document.getElementById(id);
  const log = byId("log"), dialog = byId("auth-dialog"), input = byId("command");
  let socket, playing = false, history = [], historyIndex = 0, authTimer, growthKey = "", exitsKey = "";
  let latestPrompt = [];
  function append(text, kind = "", segments = null) {
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 70;
    const entry = document.createElement("article");
    entry.className = "log-entry " + kind;
    if (kind === "prompt") entry.dataset.awaitingInput = "true";
    if (segments) {
      const roles = new Set(["text", "muted", "title", "hostile", "npc", "player", "object", "remains", "item", "command", "direction", "reward", "warning", "success", "error", "critical", "dialogue_topic", "dialogue_action"]);
      for (const part of segments) {
        if (!part || typeof part.text !== "string") continue;
        const selectable = ["dialogue_topic", "dialogue_action"].includes(part.role) &&
          typeof part.dialogue_selection === "string" && part.dialogue_selection.length <= 128;
        const span = document.createElement(selectable ? "button" : "span");
        if (selectable) {
          span.type = "button";
          span.dataset.dialogueSelection = part.dialogue_selection;
          span.setAttribute("aria-label", (part.role === "dialogue_action" ? "NPC 행동 실행: " : "NPC 화제 질문: ") + part.text);
        }
        span.textContent = part.text;
        if (roles.has(part.role)) span.className = "semantic-" + part.role;
        entry.append(span);
      }
    } else entry.textContent = text;
    log.append(entry);
    while (log.children.length > 400) log.firstElementChild.remove();
    if (nearBottom) log.scrollTop = log.scrollHeight;
    else byId("latest").hidden = false;
    return entry;
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
    if (!send("text", [text]) || !text.trim() || text === "idle") return;
    // 과거 prompt를 검색하지 않는다. 비동기 출력 뒤에는 최신 서버 값으로 새 행을 만든다.
    let entry = log.lastElementChild;
    if (!entry?.classList.contains("prompt") || entry.dataset.awaitingInput !== "true") {
      entry = append("", "prompt", latestPrompt);
    }
    entry.append(semantic("text", " "), semantic("command", text));
    entry.dataset.awaitingInput = "false";
    history.push(text); history = history.slice(-100); historyIndex = history.length;
    log.scrollTop = log.scrollHeight;
    byId("latest").hidden = true;
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

    grid.append(center);
    const positions = new Map([
      ["북", "north"], ["북동", "northeast"], ["동", "east"], ["남동", "southeast"],
      ["남", "south"], ["남서", "southwest"], ["서", "west"], ["북서", "northwest"],
    ]);
    const other = document.createElement("div");
    other.className = "other-exits";
    const vertical = exits.filter((exit) => exit.exists && ["위", "아래"].includes(exit.name));
    const up = vertical.some((exit) => exit.name === "위"), down = vertical.some((exit) => exit.name === "아래");
    center.replaceChildren(semantic(vertical.length ? (vertical.every((exit) => exit.can_move) ? "direction" : "warning") : "object", up && down ? "X" : up ? "^" : down ? "v" : "o"));
    for (const exit of exits) {
      const direction = exit.name, el = button(direction, direction), position = positions.get(direction);
      el.replaceChildren(semantic(exit.can_move ? "direction" : "warning", direction));
      el.disabled = !exit.can_move;
      el.title = `${exit.destination_name} · ${exit.status}${exit.reason ? " · " + exit.reason : ""}`;
      el.setAttribute("aria-label", `${direction} · ${exit.status}`);
      if (position) {
        el.className = "direction-" + position;
        grid.append(el);
      } else other.append(el);
    }
    const children = [grid];
    if (other.childElementCount) {
      const label = document.createElement("p");
      label.textContent = "출구";
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
    const nextKey = JSON.stringify([state.growth, state.training_controls]);
    if (nextKey === growthKey) return;
    growthKey = nextKey;
    const growth = state.growth, controls = state.training_controls || {};
    byId("training-location").textContent = state.training_available ? "주변 담당 교관에게 훈련 가능" : "담당 교관이 있는 안전한 곳에서 비전투 상태로 훈련하세요.";
    byId("attribute-points").textContent = "· 남은 포인트 " + growth.attribute_points;
    byId("skill-points").textContent = "· 남은 훈련 " + growth.skill_points;
    byId("attributes").replaceChildren(...growth.attributes.map((attribute) => {
      const row = document.createElement("div"), text = document.createElement("span");
      row.className = "growth-row";
      text.textContent = attribute.name + " " + attribute.value + " (기본 " + attribute.base + " + " + attribute.allocated + ")";
      text.title = attribute.description;
      const action = controls[attribute.id]?.[0];
      const add = button("+1", action?.command || "");
      add.setAttribute("aria-label", attribute.name + " 1 포인트 배분");
      add.disabled = !action;
      row.append(text, add); return row;
    }));
    byId("skills").replaceChildren(...growth.skills.map((skill) => {
      const row = document.createElement("div"), title = document.createElement("p"), detail = document.createElement("p");
      row.className = "skill-row";
      title.textContent = skill.name + " Rank " + skill.rank + "/" + skill.max_rank;
      detail.className = "muted";
      detail.textContent = skill.description + (skill.rank === skill.max_rank ? " · 최고 Rank" : " · 다음 Rank: 훈련 1회");
      const action = controls[skill.id]?.[0];
      const learn = button(skill.name + " 배워", action?.command || "");
      learn.disabled = !action;
      row.append(title, detail, learn); return row;
    }));
    ["reset-attributes", "reset-skills", "reset-all"].forEach((id, index) => { const action = controls.reset?.[index]; byId(id).disabled = !action; byId(id).dataset.command = action?.command || ""; });
  }
  function render(state) {
    if (Array.isArray(state.resource_prompt?.segments)) latestPrompt = state.resource_prompt.segments;
    playing = true;
    authBusy(false);
    if (dialog.open) dialog.close();
    input.disabled = false;
    byId("send-command").disabled = false;
    byId("logout").hidden = false;
    const fields = {"player-name": state.name, level: "Lv. " + state.level,
      credits: state.currency.formatted, "inventory-balance": state.currency.name + " " + state.currency.formatted, "hp-label": state.hp + " / " + state.max_hp,
      "xp-label": state.level >= state.max_level ? "최고 레벨" : (state.xp - state.xp_floor) + " / " + (state.xp_next - state.xp_floor),
      attack: state.attack, defense: state.defense, "room-name": state.room,
      "zone-tag": state.safe ? "안전 지대" : "탐사 구역", quest: state.quest, "room-hint": state.hint};
    Object.entries(fields).forEach(([key, value]) => { byId(key).textContent = value; });
    byId("resources").textContent = "자원 · " + Object.values(state.resources || {}).map((resource) => resource.name + " ×" + resource.count).join(" · ");
    const environment = state.environment;
    byId("environment-status").textContent = environment
      ? environment.time + " · " + environment.weather.name + " · " + environment.period.name + " · " + environment.light.name
      : "";
    const observation = state.observation;
    if (observation) byId("environment-status").textContent += " · 현재 시야 " + observation.effective_visibility.name + (observation.light_source?.active ? " · 손전등 켜짐" : "");
    byId("hp").max = state.max_hp; byId("hp").value = state.hp;
    byId("mental-label").textContent = state.mental + " / " + state.max_mental;
    byId("mental").max = state.max_mental; byId("mental").value = state.mental;
    byId("xp").max = state.xp_next - state.xp_floor;
    byId("xp").value = state.level >= state.max_level ? byId("xp").max : state.xp - state.xp_floor;
    renderExits(state.exit_details);
    const actions = state.enemies.map((enemy) => {
      const el = button(enemy.label + " " + enemy.hp + "/" + enemy.max_hp + (enemy.can_attack ? " 사냥" : " · 다른 그룹 교전 중"), enemy.attack_command);
      el.replaceChildren(semantic("hostile", enemy.label), " " + enemy.hp + "/" + enemy.max_hp + (enemy.can_attack ? " 사냥" : " · 다른 그룹 교전 중"));
      el.disabled = !enemy.can_attack;
      return el;
    });
    if (state.corpses.length > 1) {
      const all = button("모든 시체의 전리품 회수", "모든 시체에서 모두 가져");
      all.disabled = !state.corpses.some((source) => source.loot.some((item) => item.can_take));
      actions.push(all);
    }
    for (const corpse of state.corpses) {
      const title = document.createElement("p"); title.className = "loot-label";
      title.replaceChildren(semantic("remains", corpse.label), " · ", semantic("remains", corpse.name));
      actions.push(title);
      actions.push(button(corpse.label + " 봐", corpse.look_command));
      if (corpse.loot.length) {
        const all = button(corpse.label + " 전리품 회수", corpse.take_command);
        all.disabled = !corpse.loot.some((item) => item.can_take); actions.push(all);
      } else { const empty = document.createElement("small"); empty.textContent = corpse.loot_obscured ? "전리품을 식별하기 어려움" : "남은 전리품 없음"; actions.push(empty); }
      for (const item of corpse.loot) {
        const el = button(item.display_label + " → " + (item.protected ? item.assigned_name : "자유 획득"), item.take_command);
        el.replaceChildren(semantic(item.kind === "currency" ? "reward" : "item", item.display_label), " → ", semantic(item.protected ? "player" : "muted", item.protected ? item.assigned_name : "자유 획득"));
        el.disabled = !item.can_take; actions.push(el);
      }
    }
    if (state.ground_loot.length) {
      const all = button("바닥에서 모두 가져", "모두 가져");
      all.disabled = !state.ground_loot.some((source) => source.loot.some((item) => item.can_take));
      actions.push(all);
    }
    for (const source of state.ground_loot) for (const item of source.loot) {
      const el = button("바닥 · " + item.display_label + " → " + (item.protected ? item.assigned_name : "자유 획득"), item.take_command);
      el.replaceChildren("바닥 · ", semantic(item.kind === "currency" ? "reward" : "item", item.display_label), " → ", semantic(item.protected ? "player" : "muted", item.protected ? item.assigned_name : "자유 획득"));
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
    for (const object of state.interactables) for (const action of object.actions) {
      const el = button(object.label + " " + action.label, action.command);
      el.replaceChildren(semantic(object.role, object.label), " ", semantic("command", action.label));
      actions.push(el);
    }
    byId("context-actions").replaceChildren(...actions);
    const rows = state.inventory.map((item) => {
      const row = document.createElement("li"), name = document.createElement("span");
      if (item.light_source || item.power_source) row.classList.add("lighting-item");
      if (item.firearm || item.magazine) row.classList.add("stateful-item");
      const selector = item.selector || item.name;
      name.append(semantic("item", selector), " ×" + item.count);
      if (item.state_summary) name.append(" · " + item.state_summary);
      if (item.location === "inside") name.append(" [장전]");
      row.append(name);
      if (item.equipped) {
        const mark = document.createElement("small"); mark.textContent = item.active_weapon ? "주무기" : "착용 중"; row.append(mark);
        if (item.weapon) row.append(button("주무기", selector + " 주무기"));
        if (item.remove_action) row.append(button(item.remove_action, selector + " " + item.remove_action));
      } else if (item.equip_action) row.append(button(item.equip_action, selector + " " + item.equip_action));
      else if (item.consume_action) row.append(button(item.consume_action, item.name + " " + item.consume_action));
      else if (item.id === "bandage") row.append(button("사용", "붕대 사용"));
      if (item.information_command) row.append(button("정보", item.information_command));
      if (item.light_source) {
        const active = observation?.light_source?.name === selector && observation.light_source.active;
        row.append(button(active ? "끄기" : "켜기", selector + (active ? " 꺼" : " 켜")), button("확인", selector + " 확인"));
      }
      if (item.power_source) {
        for (const source of state.inventory.filter((device) => device.light_source?.power_type === item.power_source.type)) {
          const deviceSelector = source.selector || source.name;
          row.append(button(deviceSelector + "에 넣기", deviceSelector + "에 " + selector + " 넣어"));
        }
      }
      if (item.firearm) row.append(button("재장전", selector + " 재장전"), button("탄창 꺼내기", selector + "에서 탄창 꺼내"));
      if (item.magazine) row.append(button("채우기", selector + " 채워"), button("잔탄 꺼내기", selector + "에서 " + item.ammo_name + " 꺼내"));
      return row;
    });
    const emptySlots = Object.entries(state.equipment || {}).filter(([, name]) => !name);
    if (emptySlots.length) {
      const empty = document.createElement("li");
      empty.textContent = emptySlots.map(([slot]) => (state.equipment_labels?.[slot] || slot) + " 없음").join(" · ");
      rows.unshift(empty);
    }
    byId("inventory").replaceChildren(...rows);
    const encounter = state.combat_target;
    byId("encounter").hidden = !encounter;
    if (encounter) byId("encounter").replaceChildren(semantic("hostile", encounter.name), " · 공유 체력 " + encounter.hp + "/" + encounter.max_hp + " · 적 " + encounter.round + "차례" + (encounter.telegraph ? " · 다음 돌진! 견제와 치료를 준비하세요." : " · 강타 / 쏴 / 견제 / 치료"));
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
      if (kind === "text") {
        const text = plainText(args?.[0] ?? "");
        if (text.trim()) append(text);
      } else if (kind === "pz_log" && Array.isArray(args?.[0]?.segments)) {
        const message = args[0];
        if (message.kind === "prompt") latestPrompt = message.segments;
        append("", ["sheet", "event", "error", "chat", "prompt"].includes(message.kind) ? message.kind : "", message.segments);
      } else if (kind === "pz_state" && args?.[0]) render(args[0]);
      else if (kind === "pz_auth") {
        authBusy(false);
        byId("auth-error").textContent = args?.[0]?.ok ? "" : (args?.[0]?.message || "접속에 실패했습니다.");
        if (args?.[0]?.ok) byId("password").value = "";
      }
    });
    socket.addEventListener("close", () => {
      playing = false; latestPrompt = []; authBusy(false);
      input.disabled = true; byId("send-command").disabled = true;
      byId("connection-label").textContent = "연결 끊김";
      byId("connection-dot").classList.remove("connected");
      byId("reconnect").hidden = false; byId("logout").hidden = true;
      append("연결이 종료되었습니다. 재연결 후 같은 계정으로 접속하면 저장된 탐사를 이어갑니다.", "event");
    });
    socket.addEventListener("error", () => { byId("auth-error").textContent = "서버에 연결할 수 없습니다. 서버 실행 상태를 확인하세요."; });
  }
  document.addEventListener("click", (event) => {
    const selection = event.target.closest("[data-dialogue-selection]");
    if (selection?.dataset.dialogueSelection) {
      if (playing) send("pz_dialogue", [selection.dataset.dialogueSelection]);
      return;
    }
    const target = event.target.closest("[data-command]");
    if (target) command(target.dataset.command);
  });
  document.addEventListener("keydown", (event) => {
    if (event.isComposing || !["Enter", " "].includes(event.key)) return;
    const selection = event.target.closest("[data-dialogue-selection]");
    if (!selection?.dataset.dialogueSelection) return;
    event.preventDefault(); // 기본 button click과 중복 요청을 생성하지 않는다.
    if (playing) send("pz_dialogue", [selection.dataset.dialogueSelection]);
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
    if (!playing) return;
    if (!text) { command(""); input.value = ""; input.focus(); return; }
    // Credentials belong in the password form, never in the visible log/history.
    const chat = text.startsWith("'") || /(?:^|\s)(말|say)$/i.test(text);
    if (!chat && /^(connect|create|접속|가입)\s/i.test(text)) { append("계정 접속은 전용 접속창을 사용하세요.", "event"); input.value = ""; return; }
    command(text); input.value = ""; input.focus();
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
