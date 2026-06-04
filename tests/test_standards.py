from __future__ import annotations

import unittest

from earthwork_core import (
    bill_of_quantities,
    calculate_cut_fill,
    estimate_backfill,
    serial_section_volumes,
    soil_balance,
)
import standards
import version


RU = standards.get_standard("RU")


class ProvenanceTests(unittest.TestCase):
    def test_tool_stamp_carries_version(self):
        self.assertIn(version.__version__, version.tool_stamp())
        self.assertIn("Earthwork Studio", version.tool_stamp())

    def test_russian_edition_stamp_lists_regulations_and_date(self):
        stamp = RU.edition_stamp()
        self.assertIn("standard RU", stamp)
        self.assertIn("ГОСТ 21.508-2020", stamp)
        self.assertIn("checked 2026-06", stamp)

    def test_generic_edition_stamp_admits_no_national_code(self):
        stamp = standards.get_standard("INT").edition_stamp()
        self.assertIn("no national code", stamp)

    def test_provenance_combines_tool_and_standard(self):
        line = version.provenance(RU)
        self.assertTrue(line.startswith(version.tool_stamp()))
        self.assertIn("ГОСТ 21.508-2020", line)

    def test_provenance_without_standard_is_tool_only(self):
        self.assertEqual(version.provenance(), version.tool_stamp())


class StandardRegistryTests(unittest.TestCase):
    def tearDown(self):
        standards.set_active_standard(None)  # never leak the active selection

    def test_default_is_russian(self):
        self.assertIs(standards.get_standard(), standards.RU)
        self.assertEqual(standards.get_standard().code, "RU")

    def test_unknown_code_falls_back_to_default(self):
        self.assertIs(standards.get_standard("ZZ"), standards.DEFAULT)

    def test_registry_lists_both_standards(self):
        codes = [code for code, _name in standards.available_standards()]
        self.assertIn("RU", codes)
        self.assertIn("INT", codes)

    def test_select_active_standard_persists(self):
        standards.set_active_standard("INT")
        self.assertEqual(standards.get_standard().code, "INT")  # no-arg honours active
        standards.set_active_standard(None)
        self.assertEqual(standards.get_standard().code, "RU")

    def test_explicit_code_overrides_active(self):
        standards.set_active_standard("INT")
        self.assertEqual(standards.get_standard("RU").code, "RU")

    def test_second_standard_is_english_and_metric(self):
        intl = standards.get_standard("INT")
        self.assertEqual(intl.locale, "en")
        self.assertEqual(intl.cartogram_layers().parent, "Earthwork cut/fill plan")
        self.assertEqual(intl.earth_mass_table.__self__.volume_label, "m3")
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 0.0, proposed_z=lambda _x, _y: 0.5,
            grid_size_m=20.0,
        )
        self.assertIn("Earthwork cut/fill plan", intl.cartogram_report(result))


class CartogramTextTests(unittest.TestCase):
    def _result(self, grid_size_m):
        return calculate_cut_fill(
            boundary=((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 100.0,
            proposed_z=lambda x, _y: 100.0 + (x - 20.0) * 0.05,
            grid_size_m=grid_size_m,
            samples_per_side=8,
        )

    def test_off_grid_size_is_warned(self):
        self.assertTrue(any("ГОСТ 21.508-2020" in w for w in RU.cartogram_warnings(5.0)))

    def test_standard_grid_size_not_warned(self):
        self.assertFalse(any("ГОСТ 21.508-2020" in w for w in RU.cartogram_warnings(20.0)))

    def test_cartogram_report_mentions_method(self):
        report = RU.cartogram_report(self._result(20.0))
        self.assertIn("Картограмма земляных масс", report)
        self.assertIn("ГОСТ 21.508-2020", report)

    def test_earth_mass_table_rows_and_totals(self):
        table = RU.earth_mass_table(self._result(20.0))
        self.assertEqual(table.header[0], "Колонка")
        self.assertEqual(table.rows[0], ("0", "0.00", "200.00", "-200.00"))
        self.assertEqual(table.rows[1], ("1", "200.00", "0.00", "200.00"))
        self.assertEqual(table.rows[-1], ("Итого", "200.00", "200.00", "0.00"))


class SerialTableTests(unittest.TestCase):
    def test_serial_table_has_volume_totals_row(self):
        result = serial_section_volumes([(0.0, 5.0, 0.0), (10.0, 5.0, 0.0)])
        table = RU.serial_section_table(result)
        self.assertEqual(table.rows[-1][0], "Объём, м3")
        self.assertEqual(table.rows[-1][2], "50.00")


class FoundationCheckTests(unittest.TestCase):
    def test_base_below_frost_is_adequate_when_confirmed(self):
        check = RU.assess_foundation_frost(
            base_depth_m=1.8, frost_depth_m=1.6, heaving=True, geotech_confirmed=True
        )
        self.assertTrue(check.adequate)

    def test_base_above_frost_on_heaving_soil_flags(self):
        check = RU.assess_foundation_frost(
            base_depth_m=1.0, frost_depth_m=1.6, heaving=True, geotech_confirmed=True
        )
        self.assertFalse(check.adequate)
        self.assertIn("ВЫШЕ ПРОМЕРЗАНИЯ", check.status)

    def test_frost_depth_computed_from_index_and_soil(self):
        check = RU.assess_foundation_frost(
            base_depth_m=2.0, soil_class=4, freezing_index=49.0,
            thermal_factor=1.0, heaving=True, geotech_confirmed=True,
        )
        self.assertAlmostEqual(check.frost_depth_m, 0.23 * 7.0, places=6)

    def test_unconfirmed_geotech_is_never_adequate(self):
        check = RU.assess_foundation_frost(
            base_depth_m=3.0, frost_depth_m=1.6, heaving=True, geotech_confirmed=False
        )
        self.assertFalse(check.adequate)

    def test_report_carries_non_certification(self):
        check = RU.assess_foundation_frost(base_depth_m=2.0, frost_depth_m=1.6)
        report = RU.foundation_check_report(check, True, False, True)
        self.assertIn("не сертифицирует", report)


class EarthworkAccountingTests(unittest.TestCase):
    def test_bulking_factors_by_soil(self):
        kp, kor = RU.bulking_factors(5)  # clay swells most
        self.assertGreater(kp, RU.bulking_factors(2)[0])  # > sand
        self.assertGreaterEqual(kor, 1.0)

    def test_soil_balance_report_shows_export(self):
        balance = soil_balance(100.0, 50.0)
        report = RU.soil_balance_report(balance, 4, 1.2, 1.05)
        self.assertIn("Баланс земляных масс", report)
        self.assertIn("вывоз", report.lower())

    def test_bill_table_totals(self):
        items = bill_of_quantities([("Срезка", 80.0), ("Насыпь", 40.0)])
        table = RU.bill_of_quantities_table(items)
        self.assertEqual(table.rows[-1], ("Итого", "120.00"))


class BackfillTextTests(unittest.TestCase):
    def test_backfill_report_has_schedule_and_citation(self):
        estimate = estimate_backfill(
            structure_area_m2=100.0, perimeter_m=40.0, working_space_m=0.6,
            depth_m=2.0, bedding_thickness_m=0.1, lift_thickness_m=0.3,
        )
        report = RU.backfill_report(estimate, 0.6, 2.0, 0.1)
        self.assertIn("Обратная засыпка", report)
        self.assertIn("СП 45.13330.2017", report)
        table = RU.backfill_schedule_table(estimate)
        self.assertEqual(table.rows[-1][0], "Итого")
        self.assertEqual(len(table.rows), len(estimate.layers) + 1)


class LayerPlanTests(unittest.TestCase):
    def test_cartogram_layer_keys_are_unique_and_complete(self):
        group = RU.cartogram_layers()
        keys = [spec.key for spec in group.layers]
        self.assertEqual(len(keys), len(set(keys)))
        for required in ("boundary", "grid_curves", "zero_work_lines", "cut_hatches",
                         "vertex_mark_tags", "cell_volume_tags", "table", "analysis_mesh"):
            self.assertIn(required, keys)

    def test_all_layer_groups_have_valid_specs(self):
        groups = [
            RU.cartogram_layers(),
            RU.pit_slope_layers(),
            RU.section_layers(),
            RU.serial_section_layers(),
            RU.topsoil_layers(),
            RU.working_space_layers(),
            RU.relief_layers(),
            RU.contour_layers(),
            RU.drainage_layers(),
            RU.ditch_layers(),
            RU.grading_layers(),
            RU.blind_area_layers(),
            RU.path_layers(),
            RU.foundation_drain_layers(),
            RU.titleblock_layers(),
        ]
        for group in groups:
            self.assertTrue(group.parent)
            for spec in group.layers:
                self.assertTrue(spec.name)
                self.assertEqual(len(spec.color), 3)
                self.assertGreaterEqual(spec.plot_weight_mm, 0.0)

    def test_sheet_sizes_and_titleblock_rows(self):
        self.assertEqual(RU.sheet_size_mm("A3"), (420.0, 297.0))
        self.assertEqual(RU.sheet_size_mm("unknown"), (420.0, 297.0))
        rows = RU.titleblock_rows({"object": "Дом", "title": "ПОР"})
        self.assertEqual(rows[0], ("Объект", "Дом"))
        self.assertEqual(len(rows), 5)


class TemporarySlopeTests(unittest.TestCase):
    def test_indicative_lookup_uses_depth_brackets(self):
        self.assertAlmostEqual(RU.indicative_allowable_slope(4, 3.0), 0.5)
        self.assertAlmostEqual(RU.indicative_allowable_slope(4, 4.0), 0.75)
        self.assertIsNone(RU.indicative_allowable_slope(4, 6.0))

    def test_within_allowable_when_flatter_and_confirmed(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=1.0, depth_m=3.0, soil_class=4, geotech_confirmed=True
        )
        self.assertTrue(check.within_allowable)
        self.assertAlmostEqual(check.governing_allowable_1_to, 0.5)

    def test_too_steep_when_steeper_than_allowable(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=0.3, depth_m=3.0, soil_class=4, geotech_confirmed=True
        )
        self.assertFalse(check.within_allowable)
        self.assertIn("СЛИШКОМ КРУТО", check.status)

    def test_groundwater_forces_review(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=2.0, depth_m=2.0, soil_class=4,
            groundwater=True, geotech_confirmed=True,
        )
        self.assertFalse(check.within_allowable)
        self.assertIn("ПРОВЕРКА", check.status)

    def test_deep_excavation_needs_calculation(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=2.0, depth_m=6.0, soil_class=4, geotech_confirmed=True
        )
        self.assertIsNone(check.indicative_allowable_1_to)
        self.assertIn("ПРОВЕРКА", check.status)

    def test_override_takes_precedence(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=0.8, depth_m=3.0, soil_class=4,
            allowable_override_1_to=0.75, geotech_confirmed=True,
        )
        self.assertAlmostEqual(check.governing_allowable_1_to, 0.75)
        self.assertTrue(check.within_allowable)

    def test_unconfirmed_geotech_is_never_within_allowable(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=2.0, depth_m=2.0, soil_class=4, geotech_confirmed=False
        )
        self.assertFalse(check.within_allowable)

    def test_report_always_carries_non_certification_note(self):
        check = RU.assess_temporary_slope(
            proposed_1_to=2.0, depth_m=2.0, soil_class=4, geotech_confirmed=True
        )
        self.assertTrue(any("не сертифицирует" in note for note in check.notes))
        report = RU.slope_check_report(check, False, False, True)
        self.assertIn("не сертифицирует", report)


if __name__ == "__main__":
    unittest.main()
