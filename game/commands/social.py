"""social 영역의 명시적 게임 명령."""

from commands.base import GameCommand


class Say(GameCommand):
    category = "파티·교류"
    usage = "내용 말 · '내용"
    summary = "같은 방에 공개 발화하고 NPC의 화제·행동 키워드를 사용합니다."
    read_only = True
    input_style = "chat"
    key = "말"
    aliases = ["say"]
    help_sections = (
        ("사용법", ("내용 말 · '내용 · NPC에게 키워드 말 · 'NPC에게 키워드",)),
        ("예시", ("안녕 말", "'안녕", "윤대장에게 임무 말", "'윤대장에게 임무", "'윤대장에게 수락")),
        ("실행 규칙", ("말과 작은따옴표는 동일합니다. 플레이어 발화와 NPC 대사는 같은 방 전체에 공개됩니다.",
                      "에게 대상이 없거나 다른 방·감지 불가·플레이어/일반 객체이면 원문 전체를 공개합니다.",
                      "청록색 〈화제〉는 조회, 황금색 〈행동〉은 상태 변경입니다. 비활성 키워드는 일반색이며 클릭할 수 없습니다.",
                      "NPC 대사 원문은 모두에게 같고 자신의 조건에 따라 강조·웹 클릭 가능 여부만 달라집니다.",
                      "명시적 NPC → 유효한 3분 문맥 → 유일한 화제 NPC → 단일 NPC 인사 순으로 선택합니다.",
                      "이동·감지 상실·만료 등으로 문맥이 종료되며 타인의 대화를 듣는 것만으로 내 문맥이 바뀌지 않습니다.",
                      "웹 키워드도 원래 NPC·Intent를 고정해 같은 서비스로 실행합니다. 보상 시스템 알림은 해당 플레이어만 받습니다.")),
        ("제한", ("최대 300자, 개행·제어문자 불가, ANSI는 제거합니다. 중괄호 등 일반 문자는 그대로 표시합니다.",
                "NPC 후보가 여러 명이거나 인식된 이름의 번호가 잘못되면 오류이며 발화하지 않습니다.",
                "행동은 정확한 키워드·등록된 긍정 표현만 실행합니다. 부정·의문·가정형은 상태를 변경하지 않습니다.",
                "NPC 행동은 현재 위치·시야·접근·비전투·선행 임무 조건을 충족해야 합니다. 비공개 메시지는 대화를 사용하세요.")),
        ("관련 도움말", ("대화 도움", "봐 도움", "임무 도움", "줄임말 도움")),
    )

    def run(self):
        from world.npc_dialogue import say

        say(self.caller, self.args)


class PrivateTalk(GameCommand):
    key = "대화"
    aliases = []
    input_style = "chat"
    read_only = True
    category = "파티·교류"
    usage = "플레이어 내용 대화"
    summary = "온라인 플레이어 한 명에게 비공개 메시지를 보냅니다."
    help_sections = (
        ("사용법", (usage,)),
        ("예시", ("철수 안녕하세요 대화", "철수 2 안녕하세요 대화")),
        ("실행 규칙", ("다른 방의 온라인 캐릭터에게도 전달합니다. 주변 플레이어와 NPC에게는 공개하지 않습니다.",
                      "전송 수락 후 서로의 최근 상대를 영속 캐릭터 ID로 기록합니다. 본문·전체 이력은 저장하지 않습니다.")),
        ("제한", ("자신·NPC·적·일반 객체·오프라인 캐릭터는 대상이 아닙니다. 모호한 이름은 번호로 지정하세요.",
                "내용은 300자까지, 개행·제어문자는 거절하고 ANSI는 제거합니다. 상대의 수신 차단을 적용합니다.",
                "서버가 전달을 수락·시도하는 기능이며 실제 수신·열람·읽음 확인·오프라인 보관을 보장하지 않습니다.")),
        ("관련 도움말", ("대답 도움", "대화거부 도움", "말 도움")),
    )

    def run(self):
        from world.private_messaging import send, split_message

        recipient, body = split_message(self.args.strip())
        send(self.caller, recipient, body)


class Reply(GameCommand):
    key = "대답"
    aliases = []
    input_style = "chat"
    read_only = True
    category = "파티·교류"
    usage = "내용 대답"
    summary = "최근 성공적으로 개인 메시지를 주고받은 상대에게 답장합니다."
    help_sections = (
        ("사용법", (usage,)),
        ("예시", ("알겠습니다 대답",)),
        ("실행 규칙", ("최근 상대는 영속 캐릭터 ID로 기록합니다. 공개 발화·NPC 대화는 최근 상대를 바꾸지 않습니다.",
                      "실패한 전송은 최근 상대를 변경하지 않습니다. 대화와 같은 개인 메시지 서비스를 사용합니다.")),
        ("제한", ("현재 온라인인 다른 플레이어에게만 가능합니다. 삭제·수신 차단·300자·제어문자 검사를 적용합니다.",
                "본문 저장·읽음 확인·오프라인 보관은 제공하지 않습니다.")),
        ("관련 도움말", ("대화 도움", "대화거부 도움", "말 도움")),
    )

    def run(self):
        from world.private_messaging import reply

        reply(self.caller, self.args)


class RefuseTalk(GameCommand):
    key = "대화거부"
    aliases = []
    input_style = "target"
    read_only = True
    category = "파티·교류"
    usage = "플레이어 대화거부 · 대화거부"
    summary = "상대별 개인 메시지 수신 차단을 전환하거나 목록을 확인합니다."
    help_sections = (
        ("사용법", (usage,)),
        ("예시", ("철수 대화거부", "대화거부")),
        ("실행 규칙", ("이름을 지정하면 차단·해제를 토글합니다. 이름 없이 입력하면 자신의 차단 목록을 봅니다.",
                      "존재하는 오프라인 캐릭터도 지정할 수 있습니다. 영속 ID로 저장해 재접속 뒤에도 유지합니다.")),
        ("제한", ("자신·NPC·적·일반 객체는 대상이 아닙니다. 차단 목록은 최대 100명입니다.",
                "개인 대화·대답에만 적용하며 공개 말·NPC·시스템 알림·파티 채팅을 차단하지 않습니다.")),
        ("관련 도움말", ("대화 도움", "대답 도움", "말 도움")),
    )

    def run(self):
        from world.private_messaging import blocked_list, toggle_block

        if self.args.strip():
            toggle_block(self.caller, self.args.strip())
        else:
            self.caller.msg(blocked_list(self.caller))
