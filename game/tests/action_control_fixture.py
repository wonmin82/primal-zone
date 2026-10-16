"""운영 Action control의 안정 참조와 실제 인증 웹 진입점 검증."""

from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from server.conf.primal_inputfuncs import pz_action
from world.actions.presentation import reference_json
from world.selection_numbers.api import descriptor, label, number_for


def assert_provider(test, control, provider):
    test.assertNotIn("command", control)
    test.assertEqual(control["action"]["roles"]["provider"], [reference_json(descriptor(provider).reference)])


def execute_control(test, control):
    payload = {**control["action"], "request_id": str(uuid4())}
    with patch.object(test.char1, "msg") as output:
        pz_action(test.session, payload)
    return "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)


def selection_label(provider):
    record = descriptor(provider)
    return label(replace(record, number=number_for(record.reference)))
