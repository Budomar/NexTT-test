#!/usr/bin/env python3
"""Golden-master tests for the existing NexTT Python implementation."""

import argparse
import hashlib
import itertools
import json
import logging
import math
import platform
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BASELINE_COMMIT = "3e96974b134dc49a3058b375559d91c976279cab"
FIXED_TIME = "2000-01-02T03:04:05"
MISSING = object()

SOURCE_FILES = [
    "nextt/core/power_recalculator.py",
    "nextt/core/pallet_calculator.py",
    "nextt/core/brackets.py",
    "nextt/patterns/template_manager.py",
    "nextt/logger.py",
    "nextt/__init__.py",
    "nextt/core/__init__.py",
    "nextt/patterns/__init__.py",
]


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2000, 1, 2, 3, 4, 5)
        return value if tz is None else value.replace(tzinfo=tz)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(value):
    """Keep ordinary JSON values plus exact float64 bits by JSON path."""
    bits = {}

    def convert(item, path):
        # Convert numpy scalars returned by pandas.
        if type(item).__module__.startswith("numpy") and hasattr(item, "item"):
            item = item.item()

        if isinstance(item, float):
            bits[path] = struct.pack(">d", item).hex()
            if not math.isfinite(item):
                return {"non_finite": repr(item)}
            return item

        if isinstance(item, dict):
            return {
                str(key): convert(val, path + "/" + str(key))
                for key, val in item.items()
            }

        if isinstance(item, (list, tuple)):
            return [
                convert(val, path + "/" + str(index))
                for index, val in enumerate(item)
            ]

        if item is None or isinstance(item, (str, int, bool)):
            return item

        raise TypeError(f"Unsupported snapshot type: {type(item).__name__}")

    return {"value": convert(value, "$"), "float64_bits": bits}


def build_cases(P, B, pallet_rules):
    cases = []

    def add(case_id, target, *args, expected=MISSING, **kwargs):
        case = {
            "id": case_id,
            "target": target,
            "args": list(args),
            "kwargs": kwargs,
        }
        if expected is not MISSING:
            case["assert_value"] = expected
        cases.append(case)

    # ---- Power: explicit examples and error behaviour ----

    add("power.delta.reference", "power.delta_t_from",
        95, 85, 20, expected=70.0)
    add("power.delta.nonstandard", "power.delta_t_from",
        75, 65, 20, expected=50.0)
    add("power.delta.strings", "power.delta_t_from",
        "75", "65", "20", expected=50.0)
    add("power.delta.empty", "power.delta_t_from", "", 65, 20)

    for value, expected in [
        (None, 500), ("", 500), ("abc", 500),
        (450, 400), (750, 600), (-1, 300), (5000, 900),
    ]:
        add(f"power.height.{value!r}", "power.normalize_height",
            value, expected=expected)

    add("power.type.alias", "power.normalize_type",
        " 12 ", expected="21")

    for delta in [-10.0, 0.0, 0.0001, 35.0, 50.0, 70.0, 120.0, 120.001]:
        add(f"power.valid.{delta}", "power.is_valid_delta", delta)

    for edge in [70.0 - 0.001, 70.0 + 0.001]:
        for value in [
            math.nextafter(edge, -math.inf),
            edge,
            math.nextafter(edge, math.inf),
        ]:
            add(f"power.reference.{value.hex()}",
                "power.is_reference", value)
            add(f"power.reference_factor.{value.hex()}",
                "power.factor", "22", 500, value)

    for rad_type, height, delta in itertools.product(
        ["10", "11", "20", "21", "22", "30", "33", "12", "99", ""],
        [300, 400, 500, 600, 900, 450, None],
        [-10.0, 0.0, 35.0, 50.0, 70.0, 120.0, 120.001],
    ):
        suffix = f"{rad_type!r}.{height!r}.{delta}"
        add("power.factor." + suffix,
            "power.factor", rad_type, height, delta)
        add("power.recalc." + suffix,
            "power.recalc_power", 2000.0, rad_type, height, delta)

    for qnom in [0, -100, 2.5, 3.5, 4.5, "2000", "", None]:
        add(f"power.qnom.{qnom!r}", "power.recalc_power",
            qnom, "22", 500, 70.0)

    add("power.table.empty", "power_table", [], 500, 50.0,
        expected={})

    rounding_rows = [
        {"Наименование": "Радиатор 22/500/400",
         "RadiatorType": 22, "Мощность, Вт": 2.5},
        {"Наименование": "Радиатор 22/500/500",
         "RadiatorType": 22, "Мощность, Вт": 3.5},
        {"Наименование": "Радиатор 22/500/600",
         "RadiatorType": 22, "Мощность, Вт": 4.5},
    ]
    add("power.table.bankers_rounding", "power_table_probe",
        rounding_rows, 500, 70.0, expected=[2, 4, 4])

    duplicate_rows = [
        {"Наименование": "Радиатор 22/500/400",
         "RadiatorType": 22, "Мощность, Вт": 1000},
        {"Наименование": "Радиатор 22/500/400",
         "RadiatorType": 22, "Мощность, Вт": 1200},
        {"Наименование": "Радиатор 22/500/500 ra",
         "RadiatorType": 22, "Мощность, Вт": 1500},
    ]
    add("power.table.duplicate_and_suffix", "power_table",
        duplicate_rows, 500, 50.0)

    # ---- Pallets: every rule and its neighbouring lengths ----

    seen_pallets = set()
    for rad_type, height, lo, hi, capacity, size in pallet_rules:
        for length in [lo - 1, lo, hi, hi + 1]:
            args = (rad_type, height, length)
            if args in seen_pallets:
                continue
            seen_pallets.add(args)
            suffix = ".".join(map(str, args))
            add("pallet.rule." + suffix, "pallet.get_pallet_info", *args)
            add("pallet.approx." + suffix, "pallet.is_approximate", *args)

    for args in [
        ("99", 500, 1000), ("12", 500, 1000),
        ("22", 450, 1000), ("", 500, 1000),
        ("22", 500, 2001), ("22", 500, 2099),
    ]:
        add("pallet.invalid." + repr(args),
            "pallet.get_pallet_info", *args)

    for size in [None, "", "1200*800", "1200*1000", "1200*1200", "unknown"]:
        add(f"pallet.weight.{size!r}",
            "pallet.get_pallet_weight", size, expected=15.0)

    radiator_name = "Радиатор LaggarTT Classic K-Profil 22/500/1200"
    for qty in [1, 17, 18, 19, 36, 0, -1, "", "abc", "1.5", 1.9]:
        rows = [{
            "Артикул": "TEST",
            "Наименование": radiator_name,
            "Кол-во": qty,
        }]
        add(f"pallet.spec.qty.{qty!r}", "pallet_spec",
            rows, {"TEST": 10.125})

    add("pallet.spec.empty", "pallet_spec", [], {})
    add("pallet.spec.missing_weight", "pallet_spec", [{
        "Артикул": "MISSING",
        "Наименование": radiator_name,
        "Кол-во": 19,
    }], {})

    add("pallet.spec.mixed", "pallet_spec", [
        {"Артикул": "A", "Наименование": radiator_name, "Кол-во": 1},
        {"Артикул": "B", "Наименование": "Кронштейн TEST", "Кол-во": 2},
        {"Артикул": "C", "Наименование": "Неизвестное изделие", "Кол-во": 3},
        {"Артикул": "D", "Наименование": radiator_name, "Кол-во": 0},
    ], {"A": 10.125, "C": "invalid"})

    for length in [1200, 1201]:
        for count in [0, 0.01, 1, 2, 2.01, 13, 14]:
            add(f"pallet.totals.{length}.{count}", "pallet_totals", [{
                "Длина, мм": length,
                "Паллет, шт": count,
                "Вес с паллетами, кг": 1000,
            }])

    add("pallet.totals.empty", "pallet_totals", [])
    add("pallet.totals.invalid", "pallet_totals", [{
        "Длина, мм": "abc",
        "Паллет, шт": "abc",
        "Вес с паллетами, кг": "abc",
    }])

    # ---- Brackets: automatic and manual rules independently ----

    groups = [
        ("WALL_VK_K_RULES", "calculate"),
        ("FLOOR_VK_K_RULES", "calculate"),
        ("WALL_HV_H_RULES", "calculate"),
        ("FLOOR_HV_H_RULES", "calculate"),
        ("MANUAL_COMPATIBILITY_RULES", "calculate_for_manual"),
    ]
    seen_brackets = set()

    for rules_name, method in groups:
        for rule in getattr(B, rules_name):
            connection = (
                "VK-правое" if rule.connection_group == "VK_K"
                else "HV-правое"
            )
            mount = (
                "Настенные кронштейны" if rule.mount_type == "настенный"
                else "Напольные кронштейны"
            )
            lengths = {
                rule.length_min - 1, rule.length_min,
                rule.length_max, rule.length_max + 1,
            }
            heights = {
                rule.height_min - 1, rule.height_min,
                rule.height_max, rule.height_max + 1,
            }
            for rad_type, length, height in itertools.product(
                rule.types, sorted(lengths), sorted(heights)
            ):
                args = (rad_type, length, height, mount, connection, 1)
                key = (method,) + args
                if key in seen_brackets:
                    continue
                seen_brackets.add(key)
                case_id = hashlib.sha256(
                    json.dumps(key, ensure_ascii=False).encode("utf-8")
                ).hexdigest()[:20]
                add("brackets.rule." + case_id,
                    "brackets." + method, *args)

    for method in ["calculate", "calculate_for_manual"]:
        for connection in [
            "VK-правое", "VK-левое", "K-боковое",
            "HV-правое", "HV-левое", "H-боковое", "UNKNOWN",
        ]:
            for qty in [0, 1, 3, -1]:
                add(f"brackets.connection.{method}.{connection}.{qty}",
                    "brackets." + method,
                    "22", 1000, 500, "Настенные кронштейны",
                    connection, qty)

        for mount in ["Без кронштейнов", "UNKNOWN"]:
            add(f"brackets.mount.{method}.{mount}",
                "brackets." + method, "22", 1000, 500, mount)

        add(f"brackets.unknown_type.{method}",
            "brackets." + method,
            "99", 1000, 500, "Настенные кронштейны")

    for length in [1600, 1650, 1700]:
        add(f"brackets.wall_transition.{length}", "brackets.calculate",
            "22", length, 500, "Настенные кронштейны")

    add("brackets.total.empty", "brackets.calculate_total",
        [], "Настенные кронштейны", expected={})

    add("brackets.total.aggregate", "brackets.calculate_total", [
        {"rad_type": "22", "length": 1600, "height": 500, "qty": 2},
        {"rad_type": "22", "length": 1700, "height": 500, "qty": 3},
    ], "Настенные кронштейны")

    # ---- Templates ----

    basic = {
        "id": "basic",
        "mask": "R {type}/{height}/{length}",
        "connection": "VK-правое",
        "priority": 95,
    }

    for text in [
        "R 22/500/1000", "r 22/500/1000", "R 12/500/1000",
        "R 99/500/1000", "R 22/450/1000", "R 22/500/1050",
        "", "unrelated text", "R 22/500/1000 extra",
    ]:
        add("template.apply." + repr(text),
            "template_apply", [basic], text)

    for transform, hcode, lcode in [
        ("code * 10", "50", "100"),
        ("code * 100", "5", "10"),
        ("code / 10", "5000", "10000"),
        ("code / 100", "50000", "100000"),
    ]:
        template = dict(
            basic, height_transform=transform, length_transform=transform
        )
        add("template.transform." + transform, "template_apply",
            [template], f"R 22/{hcode}/{lcode}")

    for decimal_text in ["1,2", "1.2", "0.4", "3.0"]:
        template = dict(basic, length_transform="parse_decimal")
        add("template.decimal." + decimal_text, "template_apply",
            [template], f"R 22/500/{decimal_text}")

    reordered = dict(basic, mask="R {length}/{type}/{height}")
    add("template.marker_order", "template_apply",
        [reordered], "R 1000/22/500")

    low = dict(basic, id="low", priority=50)
    high = dict(basic, id="high", priority=99)
    equal = dict(basic, id="equal", priority=50)

    add("template.priority", "template_apply",
        [low, high], "R 22/500/1000")
    add("template.priority_tie", "template_apply",
        [low, equal], "R 22/500/1000")
    add("template.priority_zero", "template_apply",
        [dict(basic, priority=0)], "R 22/500/1000", expected=None)
    add("template.find_first", "template_find",
        [low, high], "R 22/500/1000", expected="low")

    for text in [
        "Kermi 12/500/1000",
        "Purmo 22/500/1000",
        "Radiator 22/50/100",
        "Radiator 22/500/1,2",
        "1.2. Radiator 22/500/1000",
        "",
        "Radiator 22",
    ]:
        rad_type = "21" if "Kermi" in text else "22"
        length = 1200 if "1,2" in text else 1000
        add("template.create." + repr(text), "template_create",
            text, "VK-правое", rad_type, 500, length)

    add("template.corrupt_file", "template_corrupt", expected=0)

    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise AssertionError("Duplicate scenario IDs")
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["record", "check"])
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--golden", type=Path,
                        default=Path("golden_results.json"))
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not (repo / "nextt/core/power_recalculator.py").is_file():
        parser.error("--repo must point to the NexTT repository root")

    # Avoid accidentally importing a different checkout.
    if any(name == "nextt" or name.startswith("nextt.")
           for name in sys.modules):
        raise RuntimeError("Run this script in a fresh Python process")

    sys.path.insert(0, str(repo))

    import pandas as pd
    from nextt.core.power_recalculator import PowerRecalculator as P
    from nextt.core.pallet_calculator import PalletCalculator as L
    from nextt.core.pallet_calculator import PALLET_RULES
    from nextt.core.brackets import BracketsCalculator as B
    import nextt.patterns.template_manager as tm

    logging.disable(logging.CRITICAL)

    class WeightProvider:
        def __init__(self, weights):
            self.weights = weights

        def find_by_article(self, article):
            if article not in self.weights:
                return None
            return {"Вес, кг": self.weights[article]}

    def invoke(case):
        target = case["target"]
        values = case["args"]
        kwargs = case["kwargs"]

        for prefix, obj in [
            ("power.", P), ("pallet.", L), ("brackets.", B)
        ]:
            if target.startswith(prefix):
                method = target[len(prefix):]
                return getattr(obj, method)(*values, **kwargs)

        if target in ("power_table", "power_table_probe"):
            rows, height, delta = values
            provider = SimpleNamespace(radiators_df=pd.DataFrame(rows))
            result = P.full_table_for_height(height, delta, provider)
            return result["22"][:3] if target.endswith("_probe") else result

        if target == "pallet_spec":
            rows, weights = values
            calculator = L(WeightProvider(weights))
            result = calculator.calculate_for_spec(pd.DataFrame(rows))
            return {
                "columns": list(result.columns),
                "rows": result.to_dict(orient="records"),
                "totals": calculator.calculate_totals(result),
            }

        if target == "pallet_totals":
            return L(None).calculate_totals(pd.DataFrame(values[0]))

        with tempfile.TemporaryDirectory(prefix="nextt_golden_") as directory:
            path = Path(directory) / "templates.json"

            if target in ("template_apply", "template_find"):
                templates, text = values
                path.write_text(
                    json.dumps({"шаблоны": templates}, ensure_ascii=False),
                    encoding="utf-8",
                )
                manager = tm.TemplateManager(str(path))
                if target == "template_apply":
                    return manager.apply_templates(text)
                found = manager.find_matching_template(text)
                return None if found is None else found.id

            if target == "template_create":
                manager = tm.TemplateManager(str(path))
                template = manager.analyze_and_create_template(*values)
                reloaded = tm.TemplateManager(str(path))
                return {
                    "template": None if template is None else template.to_dict(),
                    "count": manager.count,
                    "saved": path.exists(),
                    "reloaded_count": reloaded.count,
                    "reapplied": reloaded.apply_templates(values[0]),
                }

            if target == "template_corrupt":
                path.write_text("{broken json", encoding="utf-8")
                return tm.TemplateManager(str(path)).count

        raise ValueError(f"Unknown target: {target}")

    cases = build_cases(P, B, PALLET_RULES)
    fingerprints = {
        name: sha256(repo / name) for name in SOURCE_FILES
    }

    def evaluate(case):
        try:
            value = invoke(case)
            outcome = {"status": "ok", "result": snapshot(value)}
        except Exception as exc:
            outcome = {
                "status": "exception",
                "type": type(exc).__module__ + "." + type(exc).__qualname__,
                "message": str(exc),
            }

        if "assert_value" in case:
            required = {
                "status": "ok",
                "result": snapshot(case["assert_value"]),
            }
            if outcome != required:
                raise AssertionError(
                    f"Independent assertion failed: {case['id']}\n"
                    f"Expected: {required}\nActual: {outcome}"
                )
        return outcome

    if args.mode == "record":
        if args.golden.exists():
            parser.error(
                "Golden file already exists. "
                "Do not overwrite an approved baseline."
            )

        # Only nondeterministic template timestamps are frozen.
        with patch.object(tm, "datetime", FrozenDateTime):
            recorded = [
                dict(case, expected=evaluate(case)) for case in cases
            ]

        document = {
            "schema_version": 1,
            "baseline_commit": BASELINE_COMMIT,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "pandas": pd.__version__,
            },
            "fixed_template_time": FIXED_TIME,
            "source_sha256": fingerprints,
            "cases": recorded,
        }

        args.golden.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.golden.with_suffix(args.golden.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(args.golden)
        exceptions = sum(
            case["expected"]["status"] == "exception"
            for case in recorded
        )
        print(f"RECORDED: {len(recorded)} cases -> {args.golden}")
        print(f"Exception outcomes requiring review: {exceptions}")
        return

    baseline = json.loads(args.golden.read_text(encoding="utf-8"))

    if baseline["source_sha256"] != fingerprints:
        raise SystemExit(
            "Source fingerprints differ from the approved Python baseline."
        )

    recorded_cases = baseline["cases"]
    recorded_inputs = [
        {key: value for key, value in case.items() if key != "expected"}
        for case in recorded_cases
    ]
    if recorded_inputs != cases:
        raise SystemExit(
            "Scenario definitions differ from the approved baseline."
        )

    failures = []
    with patch.object(tm, "datetime", FrozenDateTime):
        for case in recorded_cases:
            actual = evaluate(case)
            if actual != case["expected"]:
                failures.append({
                    "id": case["id"],
                    "expected": case["expected"],
                    "actual": actual,
                })

    if failures:
        print(json.dumps(failures[:20], ensure_ascii=False, indent=2))
        raise SystemExit(f"FAILED: {len(failures)} scenarios")

    print(
        f"PASS: {len(recorded_cases)} cases; "
        "values, exception outcomes and float64 bits match"
    )


if __name__ == "__main__":
    main()