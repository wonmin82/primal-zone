"""비플레이어 실물의 단일 정체성. 게임 효과는 도메인 Service가 소유한다."""

from evennia.objects.objects import DefaultObject
from world import text as ft
from world.actors import content
from world.actors.validation import ActorDefinitionError
from world.distant_presentation import DistantPresence, DistantPresenceMixin
from world.multiplayer import world_change
from world.selection_numbers.mixins import NumberedObjectMixin


class Actor(NumberedObjectMixin, DistantPresenceMixin, DefaultObject):
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

    def capability_binding_ids(self):
        return tuple(dict.fromkeys(binding_id for identity in self.definition.capabilities
                                   if self.capability_active(identity)
                                   for binding_id in content.CAPABILITIES[identity].binding_ids))

    def get_local_presence(self):
        return self.definition.presentation.presence

    def get_distant_presence(self, context):
        presentation = self.definition.presentation
        return DistantPresence(self.key, presentation.semantic_role, presentation.unit,
                               presentation.distant_presence)

    def return_appearance(self, looker, **kwargs):
        presentation = self.definition.presentation
        return ft.sheet(ft.token(presentation.semantic_role, self.key), presentation.description)
