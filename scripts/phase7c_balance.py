"""Production 정의를 읽는 Phase 7C deterministic 측정. DB에 접근하지 않는다."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "game"))
from world.balance_analysis import report  # noqa: E402
from world.content import ENEMIES, ITEMS  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--candidate", choices=("pre-tuning-ammo", "ammo-unit-minus-one", "carbine-attack-plus-two", "sentinel-currency-plus-twelve"))
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("samples는 2 이상이어야 합니다.")
    # 명시적 후보는 이 read-only process의 메모리에서만 비교한다. 정의 파일은 쓰지 않는다.
    if args.candidate:
        ITEMS["ammo_556"].update(value=3, purchase_unit_value=3)
    if args.candidate == "pre-tuning-ammo":
        ITEMS["ammo_556"].update(value=3, purchase_unit_value=3)
    elif args.candidate == "ammo-unit-minus-one":
        ITEMS["ammo_556"]["purchase_unit_value"] -= 1
    elif args.candidate == "carbine-attack-plus-two":
        ITEMS["guard_carbine"]["equipment_properties"]["weapon_attack"] += 2
    elif args.candidate == "sentinel-currency-plus-twelve":
        ENEMIES["sentinel"]["currency"] += 12
    result = report(args.samples)
    result["candidate"] = args.candidate
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "samples": args.samples, "loot_ev": result["loot_ev"],
                      "guard_carbine": result["fights"]["t1_firearm"]["sentinel"],
                      "boss_solo": {"ridge": result["fights"]["t1_shield"]["alpha"],
                                    "jungle": result["fights"]["t2_shield"]["jungle_apex"]}}, ensure_ascii=False))
