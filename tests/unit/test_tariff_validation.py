"""
Unit Test Suite for Formal Tariff & Commercial Utility Bill Validation (Requirement R2).

Validates:
1. Billing data classes, post-init validation, and immutability.
2. Periodic billing calculation engine across Γ21, Γ22, Γ23, Green, Yellow, and Dynamic tariffs.
3. Statutory grid penalties (low cos φ = 0.68, contracted capacity overload 35 kVA -> 43.5 kVA).
4. Benchmark dataset completeness, physical realism, and alias resolution.
5. Automated validator line-by-line comparison asserting < 0.10% discrepancy across all 9 bills.
6. Programmatic report generation script execution.
7. Zero regressions on existing tariff engine calculations.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from scripts.generate_tariff_validation_report import generate_report
from tariff_engine.benchmark_dataset import (
    BENCHMARK_BILLS,
    get_all_benchmark_bills,
    get_benchmark_bill,
    list_benchmark_bill_ids,
)
from tariff_engine.billing import (
    LineItemCategory,
    UtilityBillInput,
    UtilityBillLineItem,
    calculate_periodic_bill,
)
from tariff_engine.contracts import TariffColor, TariffContract
from tariff_engine.cost_calculator import calculate_realtime_cost
from tariff_engine.green_tariff import calculate_green_tariff_supply_rate
from tariff_engine.regulated_charges import get_regulated_breakdown
from tariff_engine.validator import (
    compare_bill,
    validate_benchmark_suite,
)

# =============================================================================
# 1. Billing Data Classes & Immutability Tests
# =============================================================================

class TestBillingDataClasses:
    def test_utility_bill_input_validation(self) -> None:
        """Validates input parameter validation and type coercion."""
        # Valid instantiation
        inp = UtilityBillInput(
            bill_id="TEST-01",
            facility_id="fac_1",
            supplier_name="ΔΕΗ",
            contract_type="G21",
            tariff_color="green",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            billing_period_days=31,
            contracted_capacity_kva=25.0,
            power_factor=0.95,
            energy_active_total_kwh=1000.0,
        )
        assert inp.contract_type == TariffContract.G21
        assert inp.tariff_color == TariffColor.GREEN

        # Capacity <= 0
        with pytest.raises(ValueError, match="contracted_capacity_kva must be positive"):
            UtilityBillInput(
                bill_id="TEST-02",
                facility_id="fac_1",
                supplier_name="ΔΕΗ",
                contract_type=TariffContract.G21,
                tariff_color=TariffColor.GREEN,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
                billing_period_days=31,
                contracted_capacity_kva=0.0,
            )

        # Days <= 0
        with pytest.raises(ValueError, match="billing_period_days must be positive"):
            UtilityBillInput(
                bill_id="TEST-03",
                facility_id="fac_1",
                supplier_name="ΔΕΗ",
                contract_type=TariffContract.G21,
                tariff_color=TariffColor.GREEN,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
                billing_period_days=0,
                contracted_capacity_kva=25.0,
            )

        # Energy < 0
        with pytest.raises(ValueError, match="energy_active_total_kwh cannot be negative"):
            UtilityBillInput(
                bill_id="TEST-04",
                facility_id="fac_1",
                supplier_name="ΔΕΗ",
                contract_type=TariffContract.G21,
                tariff_color=TariffColor.GREEN,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
                billing_period_days=30,
                contracted_capacity_kva=25.0,
                energy_active_total_kwh=-50.0,
            )

        # Power factor out of range
        with pytest.raises(ValueError, match="power_factor must be between 0.0 and 1.0"):
            UtilityBillInput(
                bill_id="TEST-05",
                facility_id="fac_1",
                supplier_name="ΔΕΗ",
                contract_type=TariffContract.G21,
                tariff_color=TariffColor.GREEN,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
                billing_period_days=30,
                contracted_capacity_kva=25.0,
                power_factor=1.25,
            )

    def test_utility_bill_line_item_immutability(self) -> None:
        """Verifies that line items are immutable frozen dataclasses."""
        item = UtilityBillLineItem(
            code="SUPPLY_BASE",
            description="Base Energy Charge",
            category=LineItemCategory.SUPPLY,
            quantity=1000.0,
            unit="kWh",
            unit_rate=0.155,
            amount_eur=155.0,
        )
        with pytest.raises(FrozenInstanceError):
            item.amount_eur = 200.0  # type: ignore

        item_dict = item.to_dict()
        assert item_dict["code"] == "SUPPLY_BASE"
        assert item_dict["category"] == "supply"
        assert item_dict["amount_eur"] == 155.0

    def test_utility_bill_subtotals_consistency(self) -> None:
        """Verifies that bill subtotals strictly equal pre-tax base, and pre-tax + VAT equals total payable."""
        bill_data = BENCHMARK_BILLS["BILL-01-DEI-G21-SUMMER"]
        bill = calculate_periodic_bill(bill_data["input"])

        # Subtotals sum equals pretax
        expected_pretax = round(bill.supply_subtotal_eur + bill.total_regulated_charges_eur, 2)
        assert bill.pretax_total_eur == expected_pretax

        # Pretax + VAT equals total payable
        expected_total = round(bill.pretax_total_eur + bill.vat_amount_eur, 2)
        assert bill.total_payable_eur == expected_total

        # Query existing and non-existing line items
        assert bill.get_line_item("SUPPLY_BASE") is not None
        assert bill.get_line_item("NON_EXISTENT") is None

        # Dictionary serialization
        b_dict = bill.to_dict()
        assert b_dict["bill_id"] == "BILL-01-DEI-G21-SUMMER"
        assert len(b_dict["line_items"]) > 10


# =============================================================================
# 2. Periodic Billing Engine Contract & Mechanism Tests
# =============================================================================

class TestPeriodicBillingEngine:
    def test_g21_green_summer_neutral_band(self) -> None:
        """Verifies single-rate Γ21 Green calculation in neutral wholesale deadband."""
        bill_data = BENCHMARK_BILLS["BILL-01-DEI-G21-SUMMER"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        assert bill.supply_subtotal_eur == exp["supply_subtotal"]
        assert bill.total_regulated_charges_eur == exp["regulated_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]
        assert bill.get_line_item("SUPPLY_MD").amount_eur == 0.00
        assert bill.get_line_item("SUPPLY_DISCOUNT").amount_eur == 48.99

    def test_g21_green_summer_spike_breach(self) -> None:
        """Verifies Green tariff Fluctuation Mechanism positive adjustment under wholesale spike."""
        bill_data = BENCHMARK_BILLS["BILL-02-DEI-G21-SPIKE"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        # MD = 1.15 * (0.145 - 0.115) = 0.03450 €/kWh => 3100 * 0.0345 = 106.95 €
        assert bill.get_line_item("SUPPLY_MD").amount_eur == 106.95
        assert bill.supply_subtotal_eur == exp["supply_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g22_green_summer_peak_dual_rate(self) -> None:
        """Verifies dual-rate Γ22 Summer peak (+25%) and off-peak (-30%) rate application."""
        bill_data = BENCHMARK_BILLS["BILL-03-PROT-G22-SUMMER-PEAK"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        assert bill.supply_subtotal_eur == exp["supply_subtotal"]
        assert bill.total_regulated_charges_eur == exp["regulated_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g22_green_winter_peak_dual_rate(self) -> None:
        """Verifies dual-rate Γ22 Winter peak window calculation and standing charges."""
        bill_data = BENCHMARK_BILLS["BILL-04-PROT-G22-WINTER-PEAK"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        assert bill.supply_subtotal_eur == exp["supply_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g22_low_power_factor_penalty(self) -> None:
        """Verifies exact +25% DEDDIE energy penalty for cos φ = 0.68."""
        bill_data = BENCHMARK_BILLS["BILL-05-ELPED-G22-LOW-PF"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        # M_PF = 0.85 / 0.68 = 1.25 => Penalty = 155.65 * 0.25 = 38.91 €
        assert bill.get_line_item("DEDDIE_PF_PENALTY").amount_eur == 38.91
        assert bill.deddie_subtotal_eur == exp["deddie_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g22_contracted_capacity_breach(self) -> None:
        """Verifies 2.5x capacity surcharge on demand register excess."""
        bill_data = BENCHMARK_BILLS["BILL-06-HERON-G22-CAP-BREACH"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        # Excess = 43.5 - 35 = 8.5 kVA => 2.5 * (4.434 * 8.5 * 31)/365 = 8.00 €
        assert bill.get_line_item("DEDDIE_CAPACITY_EXCESS").amount_eur == 8.00
        assert bill.deddie_subtotal_eur == exp["deddie_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g21_yellow_wholesale_indexed(self) -> None:
        """Verifies Yellow wholesale indexed retail formula with 13.5% grid losses."""
        bill_data = BENCHMARK_BILLS["BILL-07-DEI-G21-YELLOW-DAM"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        # 0.1185 * 1.135 + 0.015 + 0.040 = 0.18950 €/kWh => 2800 * 0.1895 = 530.60 €
        assert bill.get_line_item("SUPPLY_BASE").amount_eur == 530.60
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g22_dynamic_spot_interval(self) -> None:
        """Verifies dynamic spot interval tariff calculation."""
        bill_data = BENCHMARK_BILLS["BILL-08-DYNAMIC-SPOT-INTERVAL"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        assert bill.supply_subtotal_eur == exp["supply_subtotal"]
        assert bill.total_payable_eur == exp["total_payable"]

    def test_g23_medium_voltage_industrial(self) -> None:
        """Verifies Medium Voltage standing charges and discounted ETMEAR rate (0.01200 €/kWh)."""
        bill_data = BENCHMARK_BILLS["BILL-09-HERON-G23-MV-INDUSTRIAL"]
        bill = calculate_periodic_bill(bill_data["input"])
        exp = bill_data["expected"]

        # ETMEAR at 0.01200 €/kWh: 85000 * 0.01200 = 1020.00 €
        assert bill.get_line_item("ETMEAR").amount_eur == 1020.00
        assert bill.get_line_item("SUPPLY_FIXED").amount_eur == 10.00
        assert bill.total_payable_eur == exp["total_payable"]


# =============================================================================
# 3. Benchmark Dataset Completeness & Integrity Tests
# =============================================================================

class TestBenchmarkDatasetIntegrity:
    def test_benchmark_bills_completeness(self) -> None:
        """Ensures all 9 benchmark bills exist with valid specifications and alias mapping."""
        bill_ids = list_benchmark_bill_ids()
        assert len(bill_ids) == 9
        assert "BILL-01-DEI-G21-SUMMER" in bill_ids
        assert "BILL-09-HERON-G23-MV-INDUSTRIAL" in bill_ids

        all_bills = get_all_benchmark_bills()
        assert len(all_bills) == 9

        # Test alias resolution
        b1_alias = get_benchmark_bill("BILL-01-DEI-G21-STANDARD")
        assert b1_alias["input"].bill_id == "BILL-01-DEI-G21-SUMMER"

        # Test unknown ID raises KeyError
        with pytest.raises(KeyError, match="Unknown benchmark bill ID"):
            get_benchmark_bill("UNKNOWN_BILL_99")

    def test_benchmark_bills_physical_realism(self) -> None:
        """Asserts physical bounds on all benchmark bills."""
        for bdata in BENCHMARK_BILLS.values():
            inp = bdata["input"]
            assert inp.energy_active_total_kwh > 0.0
            assert 0.5 <= inp.power_factor <= 1.0
            assert 20.0 <= inp.contracted_capacity_kva <= 500.0
            assert inp.billing_period_days in (28, 29, 30, 31)


# =============================================================================
# 4. Validator Engine & Discrepancy Assertion Tests
# =============================================================================

class TestValidatorEngine:
    def test_identical_bill_comparison_zero_error(self) -> None:
        """Asserts comparing a calculated bill against identical expected yields 0.0% discrepancy."""
        bdata = BENCHMARK_BILLS["BILL-01-DEI-G21-SUMMER"]
        bill = calculate_periodic_bill(bdata["input"])
        res = compare_bill(bdata["expected"], bill)

        assert res.all_passed is True
        assert res.total_delta_eur == 0.0
        assert res.total_discrepancy_pct == 0.0
        assert res.max_line_item_discrepancy_pct == 0.0

    def test_validator_catches_gross_discrepancy(self) -> None:
        """Asserts synthetic discrepancy triggers FAIL status and flags the affected bill."""
        bdata = BENCHMARK_BILLS["BILL-01-DEI-G21-SUMMER"]
        bill = calculate_periodic_bill(bdata["input"])

        corrupted_expected = dict(bdata["expected"])
        corrupted_expected["total_payable"] = 999.99  # Gross discrepancy

        res = compare_bill(corrupted_expected, bill)
        assert res.all_passed is False
        assert res.total_delta_eur > 100.0
        assert res.total_discrepancy_pct > 50.0

    def test_validator_accepts_half_cent_rounding(self) -> None:
        """Asserts 0.01 € differences on fractional items pass within dual tolerance."""
        bdata = BENCHMARK_BILLS["BILL-01-DEI-G21-SUMMER"]
        bill = calculate_periodic_bill(bdata["input"])

        # Shift DETE by 0.01 €
        adjusted_expected = dict(bdata["expected"])
        adjusted_expected["dete"] = round(adjusted_expected["dete"] + 0.01, 2)

        res = compare_bill(adjusted_expected, bill)
        dete_item = next(item for item in res.line_item_comparisons if item.code == "dete")
        assert dete_item.absolute_delta_eur == 0.01
        assert dete_item.is_valid is True
        assert dete_item.status == "PASS"

    def test_all_9_benchmark_bills_pass_under_0_1_percent(self) -> None:
        """Statutory test: Validates all 9 bills assert < 0.10% discrepancy and 100% pass."""
        suite_res = validate_benchmark_suite(tolerance_pct=0.10, tolerance_cents_eur=0.01)

        assert suite_res.suite_passed is True
        assert suite_res.total_bills_tested == 9
        assert suite_res.bills_passed == 9
        assert suite_res.bills_failed == 0
        assert suite_res.max_discrepancy_pct < 0.10
        assert suite_res.total_line_items_evaluated >= 144

        suite_dict = suite_res.to_dict()
        assert suite_dict["suite_passed"] is True


# =============================================================================
# 5. Programmatic Report Generation & Zero-Regression Tests
# =============================================================================

class TestReportGeneration:
    def test_report_generation_executable(self, tmp_path: Path) -> None:
        """Verifies report generator creates valid Markdown document with pass markers."""
        out_file = tmp_path / "tariff_validation_report.md"
        generated_path = generate_report(output_path=out_file)

        assert generated_path.exists()
        content = generated_path.read_text(encoding="utf-8")
        assert "# Empirical Tariff & Utility Bill Validation Audit Report" in content
        assert "100% PASSED (VERIFIED)" in content
        assert "BILL-01-DEI-G21-SUMMER" in content
        assert "BILL-09-HERON-G23-MV-INDUSTRIAL" in content
        assert "Low Power Factor Multiplier ($M_{\\text{PF}}$) Proof" in content


class TestZeroRegressions:
    def test_existing_tariff_engine_unaffected(self) -> None:
        """Asserts that existing tariff functions execute normally with zero regression."""
        # Test existing calculate_realtime_cost
        from datetime import datetime, timezone
        res = calculate_realtime_cost(
            power_kw=15.0,
            energy_kwh_delta=0.25,
            timestamp=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
            tariff_profile=TariffContract.G21,
            tea_eur_mwh=110.0,
        )
        assert res.running_cost_eur_per_h > 0.0
        assert res.incremental_cost_eur > 0.0

        # Test existing green tariff supply rate
        rate = calculate_green_tariff_supply_rate(p_base=0.155, tea_eur_mwh=110.0)
        assert rate > 0.0

        # Test existing regulated breakdown
        breakdown = get_regulated_breakdown(is_lv=True)
        assert breakdown.total_regulated_per_kwh > 0.0
