# Actor Phase 2 검증

[확정 설계](actor-unification-design-v1.md)의 §14와 [실행 계획](actor-unification-implementation-plan-v1.md)의 G3를 적용한다. 기준 main은 `83ea02831d4aab65e94153c9872b59329b4d7833`이다.

## 대련 및 복구

- 대련은 Actor Attribute의 영속 Encounter에 참가자, 회차, 기한, 대련용 HP와 종료 결과를 저장한다. Explorer의 참가 링크는 Actor의 영속 참가 정보와 함께 확인한다.
- 명시 행동만 60초 무행동 기한을 갱신한다. 최대 600초, 재접속 30초, 기권·타임아웃 후 동일 참가자의 재신청 제한 30초를 적용한다.
- 재시작 시 확정된 재접속 기한이나 여전히 유효한 세션을 기준으로 복구한다. 오프라인인데 연결 종료 시각이 기록되지 않은 대련은 안전 종료한다.
- 대련 종료에서 일반 보상과 시체·전리품 생성을 호출하지 않는다. 대련용 HP와 효과를 격리하며 적법한 기술·탄약 소비는 기존 서비스에서 확정한다.
- 교관·경비로봇은 통합 테스트 fixture다. 브라우저 교관은 격리 서버 복사본에서만 설치한다.
- 대련 참가자의 일반 호흡·치료·붕대와 침대 휴식은 거부한다. 대련 치료·호흡은 명시 행동을 예약하고 회차에서 실행한다. 대련 예약에는 ItemEntity 참조가 없으므로 붕대는 대련의 텍스트·웹·서비스 경로에서 지원하지 않는다.
- 정산 전에 정책별 결과 종류와 필수 필드를 검증한다. 일반 기권·포획·무력화의 표현은 스키마 수준에서 검사하며, 실제 대련 기권은 Exclusive Duel 정책에서 확정할 수 있다.

## 실제 OS 한글 입력

지원 환경에서 격리 E2E-15 교관 서버를 띄운 뒤 실제 한글 입력기를 켠다. 입력 중 Enter가 조합만 확정하는지, 다음 Enter가 명령을 한 번 전송하는지 확인한다. 한글 명령 기록, 상태 갱신 중 조합, NPC 대화와 대련 행동, 재접속 후 입력을 반복한다. 화면과 서버 응답으로 결과를 확인하고 OS·브라우저·입력기 버전을 기록한다. 이 수동 검증은 현재 미실행이다.

저장소 루트에서 아래 명령으로 E2E-15의 교관과 테스트 계정을 가진 서버를 연다. 출력된 로컬 주소와 일회용 계정을 Chrome에서 사용한다. 검증을 마친 뒤 터미널에서 Enter를 눌러 이 실행의 서버를 정리한다.

```bash
PYTHONPATH=scripts uv run python - <<'PY'
import asyncio
import os
from pathlib import Path

from smoke_harness import Harness

os.environ["PRIMAL_INTEGRATION_SCENARIO"] = "E2E-15"
harness = Harness("full")
try:
    harness.prepare(setup_script=Path("scripts/integration_setup.py").resolve())
    harness.start()
    asyncio.run(harness.ready())
    print(f"http://127.0.0.1:{harness.ports['http']}/webclient/")
    print("격리 계정", *harness.credentials[0])
    input("검증이 끝나면 Enter를 누르세요. ")
finally:
    harness.stop()
PY
```
