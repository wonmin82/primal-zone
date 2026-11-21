"use strict";
(() => {
  const byId = (id) => document.getElementById(id);
  const log = byId("log"), dialog = byId("auth-dialog"), input = byId("command");
  let socket, playing = false, history = [], historyIndex = 0, authTimer, growthKey = "", exitsKey = "";
  let latestPrompt = [];
  const semanticRoles = new Set([
    "text", "muted", "title", "hostile", "npc", "player", "object", "remains", "item", "command",
    "direction", "reward", "warning", "success", "error", "critical", "dialogue_topic", "dialogue_action",
    "combat_verb_outgoing", "damage_dealt", "combat_verb_incoming", "damage_taken",
    "hp_recovered", "mental_recovered", "status_buff", "status_debuff",
  ]);
  function appendSegments(entry, segments, allowDialogue = false) {
    for (const part of segments) {
      if (!part || typeof part.text !== "string") continue;
      const selectable = allowDialogue && ["dialogue_topic", "dialogue_action"].includes(part.role) &&
        typeof part.dialogue_selection === "string" && part.dialogue_selection.length <= 128;
      const span = document.createElement(selectable ? "button" : "span");
      if (selectable) {
        span.type = "button";
        span.dataset.dialogueSelection = part.dialogue_selection;
        span.setAttribute("aria-label", (part.role === "dialogue_action" ? "NPC 행동 실행: " : "NPC 화제 질문: ") + part.text);
      }
      span.textContent = part.text;
      if (semanticRoles.has(part.role)) span.className = "semantic-" + part.role;
      entry.append(span);
    }
  }
  function append(text, kind = "", segments = null) {
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 70;
    const entry = document.createElement("article");
    entry.className = "log-entry " + kind;
    if (kind === "prompt") entry.dataset.awaitingInput = "true";
    if (segments) appendSegments(entry, segments, true);
    else entry.textContent = text;
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
  const minimapPanel = byId("minimap-panel"), minimapSheet = byId("minimap-sheet");
  const minimapCenter = byId("minimap-center"), minimapCenters = byId("minimap-centers");
  const minimapOutput = byId("minimap-output"), minimapStatus = byId("minimap-status");
  const minimapDescription = byId("minimap-description");
  let minimapRevision = "", minimapOwner = "", minimapSequence = 0;
  let minimapSelection = {}, minimapPending = null, minimapDisplayed = "", minimapTimer;

  function setMinimapSheets(names) {
    const first = document.createElement("option");
    first.value = ""; first.textContent = "현재 위치 지도";
    const options = names.filter(name => typeof name === "string" && name).map(name => {
      const option = document.createElement("option");
      option.value = name; option.textContent = name;
      return option;
    });
    minimapSheet.replaceChildren(first, ...options);
    minimapSheet.value = names.includes(minimapSelection.sheet) ? minimapSelection.sheet : "";
  }
  function clearMinimap({choices = false} = {}) {
    clearTimeout(minimapTimer);
    minimapPending = null;
    minimapDisplayed = "";
    minimapOutput.replaceChildren(); minimapOutput.hidden = true;
    minimapOutput.setAttribute("aria-busy", "false");
    minimapStatus.textContent = ""; minimapDescription.textContent = "";
    if (choices) {
      setMinimapSheets([]);
      minimapCenters.replaceChildren();
      minimapCenter.value = "";
    }
  }
  function resetMinimap() {
    minimapOwner = minimapRevision = "";
    minimapSelection = {};
    clearMinimap({choices:true});
    minimapPanel.hidden = true; minimapPanel.open = true;
  }
  function requestMinimap(force = false) {
    if (!playing || !minimapRevision || !minimapPanel.open || minimapPanel.hidden) return;
    const key = JSON.stringify([minimapRevision, minimapSelection]);
    if (!force && (minimapPending?.key === key || minimapDisplayed === key)) return;
    clearMinimap();
    const id = ++minimapSequence;
    if (!send("pz_map", [{id, ...minimapSelection}])) {
      minimapStatus.textContent = "연결 후 지도를 다시 확인하세요.";
      return;
    }
    minimapPending = {id, key};
    minimapOutput.setAttribute("aria-busy", "true");
    minimapStatus.textContent = "지도를 불러오는 중입니다.";
    minimapTimer = setTimeout(() => {
      if (minimapPending?.id !== id) return;
      clearMinimap();
      minimapStatus.textContent = "지도 응답이 지연되었습니다. 새로고침하세요.";
    }, 10000);
  }
  function syncMinimap(revision, owner) {
    if (typeof revision !== "string" || !revision || typeof owner !== "string" || !owner) {
      resetMinimap();
      return;
    }
    if (owner !== minimapOwner) resetMinimap();
    if (revision === minimapRevision) return;
    // 지난 권한으로 받은 텍스트와 선택 후보부터 숨긴다.
    clearMinimap({choices:true});
    minimapOwner = owner; minimapRevision = revision;
    minimapPanel.hidden = false;
    requestMinimap();
  }
  function renderMinimap(response) {
    if (!playing || minimapPanel.hidden || !minimapPanel.open ||
        !minimapPending || response?.id !== minimapPending.id || response.revision !== minimapRevision ||
        response.owner !== minimapOwner) return;
    if (!Array.isArray(response.messages) || !Array.isArray(response.sheets) || !Array.isArray(response.centers)) return;
    const key = minimapPending.key;
    clearMinimap();
    minimapDisplayed = key;
    setMinimapSheets(response.sheets);
    if (typeof response.sheet === "string" && response.sheets.includes(response.sheet) && (minimapSelection.sheet || minimapSelection.center)) {
      minimapSheet.value = response.sheet;
    }
    minimapCenters.replaceChildren(...response.centers.filter(name => typeof name === "string").map(name => {
      const option = document.createElement("option");
      option.value = name;
      return option;
    }));
    const elements = [];
    for (const message of response.messages) {
      if (!Array.isArray(message?.segments)) continue;
      const canvas = message.kind === "map";
      const row = document.createElement(canvas ? "div" : "p");
      row.className = canvas ? "minimap-map" : "minimap-message";
      if (canvas) {
        row.tabIndex = 0;
        row.setAttribute("role", "region");
        row.setAttribute("aria-label", "문자 지도, 방향키로 스크롤");
        row.setAttribute("aria-describedby", "minimap-description");
        const glyphs = document.createElement("div");
        glyphs.setAttribute("aria-hidden", "true");
        appendSegments(glyphs, message.segments);
        row.append(glyphs);
      } else appendSegments(row, message.segments);
      elements.push(row);
    }
    minimapOutput.replaceChildren(...elements);
    minimapOutput.hidden = !elements.length;
    minimapDescription.textContent = typeof response.summary === "string" ? response.summary : "";
    if (!elements.length) minimapStatus.textContent = "표시할 지도가 없습니다.";
  }
  minimapPanel.addEventListener("toggle", () => {
    if (minimapPanel.open) requestMinimap();
    else {
      if (minimapOwner && playing) send("pz_map", [{subscribe:false}]);
      minimapSelection = {};
      clearMinimap({choices:true});
    }
  });
  minimapSheet.addEventListener("change", () => {
    minimapSelection = minimapSheet.value ? {sheet:minimapSheet.value} : {};
    minimapCenter.value = ""; minimapCenters.replaceChildren();
    requestMinimap();
  });
  minimapCenter.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.isComposing || event.keyCode === 229)) event.preventDefault();
  });
  byId("minimap-center-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const center = minimapCenter.value.trim();
    if (!center || center.length > 120) return;
    minimapSelection = {...minimapSelection, center};
    requestMinimap();
  });
  byId("minimap-current").addEventListener("click", () => {
    if (!minimapSelection.sheet && !minimapSelection.center) return;
    minimapSelection = {};
    minimapSheet.value = ""; minimapCenter.value = ""; minimapCenters.replaceChildren();
    requestMinimap();
  });
  byId("minimap-refresh").addEventListener("click", () => requestMinimap(true));

  let actionSequence = 0;
  function actionButton(label, invocation) {
    const el = document.createElement("button");
    el.type = "button"; el.textContent = label;
    el.dataset.actionInvocation = JSON.stringify(invocation);
    return el;
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
      const add = action?.action ? actionButton("+1", action.action) : button("+1", action?.command || "");
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
      const learn = action?.action ? actionButton(skill.name + " 배워", action.action) : button(skill.name + " 배워", action?.command || "");
      learn.disabled = !action;
      row.append(title, detail, learn); return row;
    }));
    ["attributes", "skills", "all"].forEach((scope) => {
      const action = controls.reset?.find((control) => control.action?.arguments?.value === scope), el = byId("reset-" + scope);
      el.disabled = !action;
      delete el.dataset.command;
      delete el.dataset.actionInvocation;
      if (action?.action) el.dataset.actionInvocation = JSON.stringify(action.action);
      else if (action?.command) el.dataset.command = action.command;
    });
  }
  // 로컬 시계 차이와 추가 타이머 없이 서버가 관측한 수신 시점의 TTL을 표시한다.
  function pendingTime(entry, serverNow) {
    if (!Number.isFinite(entry?.expires_at) || !Number.isFinite(serverNow)) return {label:"남은 시간 재확인 필요", expired:false};
    const remaining = Math.max(0, Math.ceil(entry.expires_at - serverNow));
    return {label:remaining ? remaining + "초 남음 (수신 기준)" : "만료됨", expired:remaining === 0};
  }

  function duelControls(duels, serverNow) {
    const controls = [];
    const endings = {victory:"승리", defeat:"패배", surrender:"기권",
      timeout:"시간 초과", disconnect:"재접속 유예 만료", abort:"복구 불가"};
    for (const duel of duels) {
      const status = duel.status;
      if (status) {
        const text = document.createElement("p");
        text.className = "loot-label";
        if (status.state === "active") {
          const duelTime = pendingTime({expires_at:status.ends_at}, serverNow).label;
          text.textContent = duel.label + " · 대련 진행 중 · 최대 시간 " + duelTime;
          if (Number.isFinite(status.actor_hp)) text.textContent += " · 상대 HP " + status.actor_hp;
          if (status.participant) {
            if (Number.isFinite(status.player_hp)) text.textContent += " · 내 대련 HP " + status.player_hp;
            const idle = pendingTime({expires_at:status.idle_at}, serverNow).label;
            text.textContent += " · 명시 행동 기한 " + idle + " · 자동 공격은 명시 행동으로 세지 않습니다.";
            if (status.reconnect_until) {
              const reconnect = pendingTime({expires_at:status.reconnect_until}, serverNow).label;
              text.textContent += " · 재접속 유예 " + reconnect;
            }
          }
        } else {
          const result = status.final_result;
          const reason = result?.reason === "idle" ? "무행동 시간 초과" : endings[result?.kind];
          text.textContent = duel.label + " · 대련 종료" + (reason ? " · " + reason : "");
          if (status.cooldown_until > serverNow) {
            text.textContent += " · 재신청까지 " + pendingTime({expires_at:status.cooldown_until}, serverNow).label;
          }
        }
        controls.push(text);
      }
      if (duel.start_action) controls.push(actionButton(duel.label + " 대련", duel.start_action));
      for (const [label, action] of Object.entries(duel.actions)) controls.push(actionButton("대련 " + label, action));
      if (duel.surrender_action) controls.push(actionButton("대련 기권", duel.surrender_action));
    }
    return controls;
  }

  function render(state) {
    if (Array.isArray(state.resource_prompt?.segments)) latestPrompt = state.resource_prompt.segments;
    playing = true;
    syncMinimap(state.minimap_revision, state.minimap_owner);
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
      const el = actionButton(enemy.label + " " + enemy.hp + "/" + enemy.max_hp + (enemy.can_attack ? " 사냥" : " · 다른 그룹 교전 중"), enemy.attack_action);
      el.replaceChildren(semantic("hostile", enemy.label), " " + enemy.hp + "/" + enemy.max_hp + (enemy.can_attack ? " 사냥" : " · 다른 그룹 교전 중"));
      el.disabled = !enemy.can_attack;
      return el;
    });
    actions.push(...duelControls(state.duels || [], state.server_now));
    if (state.corpses.length > 1 && state.loot_actions?.corpses) {
      const all = actionButton("모든 시체의 전리품 회수", state.loot_actions.corpses);
      all.disabled = !state.corpses.some((source) => source.loot.some((item) => item.can_take));
      actions.push(all);
    }
    for (const corpse of state.corpses) {
      const title = document.createElement("p"); title.className = "loot-label";
      title.replaceChildren(semantic("remains", corpse.label), " · ", semantic("remains", corpse.name));
      actions.push(title);
      actions.push(button(corpse.label + " 봐", corpse.look_command));
      if (corpse.loot.length && corpse.take_action) {
        const all = actionButton(corpse.label + " 전리품 회수", corpse.take_action);
        all.disabled = !corpse.loot.some((item) => item.can_take); actions.push(all);
      } else if (!corpse.loot.some((item) => item.action)) { const empty = document.createElement("small"); empty.textContent = corpse.loot_obscured ? "전리품을 식별하기 어려움" : "회수 가능한 전리품 없음"; actions.push(empty); }
      for (const item of corpse.loot) {
        const el = actionButton(item.display_label + " → " + (item.protected ? item.assigned_name : "자유 획득"), item.action);
        el.replaceChildren(semantic(item.kind === "currency" ? "reward" : "item", item.display_label), " → ", semantic(item.protected ? "player" : "muted", item.protected ? item.assigned_name : "자유 획득"));
        el.disabled = !item.can_take || !item.action; actions.push(el);
      }
    }
    if (state.ground_loot.length && state.loot_actions?.ground) {
      const all = actionButton("바닥에서 모두 가져", state.loot_actions.ground);
      all.disabled = !state.ground_loot.some((source) => source.loot.some((item) => item.can_take));
      actions.push(all);
    }
    for (const source of state.ground_loot) for (const item of source.loot) {
      const el = actionButton("바닥 · " + item.display_label + " → " + (item.protected ? item.assigned_name : "자유 획득"), item.action);
      el.replaceChildren("바닥 · ", semantic(item.kind === "currency" ? "reward" : "item", item.display_label), " → ", semantic(item.protected ? "player" : "muted", item.protected ? item.assigned_name : "자유 획득"));
      el.disabled = !item.can_take || !item.action; actions.push(el);
    }
    renderGrowth(state);
    const party = state.party;
    byId("party-state").textContent = party ? "일행 #" + party.id + " · 리더: " + party.leader_name + (party.is_leader ? " (나)" : "") + " · " + (party.leader_online ? "온라인" : party.can_succeed ? "오프라인 · 승계 가능" : "오프라인 · 승계 불가") + " · 전리품: 순번 분배" : "소속 일행 없음";
    byId("party-members").replaceChildren(...(party?.members || []).map((member) => {
      const row = document.createElement("li"); row.append(semantic("player", member.name), member.id === party.leader ? " · 리더" : "", member.online ? " · 온라인" : " · 오프라인");
      if (party.is_leader) {
        if (member.id !== party.leader) row.append(button("리더 위임", (member.label || member.name) + " 일행리더"), button("제외", (member.label || member.name) + " 일행제외"));
        row.append(button("방어 담당", (member.label || member.name) + " 일행방어"));
      }
      return row;
    }));
    const defender = party?.defender;
    byId("party-tactics").textContent = party ? "구성원 " + party.members.length + "/" + (party.max_size || 4) + " · 방어 담당: " + (defender ? defender.name + (defender.online ? " (온라인)" : " (오프라인)") + (defender.active ? " · 효과 활성" : " · 효과 비활성 (지정 유지)") : "없음") : "";
    byId("party-pending").replaceChildren(...(party?.join_requests || []).map((request) => {
      const status = pendingTime(request, state.server_now);
      const row = document.createElement("li"); row.append(semantic("player", request.name), " · 가입 요청 · " + status.label);
      if (party.is_leader && !status.expired) row.append(button("허락", request.label + " 일행허락"), button("거절", request.label + " 일행거절"));
      return row;
    }), ...(party?.invitations || []).map((invite) => {
      const row = document.createElement("li"); row.textContent = invite.name + " · 초청 대기 · " + pendingTime(invite, state.server_now).label; return row;
    }));
    byId("party-outgoing").textContent = state.join_request ? "가입 요청: 일행 #" + state.join_request.party_id + " · " + pendingTime(state.join_request, state.server_now).label : "";
    const partyActions = [button("일행 조회", "일행")];
    if (!party) partyActions.push(button("일행 만들기", "일행모으기"));
    else {
      partyActions.push(button("탈퇴", "일행탈퇴"), button("방어 조회", "일행방어"));
      if (party.can_succeed) partyActions.push(button("오프라인 리더 즉시 승계", "일행승계"));
      if (party.is_leader) {
        partyActions.push(button("현재 적 공동 공격", "일행공격"), button("방어 해제", "해제 일행방어"), button("순번 분배", "순번 일행분배"),
          button(party.confirm_dissolve ? "해체 최종 확인" : "해체 요청", party.confirm_dissolve ? "확인 일행해체" : "일행해체"));
        for (const enemy of state.enemies) {
          const attack = actionButton(enemy.label + " 공동 공격", enemy.party_attack_action);
          attack.disabled = !enemy.can_attack; partyActions.push(attack);
        }
      }
    }
    byId("party-actions").replaceChildren(...partyActions);
    byId("party-invite-form").hidden = !!party && !party.is_leader;
    byId("party-request").hidden = !!party;
    byId("party-chat-form").hidden = !party;
    const invitation = state.invitation;
    byId("party-invitation").hidden = !invitation || pendingTime(invitation, state.server_now).expired;
    byId("party-inviter").textContent = invitation ? invitation.inviter + "의 일행 초청 · " + pendingTime(invitation, state.server_now).label : "";
    for (const object of state.interactables) for (const action of object.actions) {
      const el = action.action ? actionButton(object.label + " " + action.label, action.action) : button(object.label + " " + action.label, action.command);
      el.replaceChildren(semantic(object.role, object.label), " ", semantic("command", action.label));
      actions.push(el);
    }
    byId("context-actions").replaceChildren(...actions);
    for (const action of state.action_controls || []) {
      if (action.action.roles.provider?.[0]?.kind !== "item") {
        byId("context-actions").append(actionButton(action.label, action.action));
      }
    }
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
        const mark = document.createElement("small");
        mark.textContent = item.active_weapon ? "주무기" : "착용 중";
        row.append(mark);
      }
      for (const control of state.action_controls || []) {
        const provider = control.action.roles.provider?.[0];
        if (provider?.kind === "item" && provider.identity === item.identity) {
          row.append(actionButton(control.label, control.action));
        }
      }
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
    if (encounter) byId("encounter").replaceChildren(semantic("hostile", encounter.name), " · 공유 체력 " + encounter.hp + "/" + encounter.max_hp + " · 적 " + encounter.round + "차례" + (encounter.telegraph ? " · 다음 특수 공격! 견제와 치료를 준비하세요." : " · 강타 / 쏴 / 견제 / 치료"));
  }
  function connect() {
    if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
    byId("connection-label").textContent = "연결 중";
    byId("reconnect").hidden = true;
    const configured = document.body.dataset.wsUrl;
    const url = configured || ((location.protocol === "https:" ? "wss://" : "ws://") + location.hostname + ":" + document.body.dataset.wsPort);
    const connection = new WebSocket(url, "v1.evennia.com");
    socket = connection;
    resetMinimap();
    connection.addEventListener("open", () => {
      if (connection !== socket) return;
      byId("connection-label").textContent = "연결됨";
      byId("connection-dot").classList.add("connected");
      byId("auth-error").textContent = "";
      if (!playing && !dialog.open) dialog.showModal();
    });
    connection.addEventListener("message", (event) => {
      if (connection !== socket || connection.readyState !== WebSocket.OPEN) return;
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
        append("", ["sheet", "event", "error", "chat", "prompt", "map"].includes(message.kind) ? message.kind : "", message.segments);
      } else if (kind === "pz_state" && args?.[0]) render(args[0]);
      else if (kind === "pz_map") renderMinimap(args?.[0]);
      else if (kind === "pz_map_state" && minimapOwner && args?.[0]?.owner === minimapOwner) {
        syncMinimap(args[0].revision, minimapOwner);
      }
      else if (kind === "pz_map_reset") resetMinimap();
      else if (kind === "pz_action_result" && args?.[0]?.action) {
        byId("context-actions").append(actionButton("확정", args[0].action));
      }
      else if (kind === "pz_auth") {
        authBusy(false);
        byId("auth-error").textContent = args?.[0]?.ok ? "" : (args?.[0]?.message || "접속에 실패했습니다.");
        if (args?.[0]?.ok) {
          resetMinimap();
          byId("password").value = "";
        }
      }
    });
    connection.addEventListener("close", () => {
      if (connection !== socket) return;
      resetMinimap();
      playing = false; latestPrompt = []; authBusy(false);
      input.disabled = true; byId("send-command").disabled = true;
      byId("connection-label").textContent = "연결 끊김";
      byId("connection-dot").classList.remove("connected");
      byId("reconnect").hidden = false; byId("logout").hidden = true;
      append("연결이 종료되었습니다. 재연결 후 같은 계정으로 접속하면 저장된 탐사를 이어갑니다.", "event");
    });
    connection.addEventListener("error", () => {
      if (connection === socket) byId("auth-error").textContent = "서버에 연결할 수 없습니다. 서버 실행 상태를 확인하세요.";
    });
  }
  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action-invocation]");
    if (action) {
      if (playing) send("pz_action", [{...JSON.parse(action.dataset.actionInvocation), request_id: Date.now() + "-" + (++actionSequence)}]);
      return;
    }
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
    if (name) command(name + " " + (event.submitter?.value === "일행요청" ? "일행요청" : "일행초청"));
  });
  byId("party-chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const body = byId("party-chat-body").value.trim();
    if (body) { command(body + " 일행대화"); byId("party-chat-body").value = ""; }
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
