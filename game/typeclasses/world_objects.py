"""시설의 실물 표현. Door·Storage 등 상태와 규칙은 각 도메인에 유지한다."""

from world.actions.providers import ActionProviderObject
from world.actors import content
from world.actors.validation import ActorDefinitionError


class WorldObject(ActionProviderObject):
    @property
    def definition(self):
        try:
            return content.WORLD_OBJECTS[self.db.world_object_id]
        except KeyError as error:
            raise ActorDefinitionError("WorldObject의 정적 정의가 없습니다.") from error

    @property
    def action_provider_definition(self):
        return self.definition.action_provider_id

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false()")

    def return_appearance(self, looker, **kwargs):
        from world import text as ft

        presentation = self.definition.presentation
        return ft.sheet(ft.token(presentation.semantic_role, self.key), presentation.description)
