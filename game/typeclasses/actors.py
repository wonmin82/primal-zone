"""비플레이어 실물의 단일 정체성. 게임 효과는 도메인 Service가 소유한다."""

from evennia.objects.objects import DefaultObject
from world import text as ft
from world.actors import content
from world.actors.validation import ActorDefinitionError
from world.distant_presentation import DistantPresence, DistantPresenceMixin
from world.multiplayer import world_change
from world.selection_numbers.mixins import NumberedObjectMixin
from world.shared_combat import SharedCombatMixin


class Actor(SharedCombatMixin, NumberedObjectMixin, DistantPresenceMixin, DefaultObject):
    @property
    def actor_id(self):
        return self.db.actor_id

    @property
    def spawn_id(self):
        return self.db.spawn_id

    @property
    def definition(self):
        try:
            return content.ACTORS[self.actor_id]
        except KeyError as error:
            raise ActorDefinitionError("Actor의 정적 정의가 없습니다.") from error

    @property
    def action_provider_definition(self):
        return self.definition.action_provider_id

    @property
    def detectability(self):
        return self.definition.presentation.detectability

    @property
    def distant_visible(self):
        return self.definition.presentation.distant_visible

    @property
    def level(self):
        return self.definition.level

    @property
    def classification(self):
        return self.definition.classification

    @property
    def hp(self):
        state = self.db.combat_state
        return state["hp"] if state is not None else None

    @hp.setter
    def hp(self, value):
        self.db.combat_state = {**self.db.combat_state, "hp": value}

    @property
    def combat_definition_id(self):
        return self.actor_id

    @property
    def shared_combat_active(self):
        return self.supports_shared_combat and self.capability_active("combat")

    @property
    def supports_shared_combat(self):
        return bool(self.actor_id and "combat_mode" in self.combat_profile)

    @property
    def combat_profile(self):
        return self.definition.profiles.get("combat", {})

    @property
    def max_hp(self):
        state = self.db.combat_state
        if state is None:
            return None
        profile = self.definition.profiles.get("combat", {})
        return state.get("max_hp", profile.get("max_hp", profile.get("hp")))

    @max_hp.setter
    def max_hp(self, value):
        self.db.combat_state = {**self.db.combat_state, "max_hp": value}

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false()")

    def capability_active(self, capability_id):
        if capability_id not in self.definition.capabilities:
            return False
        descriptor = content.CAPABILITIES.get(capability_id)
        if descriptor is None:
            return False
        states = self.db.capability_states or {}
        return (states.get(capability_id, True) is True
                and (not descriptor.active_states or self.db.state in descriptor.active_states))

    def set_capability_active(self, capability_id, active):
        if capability_id not in self.definition.capabilities or type(active) is not bool:
            raise ActorDefinitionError("보유 Capability와 명시적 활성 상태가 필요합니다.")
        with world_change():
            states = dict(self.db.capability_states or {})
            if active:
                states.pop(capability_id, None)
            else:
                states[capability_id] = False
            self.db.capability_states = states

    def available(self, caller, observed_at=None):
        if any(self.capability_active(kind) for kind in ("medical", "settlement", "shop", "training")):
            from typeclasses.interactables import _service_available

            return _service_available(self, caller, observed_at)
        return True

    def training_offer(self):
        from typeclasses.interactables import AttributeTrainer, SkillTrainer, TrainingManager

        if self.db.skill_id:
            return SkillTrainer.training_offer(self)
        if self.db.attribute_id:
            return AttributeTrainer.training_offer(self)
        return TrainingManager.training_offer(self)

    def capability_binding_ids(self):
        if self.capability_active("shop") or self.capability_active("training"):
            from world.actions.manifest import get_index

            return tuple(binding.id for binding in get_index().bindings_for_provider.get(
                self.action_provider_definition, (),
            ))
        return tuple(dict.fromkeys(binding_id for identity in self.definition.capabilities
                                   if self.capability_active(identity)
                                   for binding_id in content.CAPABILITIES[identity].binding_ids))

    @property
    def semantic_role(self):
        return self.definition.presentation.semantic_role

    @property
    def presence(self):
        return self.get_local_presence()

    def get_local_presence(self):
        return self.definition.presentation.presence

    def get_distant_presence(self, context):
        presentation = self.definition.presentation
        return DistantPresence(self.key, presentation.semantic_role, presentation.unit,
                               presentation.distant_presence)

    def is_distant_visible(self, context):
        if self.supports_shared_combat and (not self.capability_active("combat") or self.hp <= 0):
            return False
        return super().is_distant_visible(context)

    def return_appearance(self, looker, **kwargs):
        presentation = self.definition.presentation
        if self.supports_shared_combat:
            active = self.shared_combat_active
            return ft.sheet(
                ft.token(presentation.semantic_role, self.key),
                presentation.description,
                f"체력 {self.hp} / {self.max_hp}" if active else "아직 다시 모습을 드러내지 않았다.",
                "",
                ft.actions(["공격"] if active else []),
            )
        lines = [presentation.description]
        if self.capability_active("settlement") or self.capability_active("shop"):
            from world.actions.presentation import provider_verbs
            from world.targets import labels, room_objects

            actions = set(provider_verbs(looker, self, kwargs.get("observed_at")))
            target = labels(room_objects(looker)).get(self.id)
            if target and actions:
                commands = ((
                    f"{target} 목록", f"{target}에게 물건이름 사", f"{target}에게 물건이름 가치", f"{target}에게 물건이름 팔아",
                ) if self.capability_active("shop") else (
                    f"{target} 환율", "회수부품 교환", "회수부품 10개 교환", "회수부품 모두 교환",
                    f"{target}에게 회수부품 10개 교환",
                ))
                lines.extend(("", ft.join(
                    [ft.usage(command, actions) for command in commands
                     if command.rsplit(" ", 1)[-1] in actions], " · ",
                )))
        if self.capability_active("medical"):
            from world.actions.presentation import provider_verbs

            actions = provider_verbs(looker, self, kwargs.get("observed_at"))
            if "회복" in actions:
                from world import rules
                from world.content import ROOMS

                try:
                    restored, cost = rules.treatment_quote(
                        looker.profile_snapshot(), safe=ROOMS.get(looker.zone, {}).get("safe", False),
                    )
                    lines.append(f"현재 HP {restored} 전체 회복 예상 비용: {cost}칩 (실행 시 재계산)")
                except rules.RuleError as error:
                    lines.append(str(error))
                lines.extend(("회복 · 20 회복 · 의무관에게 20 회복 / 회복실 침대 휴식은 무료", ft.actions(actions)))
        if self.capability_active("training"):
            from world.actions.presentation import provider_verbs

            actions = set(provider_verbs(looker, self, kwargs.get("observed_at")))
            offer, commands = self.training_offer()
            commands = [command for command in commands if command.rsplit(" ", 1)[-1] in actions
                        or command.endswith(" 재훈련") and "재분배" in actions]
            lines.extend(("", offer, "", ft.join(
                [ft.usage(command, actions | {"재훈련"}) for command in commands], "\n",
            )))
        if self.capability_active("combat"):
            maximum = self.max_hp
            lines.append(f"체력 {self.hp}/{maximum}" if maximum is not None else f"체력 {self.hp}")
        result = ft.sheet(ft.token(presentation.semantic_role, self.key), *lines)
        if self.capability_active("dialogue"):
            from world.npc_dialogue import accessible, discovery

            if accessible(looker, self):
                return ft.text(result, "\n", discovery(self, looker))
        return result
