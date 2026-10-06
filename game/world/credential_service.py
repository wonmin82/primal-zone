"""출입증은 backend와 무관한 ItemEntity SSOT이며 임무는 재발급 근거다."""

from world import rules
from world.content import ITEMS
from world.item_entities import api
from world.item_entities.services import lock_character_items
from world.multiplayer import world_change

CREDENTIAL_QUESTS = {"outpost_supply_pass": "radio_tower", "special_supply_pass": "deep_jungle"}


def credential_items(character):
    return tuple(row for row in api.items_owned_by(character)
                 if ITEMS[row.definition_id].get("item_type") == "credential")


def has_credential(character, credential_id):
    return any(row.definition_id == credential_id for row in credential_items(character))


def grant_credential(character, credential_id):
    if credential_id not in CREDENTIAL_QUESTS:
        raise rules.RuleError("알 수 없는 출입증입니다.")
    with world_change():
        locked = lock_character_items(character)
        existing = next((row for row in locked.values() if row.definition_id == credential_id), None)
        return existing or api.create_item(credential_id, location_kind="inventory", owner_object=character)


def reissue_credential(character, credential_id):
    with world_change():
        lock_character_items(character)
        if not character.profile_snapshot()["quests"][CREDENTIAL_QUESTS[credential_id]]["claimed"]:
            raise rules.RuleError("임무 최종 보고를 마친 뒤 재발급받을 수 있습니다.")
        return grant_credential(character, credential_id)


def issuer_talk(character, credential_id, operation):
    """기존 pure 보상과 출입증 생성, profile 저장을 동일 transaction에서 처리한다."""
    with world_change():
        lock_character_items(character)
        granted = False

        def talk(profile):
            nonlocal granted
            result = operation(profile)
            if result == "complete":
                from world.content.item_mapping import BOSS_REWARDS

                identity = BOSS_REWARDS[CREDENTIAL_QUESTS[credential_id]]
                if not any(row.definition_id == identity for row in api.items_owned_by(character)):
                    api.create_item(identity, location_kind="inventory", owner_object=character)
            if profile["quests"][CREDENTIAL_QUESTS[credential_id]]["claimed"] and not has_credential(character, credential_id):
                grant_credential(character, credential_id)
                granted = True
            return result

        return character.change(talk), granted
