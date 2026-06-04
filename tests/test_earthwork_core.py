from __future__ import annotations

import unittest

from earthwork_core import (
    analyze_slopes,
    area_balance,
    backfill_layers,
    bill_of_quantities,
    build_section,
    calculate_cut_fill,
    classify_units,
    contour_segments,
    ditch_profile,
    ditch_volume,
    drainage_analysis,
    estimate_backfill,
    frost_depth,
    grade_by_points,
    grade_pad_grid,
    graded_pad_elevation,
    balanced_platform,
    hatch_polygon,
    mass_haul_curve,
    path_grades,
    platform_cut_fill,
    points_to_csv,
    polygon_perimeter,
    serial_section_volumes,
    slope_field,
    soil_balance,
    topsoil_strip,
    working_space_area,
)


class UnitClassificationTests(unittest.TestCase):
    def test_millimetre_model(self):
        units = classify_units(0.001, "Millimeters")
        self.assertTrue(units.reliable)
        self.assertEqual(units.units_per_meter, 1000.0)
        self.assertEqual(units.label, "mm")

    def test_metre_model(self):
        units = classify_units(1.0, "Meters")
        self.assertEqual(units.units_per_meter, 1.0)
        self.assertEqual(units.label, "m")

    def test_inch_model_is_supported(self):
        units = classify_units(0.0254, "Inches")
        self.assertTrue(units.reliable)
        self.assertAlmostEqual(units.units_per_meter, 1.0 / 0.0254, places=6)
        self.assertEqual(units.label, "in")

    def test_label_recognised_from_scale_without_name(self):
        units = classify_units(0.3048)  # feet, name omitted
        self.assertEqual(units.label, "ft")
        self.assertEqual(units.name, "Feet")

    def test_unitless_document_is_flagged_unreliable(self):
        for spec in (
            classify_units(0.0, "None"),
            classify_units(1.0, "no active document", reliable=False),
            classify_units(0.0, "Meters"),
            classify_units(None, "units unavailable", reliable=False),
        ):
            self.assertFalse(spec.reliable)
            self.assertEqual(spec.units_per_meter, 1.0)  # safe metre fallback

    def test_volumes_scale_identically_across_unit_systems(self):
        # The same physical site must give the same m3 whatever the model unit.
        def cutfill(upm):
            scale = upm  # 1 m expressed in model units
            return calculate_cut_fill(
                boundary=((0.0, 0.0), (20.0 * scale, 0.0),
                          (20.0 * scale, 20.0 * scale), (0.0, 20.0 * scale)),
                existing_z=lambda _x, _y: 0.0,
                proposed_z=lambda _x, _y: 0.5 * scale,
                grid_size_m=20.0,
                units_per_meter=upm,
            )

        metres = cutfill(1.0).fill_m3
        millimetres = cutfill(1000.0).fill_m3
        inches = cutfill(1.0 / 0.0254).fill_m3
        self.assertAlmostEqual(metres, 200.0, places=6)
        self.assertAlmostEqual(millimetres, 200.0, places=3)
        self.assertAlmostEqual(inches, 200.0, places=3)


class CutFillTests(unittest.TestCase):
    def test_uniform_fill_volume(self):
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 100.0,
            proposed_z=lambda _x, _y: 100.5,
            grid_size_m=20.0,
            samples_per_side=4,
        )

        self.assertEqual(len(result.cells), 1)
        self.assertAlmostEqual(result.fill_m3, 200.0)
        self.assertAlmostEqual(result.cut_m3, 0.0)
        self.assertAlmostEqual(result.balance_m3, 200.0)

    def test_millimetre_model_reports_metric_volumes(self):
        # Same 20 m x 20 m site and 0.5 m fill as the metres test, but every
        # coordinate and elevation is in millimetres (units_per_meter=1000).
        result = calculate_cut_fill(
            boundary=(
                (0.0, 0.0),
                (20000.0, 0.0),
                (20000.0, 20000.0),
                (0.0, 20000.0),
            ),
            existing_z=lambda _x, _y: 100000.0,
            proposed_z=lambda _x, _y: 100500.0,
            grid_size_m=20.0,
            samples_per_side=4,
            units_per_meter=1000.0,
        )

        self.assertEqual(len(result.cells), 1)
        self.assertAlmostEqual(result.fill_m3, 200.0, places=6)
        self.assertAlmostEqual(result.cut_m3, 0.0, places=6)
        self.assertAlmostEqual(result.grid_size_m, 20.0)
        # Grid lines stay in document units so the geometry overlays the model.
        self.assertAlmostEqual(result.cells[0].area_m2, 400.0, places=6)
        self.assertEqual(result.cells[0].corners[2].x, 20000.0)

    def test_mixed_cut_and_fill_are_kept_separate(self):
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 0.0,
            proposed_z=lambda x, _y: x - 10.0,
            grid_size_m=20.0,
            samples_per_side=20,
        )

        self.assertAlmostEqual(result.fill_m3, 1000.0, places=6)
        self.assertAlmostEqual(result.cut_m3, 1000.0, places=6)
        self.assertEqual(result.cells[0].classification, "mixed")
        self.assertEqual(len(result.zero_work_segments), 1)

    def test_flat_terrain_has_no_zero_work_line(self):
        # Untouched terrain (proposed == existing) is a "zero" cell and must not
        # produce a zero-work line, even with tiny floating-point noise.
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 155.06,
            proposed_z=lambda _x, _y: 155.06,
            grid_size_m=20.0,
            samples_per_side=4,
        )
        self.assertEqual(result.cells[0].classification, "zero")
        self.assertEqual(len(result.zero_work_segments), 0)

    def test_zero_work_line_only_in_mixed_cells(self):
        # Two columns: left all cut, right all fill. Neither single-sign cell may
        # carry a zero-work line; the line lives only where cut meets fill.
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 100.0,
            proposed_z=lambda x, _y: 100.0 + (x - 20.0) * 0.05,
            grid_size_m=20.0,
            samples_per_side=8,
        )
        classes = {(c.column): c.classification for c in result.cells}
        self.assertEqual(classes[0], "cut")
        self.assertEqual(classes[1], "fill")
        # The sign change is exactly on the shared grid line, not inside a cell.
        self.assertEqual(len(result.zero_work_segments), 0)

    def test_outside_boundary_cells_skip_corner_sampling(self):
        # Cells that lie entirely outside the site boundary must not probe the
        # terrain samplers - their corners can fall far from an irregular mesh.
        seen = []

        def recording_sampler(x, y):
            seen.append((x, y))
            return 0.0

        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (0.0, 20.0)),  # right triangle
            existing_z=recording_sampler,
            proposed_z=lambda _x, _y: 1.0,
            grid_size_m=10.0,
            samples_per_side=2,
        )

        # The cell spanning x[10,20] y[10,20] is wholly outside the triangle, so
        # its far corner (20, 20) must never be sampled.
        self.assertNotIn((20.0, 20.0), seen)
        self.assertNotIn((1, 1), {(cell.column, cell.row) for cell in result.cells})
        self.assertTrue(result.cells)

    def test_subcentimetre_noise_reads_as_flat(self):
        # ~3 mm of mesh-sampling noise must classify as flat, not shallow cut.
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 154.780,
            proposed_z=lambda _x, _y: 154.777,
            grid_size_m=20.0,
            samples_per_side=4,
        )
        self.assertEqual(result.cells[0].classification, "zero")
        self.assertEqual(result.fill_m3, 0.0)
        self.assertEqual(result.cut_m3, 0.0)

    def test_one_centimetre_difference_is_kept(self):
        # A real 1 cm raise is above the dead-band and must still register.
        result = calculate_cut_fill(
            boundary=((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
            existing_z=lambda _x, _y: 100.00,
            proposed_z=lambda _x, _y: 100.01,
            grid_size_m=20.0,
            samples_per_side=4,
        )
        self.assertEqual(result.cells[0].classification, "fill")
        self.assertAlmostEqual(result.fill_m3, 0.01 * 400.0, places=6)


class GradePadTests(unittest.TestCase):
    def test_inside_pad_is_flat(self):
        self.assertEqual(graded_pad_elevation(12.0, True, 0.0, 10.0, 2.0), 10.0)

    def test_outside_pad_clamps_to_transition_band(self):
        self.assertEqual(graded_pad_elevation(20.0, False, 4.0, 10.0, 2.0), 12.0)
        self.assertEqual(graded_pad_elevation(0.0, False, 4.0, 10.0, 2.0), 8.0)
        self.assertEqual(graded_pad_elevation(11.0, False, 4.0, 10.0, 2.0), 11.0)

    def test_grade_pad_grid_resamples_to_uniform_grid(self):
        # 10 m x 10 m terrain at z=0, square pad over the central 4..6 m, pad at
        # z=2, slope 1:1. Resampling at 1 m gives an 11x11 node grid that does not
        # depend on any source topology.
        def inside(x, y):
            return 4.0 <= x <= 6.0 and 4.0 <= y <= 6.0

        def distance(x, y):
            dx = max(4.0 - x, 0.0, x - 6.0)
            dy = max(4.0 - y, 0.0, y - 6.0)
            return (dx * dx + dy * dy) ** 0.5

        points, edited = grade_pad_grid(
            existing_z=lambda _x, _y: 0.0,
            inside_pad_at=inside,
            distance_to_pad_at=distance,
            origin=(0.0, 0.0),
            columns=10,
            rows=10,
            spacing=1.0,
            pad_elevation_m=2.0,
            slope_ratio=1.0,
        )

        self.assertEqual(len(points), 11 * 11)
        node = {(round(x, 6), round(y, 6)): z for x, y, z in points}
        self.assertEqual(node[(5.0, 5.0)], 2.0)            # pad centre is flat
        self.assertEqual(node[(0.0, 5.0)], 0.0)            # far ground untouched
        self.assertEqual(node[(7.0, 5.0)], 1.0)            # 1 m out, 1:1 -> +1 m
        self.assertGreater(edited, 0)

    def test_grade_pad_grid_rejects_degenerate_grid(self):
        with self.assertRaises(ValueError):
            grade_pad_grid(
                existing_z=lambda _x, _y: 0.0,
                inside_pad_at=lambda _x, _y: False,
                distance_to_pad_at=lambda _x, _y: 0.0,
                origin=(0.0, 0.0),
                columns=0,
                rows=5,
                spacing=1.0,
                pad_elevation_m=1.0,
                slope_ratio=1.0,
            )


class SlopeAnalysisTests(unittest.TestCase):
    def test_constant_slope_hachures_point_downhill(self):
        # z = -0.5 x: a 1:2 slope descending towards +x everywhere.
        analysis = analyze_slopes(
            sampler=lambda x, _y: -0.5 * x,
            origin=(0.0, 0.0),
            columns=4,
            rows=4,
            spacing=1.0,
            min_steepness=0.2,
            hachure_length=0.8,
        )
        self.assertEqual(analysis.slope_cell_count, 16)
        self.assertAlmostEqual(analysis.max_steepness, 0.5, places=6)
        self.assertAlmostEqual(analysis.max_slope_1_to, 2.0, places=6)
        for (start, end) in analysis.hachures:
            self.assertGreater(end[0], start[0])               # downhill is +x
            self.assertAlmostEqual(end[1], start[1], places=6)  # no cross-slope

    def test_hachures_anchor_at_top_edge_and_point_downhill(self):
        # z = -0.5 x: uphill is -x, so the crest (бровка) is the x=0 boundary.
        # Every hachure must start on that edge and tick downhill (+x).
        analysis = analyze_slopes(
            sampler=lambda x, _y: -0.5 * x,
            origin=(0.0, 0.0),
            columns=4,
            rows=4,
            spacing=1.0,
            min_steepness=0.2,
            hachure_length=0.5,
        )
        self.assertTrue(analysis.hachures)
        for (start, end) in analysis.hachures:
            self.assertAlmostEqual(start[0], 0.0)     # anchored on the crest
            self.assertGreater(end[0], start[0])      # ticking downhill (+x)

    def test_flat_surface_has_no_hachures(self):
        analysis = analyze_slopes(
            sampler=lambda _x, _y: 12.0,
            origin=(0.0, 0.0),
            columns=3,
            rows=3,
            spacing=1.0,
            min_steepness=0.2,
        )
        self.assertEqual(analysis.slope_cell_count, 0)
        self.assertEqual(analysis.hachures, ())
        self.assertEqual(analysis.outline, ())
        self.assertEqual(analysis.max_slope_1_to, 0.0)

    def test_gentle_slope_below_threshold_is_ignored(self):
        # 1:10 slope (steepness 0.1) is below a 1:5 (0.2) threshold.
        analysis = analyze_slopes(
            sampler=lambda x, _y: -0.1 * x,
            origin=(0.0, 0.0),
            columns=3,
            rows=3,
            spacing=1.0,
            min_steepness=0.2,
        )
        self.assertEqual(analysis.slope_cell_count, 0)
        self.assertAlmostEqual(analysis.max_steepness, 0.1, places=6)

    def test_missing_samples_skip_cells(self):
        # Sampler returns None on the right half: those cells must be skipped.
        def sampler(x, _y):
            return None if x > 2.0 else -0.5 * x

        analysis = analyze_slopes(
            sampler=sampler,
            origin=(0.0, 0.0),
            columns=4,
            rows=2,
            spacing=1.0,
            min_steepness=0.2,
        )
        for (start, _end) in analysis.hachures:
            self.assertLessEqual(start[0], 2.0)


class FrostDepthTests(unittest.TestCase):
    def test_frost_depth_formula(self):
        # d0=0.23 (loam), Mt=49 -> 0.23 * 7 = 1.61 m
        self.assertAlmostEqual(frost_depth(0.23, 49.0), 1.61)

    def test_frost_depth_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            frost_depth(0.0, 49.0)
        with self.assertRaises(ValueError):
            frost_depth(0.23, -1.0)


class MassHaulTests(unittest.TestCase):
    def test_balanced_platform_is_the_mean(self):
        self.assertAlmostEqual(balanced_platform([98.0, 100.0, 102.0]), 100.0)

    def test_platform_cut_fill_balances_at_mean(self):
        cut, fill = platform_cut_fill([98.0, 100.0, 102.0], 1.0, 100.0)
        self.assertAlmostEqual(cut, 2.0)
        self.assertAlmostEqual(fill, 2.0)

    def test_higher_platform_means_more_fill(self):
        cut, fill = platform_cut_fill([98.0, 100.0, 102.0], 1.0, 101.0)
        self.assertAlmostEqual(cut, 1.0)
        self.assertAlmostEqual(fill, 4.0)

    def test_mass_haul_curve_net_zero_at_balance(self):
        curve = mass_haul_curve([98.0, 100.0, 102.0], 1.0, [99.0, 100.0, 101.0])
        net_at_balance = [net for level, _c, _f, net in curve if abs(level - 100.0) < 1e-9][0]
        self.assertAlmostEqual(net_at_balance, 0.0)


class PathGradeTests(unittest.TestCase):
    def test_grades_and_steepest(self):
        # rises 0.5 over 10, then 1.5 over 10 -> 5% then 15%
        profile = path_grades([(0.0, 100.0), (10.0, 100.5), (20.0, 102.0)])
        self.assertAlmostEqual(profile.grades[0].grade_percent, 5.0)
        self.assertAlmostEqual(profile.grades[1].grade_percent, 15.0)
        self.assertAlmostEqual(profile.max_abs_grade_percent, 15.0)
        self.assertAlmostEqual(profile.length, 20.0)

    def test_downhill_grade_counts_by_magnitude(self):
        profile = path_grades([(0.0, 100.0), (10.0, 99.0)])
        self.assertAlmostEqual(profile.grades[0].grade_percent, -10.0)
        self.assertAlmostEqual(profile.max_abs_grade_percent, 10.0)

    def test_path_needs_two_stations(self):
        with self.assertRaises(ValueError):
            path_grades([(0.0, 1.0)])


class GradeByPointsTests(unittest.TestCase):
    def test_single_point_is_flat_at_its_elevation(self):
        grid = grade_by_points([(5.0, 5.0, 100.0)], (0.0, 0.0), 4, 4, 1.0)
        self.assertEqual(len(grid), 25)
        self.assertTrue(all(abs(z - 100.0) < 1e-9 for _x, _y, z in grid))

    def test_datum_shifts_the_whole_surface(self):
        grid = grade_by_points([(0.0, 0.0, 10.0)], (0.0, 0.0), 2, 2, 1.0, datum=2.5)
        self.assertTrue(all(abs(z - 12.5) < 1e-9 for _x, _y, z in grid))

    def test_node_at_design_point_is_exact(self):
        grid = grade_by_points(
            [(0.0, 0.0, 100.0), (4.0, 0.0, 104.0)], (0.0, 0.0), 4, 1, 1.0
        )
        node = {(round(x, 6), round(y, 6)): z for x, y, z in grid}
        self.assertAlmostEqual(node[(0.0, 0.0)], 100.0)
        self.assertAlmostEqual(node[(4.0, 0.0)], 104.0)
        # an interior node lies between the two design elevations
        self.assertTrue(100.0 < node[(2.0, 0.0)] < 104.0)

    def test_requires_a_design_point(self):
        with self.assertRaises(ValueError):
            grade_by_points([], (0.0, 0.0), 2, 2, 1.0)


class AreaBalanceTests(unittest.TestCase):
    def test_percentages_and_free_remainder(self):
        items = area_balance(1000.0, [("building", 200.0), ("paving", 150.0)])
        by_key = {i.key: i for i in items}
        self.assertAlmostEqual(by_key["building"].percent, 20.0)
        self.assertAlmostEqual(by_key["free"].area_m2, 650.0)
        self.assertAlmostEqual(by_key["free"].percent, 65.0)

    def test_plot_area_must_be_positive(self):
        with self.assertRaises(ValueError):
            area_balance(0.0, [("building", 100.0)])


class SoilBalanceTests(unittest.TestCase):
    def test_export_when_cut_exceeds_fill(self):
        balance = soil_balance(100.0, 50.0, initial_bulking=1.2, residual_bulking=1.05)
        self.assertAlmostEqual(balance.bank_for_fill_m3, 50.0 / 1.05, places=6)
        self.assertAlmostEqual(balance.export_bank_m3, 100.0 - 50.0 / 1.05, places=6)
        self.assertEqual(balance.import_bank_m3, 0.0)
        self.assertAlmostEqual(balance.cut_loose_m3, 120.0, places=6)
        self.assertAlmostEqual(
            balance.export_loose_m3, (100.0 - 50.0 / 1.05) * 1.2, places=6
        )

    def test_import_when_fill_exceeds_cut(self):
        balance = soil_balance(30.0, 50.0, initial_bulking=1.2, residual_bulking=1.05)
        self.assertAlmostEqual(balance.import_bank_m3, 50.0 / 1.05 - 30.0, places=6)
        self.assertEqual(balance.export_bank_m3, 0.0)
        self.assertGreater(balance.import_loose_m3, balance.import_bank_m3)

    def test_bulking_factors_must_be_positive(self):
        with self.assertRaises(ValueError):
            soil_balance(10.0, 5.0, initial_bulking=0.0)

    def test_bill_drops_empty_rows(self):
        items = bill_of_quantities([("Срезка", 80.0), ("Выемка", 0.0), ("Насыпь", 40.0)])
        self.assertEqual([i.name for i in items], ["Срезка", "Насыпь"])
        self.assertAlmostEqual(sum(i.volume_m3 for i in items), 120.0)


class BackfillTests(unittest.TestCase):
    def test_polygon_perimeter_of_rectangle(self):
        self.assertAlmostEqual(
            polygon_perimeter(((0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0))), 28.0
        )

    def test_working_space_area_minkowski(self):
        import math
        # perimeter 40 m, 0.6 m working space -> 40*0.6 + pi*0.36
        self.assertAlmostEqual(
            working_space_area(40.0, 0.6), 40.0 * 0.6 + math.pi * 0.36, places=6
        )

    def test_backfill_layers_split_into_lifts(self):
        layers = backfill_layers(1.0, 0.3)
        self.assertEqual(len(layers), 4)
        self.assertAlmostEqual(layers[-1].thickness_m, 0.1)
        self.assertAlmostEqual(layers[-1].top_m, 1.0)
        self.assertTrue(all(layer.thickness_m <= 0.3 + 1e-9 for layer in layers))

    def test_estimate_backfill_quantities(self):
        import math
        estimate = estimate_backfill(
            structure_area_m2=100.0,
            perimeter_m=40.0,
            working_space_m=0.6,
            depth_m=2.0,
            bedding_thickness_m=0.1,
            lift_thickness_m=0.3,
        )
        annulus = 40.0 * 0.6 + math.pi * 0.36
        self.assertAlmostEqual(estimate.annulus_area_m2, annulus, places=6)
        self.assertAlmostEqual(estimate.excavation_area_m2, 100.0 + annulus, places=6)
        self.assertAlmostEqual(
            estimate.bedding_volume_m3, (100.0 + annulus) * 0.1, places=6
        )
        self.assertAlmostEqual(estimate.backfill_volume_m3, annulus * 2.0, places=6)
        self.assertEqual(len(estimate.layers), 7)

    def test_backfill_layers_reject_bad_lift(self):
        with self.assertRaises(ValueError):
            backfill_layers(1.0, 0.0)


class TopsoilTests(unittest.TestCase):
    def test_strip_volume_is_area_times_depth(self):
        strip = topsoil_strip(
            ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),
            strip_depth_m=0.2,
        )
        self.assertAlmostEqual(strip.area_m2, 100.0)
        self.assertAlmostEqual(strip.volume_m3, 20.0)

    def test_strip_volume_in_millimetre_model(self):
        # Same 10 m x 10 m area, but coordinates in millimetres.
        strip = topsoil_strip(
            ((0.0, 0.0), (10000.0, 0.0), (10000.0, 10000.0), (0.0, 10000.0)),
            strip_depth_m=0.15,
            units_per_meter=1000.0,
        )
        self.assertAlmostEqual(strip.area_m2, 100.0, places=6)
        self.assertAlmostEqual(strip.volume_m3, 15.0, places=6)

    def test_negative_depth_rejected(self):
        with self.assertRaises(ValueError):
            topsoil_strip(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), strip_depth_m=-0.1)

    def test_hatch_segments_stay_inside_polygon(self):
        square = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
        segments = hatch_polygon(square, spacing=2.5, angle_deg=45.0)
        self.assertTrue(segments)
        for start, end in segments:
            for point in (start, end):
                self.assertGreaterEqual(point[0], -1e-6)
                self.assertLessEqual(point[0], 10.0 + 1e-6)
                self.assertGreaterEqual(point[1], -1e-6)
                self.assertLessEqual(point[1], 10.0 + 1e-6)

    def test_hatch_spacing_must_be_positive(self):
        with self.assertRaises(ValueError):
            hatch_polygon(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), spacing=0.0)


class SerialSectionTests(unittest.TestCase):
    def test_constant_area_volume_is_prismatic(self):
        # 5 m2 cut at three stations 10 m apart -> 5 * 20 = 100 m3.
        result = serial_section_volumes([(0.0, 5.0, 0.0), (10.0, 5.0, 0.0), (20.0, 5.0, 0.0)])
        self.assertAlmostEqual(result.cut_volume, 100.0)
        self.assertAlmostEqual(result.fill_volume, 0.0)

    def test_average_end_area_between_stations(self):
        # Areas 0, 5, 0 at 0/10/20 m -> (0+5)/2*10 + (5+0)/2*10 = 50 m3.
        result = serial_section_volumes([(0.0, 0.0, 2.0), (10.0, 5.0, 1.0), (20.0, 0.0, 0.0)])
        self.assertAlmostEqual(result.cut_volume, 50.0)
        self.assertAlmostEqual(result.fill_volume, 0.5 * (2 + 1) * 10 + 0.5 * (1 + 0) * 10)

    def test_unsorted_stations_are_ordered(self):
        result = serial_section_volumes([(20.0, 0.0, 0.0), (0.0, 4.0, 0.0), (10.0, 4.0, 0.0)])
        self.assertAlmostEqual(result.cut_volume, 0.5 * 8 * 10 + 0.5 * 4 * 10)
        self.assertEqual(result.stations[0][0], 0.0)

    def test_empty_serial_sections_rejected(self):
        with self.assertRaises(ValueError):
            serial_section_volumes([])


class SlopeFieldTests(unittest.TestCase):
    def test_tilted_plane_field_points_downhill(self):
        # z = -0.5 x -> steepness 0.5 everywhere, downhill +x, mean z sensible.
        samples = slope_field(lambda x, _y: -0.5 * x, (0.0, 0.0), 3, 3, 1.0)
        self.assertEqual(len(samples), 9)
        for s in samples:
            self.assertAlmostEqual(s.steepness, 0.5, places=6)
            self.assertAlmostEqual(s.downhill_x, 1.0, places=6)
            self.assertAlmostEqual(s.downhill_y, 0.0, places=6)

    def test_flat_field_has_zero_direction(self):
        samples = slope_field(lambda _x, _y: 7.0, (0.0, 0.0), 2, 2, 1.0)
        self.assertEqual(len(samples), 4)
        for s in samples:
            self.assertEqual(s.steepness, 0.0)
            self.assertEqual((s.downhill_x, s.downhill_y), (0.0, 0.0))
            self.assertAlmostEqual(s.z, 7.0)

    def test_off_mesh_cells_are_skipped(self):
        samples = slope_field(
            lambda x, _y: None if x > 1.5 else -0.5 * x, (0.0, 0.0), 3, 1, 1.0
        )
        self.assertTrue(all(s.x <= 1.5 for s in samples))


class PointsCsvTests(unittest.TestCase):
    def test_csv_uses_period_decimals_and_comma(self):
        text = points_to_csv([(1.5, -2.25, 100.125), (0.0, 0.0, 0.0)], decimals=3)
        self.assertEqual(text, "1.500,-2.250,100.125\n0.000,0.000,0.000")

    def test_csv_respects_decimals_and_delimiter(self):
        text = points_to_csv([(1.23456, 2.0, 3.0)], delimiter=";", decimals=2)
        self.assertEqual(text, "1.23;2.00;3.00")

    def test_csv_ignores_extra_point_fields(self):
        text = points_to_csv([(1.0, 2.0, 3.0, "label")], decimals=1)
        self.assertEqual(text, "1.0,2.0,3.0")


class DitchTests(unittest.TestCase):
    def test_fixed_depth_invert_follows_ground(self):
        profile = ditch_profile(
            [(0.0, 100.0), (10.0, 100.5), (20.0, 101.0)], depth=0.5
        )
        self.assertAlmostEqual(profile.stations[0].invert_z, 99.5)
        self.assertAlmostEqual(profile.stations[2].invert_z, 100.5)
        self.assertTrue(all(abs(s.depth - 0.5) < 1e-9 for s in profile.stations))
        self.assertEqual(profile.daylight_count, 0)

    def test_designed_slope_and_daylight_flag(self):
        # Flat ground at 100; invert starts at 99 and rises 10%/length -> daylights.
        profile = ditch_profile(
            [(0.0, 100.0), (5.0, 100.0), (20.0, 100.0)],
            start_invert=99.0, longitudinal_slope=-0.1,
        )
        # invert = 99 - (-0.1)*d = 99 + 0.1 d; at d=20 -> 101 (above ground 100)
        self.assertAlmostEqual(profile.stations[-1].invert_z, 101.0)
        self.assertGreaterEqual(profile.daylight_count, 1)

    def test_trapezoidal_volume(self):
        # Constant 1 m depth, bottom 0.4, side 1.5 over 10 m:
        # area = 0.4*1 + 1.5*1^2 = 1.9 m2; volume = 1.9*10 = 19 m3.
        profile = ditch_profile([(0.0, 5.0), (10.0, 5.0)], depth=1.0)
        self.assertAlmostEqual(ditch_volume(profile, 0.4, 1.5), 19.0)

    def test_ditch_needs_two_stations(self):
        with self.assertRaises(ValueError):
            ditch_profile([(0.0, 1.0)], depth=0.5)


class DrainageTests(unittest.TestCase):
    def test_bowl_has_a_central_low_point(self):
        import math as _m
        analysis = drainage_analysis(
            lambda x, y: _m.hypot(x - 5.0, y - 5.0), (0.0, 0.0), 10, 10, 1.0
        )
        lows = {(p.x, p.y) for p in analysis.low_points}
        self.assertEqual(lows, {(5.0, 5.0)})  # single sink at the bowl centre
        self.assertTrue(analysis.flow_paths)

    def test_dome_has_a_central_high_point(self):
        import math as _m
        analysis = drainage_analysis(
            lambda x, y: -_m.hypot(x - 5.0, y - 5.0), (0.0, 0.0), 10, 10, 1.0
        )
        highs = {(p.x, p.y) for p in analysis.high_points}
        self.assertIn((5.0, 5.0), highs)

    def test_flow_traces_descend(self):
        # z = x: every flow path runs to lower x (downhill).
        analysis = drainage_analysis(
            lambda x, _y: x, (0.0, 0.0), 6, 6, 1.0, seed_every=2
        )
        self.assertTrue(analysis.flow_paths)
        for path in analysis.flow_paths:
            xs = [point[0] for point in path]
            self.assertTrue(all(xs[k] >= xs[k + 1] for k in range(len(xs) - 1)))

    def test_flat_surface_has_no_extrema(self):
        analysis = drainage_analysis(lambda _x, _y: 3.0, (0.0, 0.0), 4, 4, 1.0)
        self.assertEqual(analysis.low_points, ())
        self.assertEqual(analysis.high_points, ())


class ContourTests(unittest.TestCase):
    def test_tilted_plane_contours_are_at_level(self):
        # z = x over [0,4]; the level-2 contour is the vertical line x = 2.
        segments = contour_segments(lambda x, _y: x, (0.0, 0.0), 4, 4, 1.0, 1.0, base=0.0)
        level2 = [(s, e) for level, s, e in segments if abs(level - 2.0) < 1e-9]
        self.assertTrue(level2)
        for start, end in level2:
            self.assertAlmostEqual(start[0], 2.0)
            self.assertAlmostEqual(end[0], 2.0)

    def test_flat_surface_has_no_contours(self):
        self.assertEqual(
            contour_segments(lambda _x, _y: 5.0, (0.0, 0.0), 3, 3, 1.0, 1.0), ()
        )

    def test_interval_must_be_positive(self):
        with self.assertRaises(ValueError):
            contour_segments(lambda x, _y: x, (0.0, 0.0), 2, 2, 1.0, 0.0)


class SectionTests(unittest.TestCase):
    def test_pit_section_is_all_cut(self):
        # Existing flat at 0; proposed dips to -2 at the middle (a pit profile).
        section = build_section([(0.0, 0.0, 0.0), (5.0, 0.0, -2.0), (10.0, 0.0, 0.0)])
        self.assertAlmostEqual(section.cut_area, 10.0)   # triangle 0.5*10*2
        self.assertAlmostEqual(section.fill_area, 0.0)
        self.assertEqual(len(section.existing_line), 3)
        self.assertEqual(len(section.proposed_line), 3)
        self.assertAlmostEqual(section.length, 10.0)
        self.assertAlmostEqual(section.min_z, -2.0)

    def test_crossing_section_splits_cut_and_fill(self):
        # Proposed rises from -1 to +1 across flat ground: cut then fill, equal.
        section = build_section([(0.0, 0.0, -1.0), (10.0, 0.0, 1.0)])
        self.assertAlmostEqual(section.cut_area, 2.5)
        self.assertAlmostEqual(section.fill_area, 2.5)
        self.assertEqual(len(section.cut_regions), 1)
        self.assertEqual(len(section.fill_regions), 1)

    def test_existing_only_section_has_no_regions(self):
        section = build_section([(0.0, 1.0, None), (4.0, 3.0, None)])
        self.assertEqual(section.proposed_line, ())
        self.assertEqual(section.cut_regions, ())
        self.assertEqual(section.fill_regions, ())
        self.assertEqual(section.cut_area, 0.0)
        self.assertEqual(section.fill_area, 0.0)

    def test_section_needs_two_stations(self):
        with self.assertRaises(ValueError):
            build_section([(0.0, 1.0, 0.0)])


if __name__ == "__main__":
    unittest.main()

