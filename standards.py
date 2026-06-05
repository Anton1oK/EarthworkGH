"""Country/standard layer: all code-specific rules, language and layer plans.

The engineering geometry in ``earthwork_core`` and the Rhino plumbing in
``rhino_adapter`` are deliberately neutral - no regulation text, no localised
strings, no layer names. Everything tied to a particular country's standards
lives here, behind a ``Standard`` interface, so another country can be added by
writing a new ``Standard`` subclass and registering it. ``RU`` (Russian SPDS /
GOST / SP) is the first implementation; it is the default.
"""

from __future__ import annotations

from dataclasses import dataclass

from earthwork_core import QuantityTable, _format_m3, area_balance, frost_depth


@dataclass(frozen=True)
class LayerSpec:
    """A drawing layer: which output category it holds and how it looks."""

    key: str
    name: str
    color: tuple
    plot_weight_mm: float = 0.0


@dataclass(frozen=True)
class LayerGroup:
    """A parent layer with its child layer specs, in draw order."""

    parent: str
    layers: tuple[LayerSpec, ...]


@dataclass(frozen=True)
class FoundationCheck:
    """A frost-depth foundation check: a working aid, never a certification."""

    base_depth_m: float
    frost_depth_m: "float | None"
    status: str
    adequate: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SlopeCheck:
    """A temporary-slope check result. A working aid, never a certification."""

    soil_class: "int | None"
    soil_name: str
    depth_m: float
    proposed_1_to: float
    indicative_allowable_1_to: "float | None"
    governing_allowable_1_to: "float | None"
    status: str
    within_allowable: bool
    notes: tuple[str, ...]


class Standard:
    """Interface a country standard must provide. See ``RussianStandard``."""

    code = ""
    name = ""
    locale = ""
    allowed_grid_sides_m: tuple = ()

    # The regulation editions this standard encodes, and when they were last
    # reviewed - national metadata, surfaced in the output provenance stamp.
    regulations: tuple = ()
    checked_on = ""

    # Volumes are computed in m3 internally; ``volume_factor`` converts m3 to the
    # standard's display unit for the baked cell tags (1.0 keeps m3; US uses yd3).
    volume_factor = 1.0

    def edition_stamp(self):
        """Editions + checked-on date for the provenance line (national text)."""

        label = "standard {}".format(self.code) if self.code else "standard"
        if self.regulations:
            label += ": " + ", ".join(self.regulations)
        if self.checked_on:
            label += "; checked {}".format(self.checked_on)
        return label

    # The methods below are implemented per country.
    def cartogram_warnings(self, grid_size_m):
        raise NotImplementedError

    def cartogram_report(self, result):
        raise NotImplementedError

    def earth_mass_table(self, result):
        raise NotImplementedError

    def cartogram_layers(self):
        raise NotImplementedError


class RussianStandard(Standard):
    """Russian SPDS standard: GOST 21.508-2020, SP 45.13330.2017, SP 82.13330.2016."""

    code = "RU"
    name = "СПДС (ГОСТ/СП, Россия)"
    locale = "ru"
    allowed_grid_sides_m = (10.0, 20.0, 25.0, 40.0, 50.0)
    volume_label = "м3"  # unit suffix on cell-volume tags
    regulations = (
        "ГОСТ 21.508-2020",
        "СП 45.13330.2017",
        "СП 82.13330.2016",
        "ГОСТ Р 21.101-2020",
    )
    checked_on = "2026-06"

    # -- Cartogram (GOST 21.508-2020) --------------------------------------
    def cartogram_warnings(self, grid_size_m):
        warnings = []
        if not any(abs(grid_size_m - side) < 1e-9 for side in self.allowed_grid_sides_m):
            warnings.append(
                "Шаг сетки не входит в перечень 10, 20, 25, 40 или 50 м "
                "по ГОСТ 21.508-2020 п. 8.3. Используйте его как рабочий "
                "расчетный шаг или обоснуйте иной метод."
            )
        warnings.append(
            "Объемы по границе участка аппроксимированы подячейками; "
            "для выпуска документации проверьте граничные фигуры."
        )
        return tuple(warnings)

    def cartogram_report(self, result):
        lines = [
            "Картограмма земляных масс",
            "Метод: сетка квадратов, ГОСТ 21.508-2020, раздел 8",
            "Шаг сетки: {:.3f} м".format(result.grid_size_m),
            "Насыпь (+): {:.3f} м3".format(result.fill_m3),
            "Выемка (-): {:.3f} м3".format(result.cut_m3),
            "Баланс (+насыпь/-выемка): {:.3f} м3".format(result.balance_m3),
            "Число расчетных ячеек: {}".format(len(result.cells)),
        ]
        warnings = self.cartogram_warnings(result.grid_size_m)
        if warnings:
            lines.append("Предупреждения:")
            lines.extend("- {}".format(item) for item in warnings)
        return "\n".join(lines)

    def earth_mass_table(self, result):
        header = ("Колонка", "Насыпь, м3", "Выемка, м3", "Баланс, м3")
        rows = [
            (
                str(total.column),
                _format_m3(total.fill_m3),
                _format_m3(total.cut_m3),
                _format_m3(total.fill_m3 - total.cut_m3),
            )
            for total in result.column_totals
        ]
        rows.append(
            (
                "Итого",
                _format_m3(result.fill_m3),
                _format_m3(result.cut_m3),
                _format_m3(result.balance_m3),
            )
        )
        return QuantityTable(header=header, rows=tuple(rows))

    def cartogram_layers(self):
        return LayerGroup(
            parent="Картограмма земляных масс",
            layers=(
                LayerSpec("boundary", "Граница участка", (0, 0, 0), 0.35),
                LayerSpec("grid_curves", "Сетка квадратов", (128, 128, 128), 0.13),
                LayerSpec("zero_work_lines", "Линия нулевых работ", (0, 90, 200), 0.50),
                LayerSpec("cut_hatches", "Штриховка выемки", (200, 70, 60), 0.13),
                LayerSpec("vertex_mark_tags", "Отметки углов", (20, 20, 20), 0.0),
                LayerSpec("cell_volume_tags", "Объёмы ячеек", (130, 0, 0), 0.0),
                LayerSpec("table", "Ведомость объёмов", (0, 0, 0), 0.18),
                LayerSpec("analysis_mesh", "Анализ (предпросмотр)", (200, 200, 200), 0.0),
            ),
        )

    # -- Grading pad (SP 45.13330.2017) ------------------------------------
    def grade_pad_report(self, pad_elevation_m, slope_ratio, resolution_m, edited):
        warnings = [
            "Крутизна откоса 1:{:.3f} задана пользователем.".format(slope_ratio),
            "Проверить откос по СП 45.13330.2017 п. 6.1.10 и приложению В "
            "с учетом грунтов, воды, глубины и нагрузки у бровки.",
        ]
        report = "\n".join(
            [
                "Площадка вертикальной планировки",
                "Отметка площадки: {:.3f} м".format(pad_elevation_m),
                "Заложение откоса: 1:{:.3f}".format(slope_ratio),
                "Шаг пересчета сетки: {:.3f} м".format(resolution_m),
                "Изменено узлов сетки: {}".format(edited),
            ]
        )
        return report, warnings

    # -- Pit slopes (SP 45.13330.2017) -------------------------------------
    def slope_report(
        self, grid_size_m, columns, rows, slope_cells, min_slope_1_to,
        max_slope_1_to, hachure_count,
    ):
        lines = [
            "Откосы котлована",
            "Шаг анализа: {:.3f} м".format(grid_size_m),
            "Расчётных ячеек: {} ({} x {})".format(columns * rows, columns, rows),
            "Ячеек откосов: {}".format(slope_cells),
            "Порог уклона: круче 1:{:.2f}".format(min_slope_1_to),
        ]
        if max_slope_1_to > 0.0:
            lines.append("Наибольший уклон: 1:{:.2f}".format(max_slope_1_to))
        else:
            lines.append("Наибольший уклон: площадка ровная или нет данных на сетке")
        lines.append("Штрихов откосов: {}".format(hachure_count))
        if hachure_count == 0 and max_slope_1_to > 0.0:
            lines.append(
                "Уклоны положе порога. Задайте min_slope_1_to не меньше {:.1f} "
                "или уменьшите grid_size_m.".format(max_slope_1_to)
            )
        elif hachure_count == 0:
            lines.append(
                "Откосы не найдены: проверьте, что сетка попадает на меш, "
                "и уменьшите grid_size_m."
            )
        lines.append(
            "Откосы не сертифицированы: проверить по СП 45.13330.2017, "
            "приложение В, с учётом грунтов, воды, глубины и нагрузки."
        )
        return "\n".join(lines)

    def pit_slope_layers(self):
        return LayerGroup(
            parent="Котлован",
            layers=(
                LayerSpec("hachures", "Откосы", (200, 70, 60), 0.13),
                LayerSpec("outline", "Контур откосов", (0, 0, 0), 0.35),
            ),
        )

    # -- Profile section ---------------------------------------------------
    def section_report(self, length_m, station_count, cut_area_m2, fill_area_m2, has_proposed):
        lines = [
            "Разрез по линии",
            "Длина разреза: {:.3f} м".format(length_m),
            "Станций: {}".format(station_count),
        ]
        if has_proposed:
            lines.append("Выемка (сечение): {:.3f} м2".format(cut_area_m2))
            lines.append("Насыпь (сечение): {:.3f} м2".format(fill_area_m2))
        else:
            lines.append("Проектный меш не задан: показан только существующий рельеф.")
        return "\n".join(lines)

    def section_layers(self):
        return LayerGroup(
            parent="Разрез",
            layers=(
                LayerSpec("existing", "Существующий рельеф", (90, 60, 30), 0.25),
                LayerSpec("proposed", "Проектный рельеф", (0, 90, 200), 0.35),
                LayerSpec("cut", "Выемка", (200, 70, 60), 0.13),
                LayerSpec("fill", "Насыпь", (73, 156, 84), 0.13),
            ),
        )

    # -- Serial sections ---------------------------------------------------
    def serial_section_table(self, result):
        header = ("Сечение", "Расст., м", "Выемка, м2", "Насыпь, м2")
        rows = [
            (
                str(index + 1),
                "{:.2f}".format(distance),
                _format_m3(cut_area),
                _format_m3(fill_area),
            )
            for index, (distance, cut_area, fill_area) in enumerate(result.stations)
        ]
        rows.append(
            ("Объём, м3", "", _format_m3(result.cut_volume), _format_m3(result.fill_volume))
        )
        return QuantityTable(header=header, rows=tuple(rows))

    def serial_section_report(self, result, spacing_m):
        return "\n".join(
            [
                "Серия поперечных сечений",
                "Шаг сечений: {:.3f} м".format(spacing_m),
                "Метод: средних площадей (average end area)",
                "",
                self.serial_section_table(result).render_text(),
            ]
        )

    def serial_section_empty_report(self):
        return "Ни одно сечение не пересекает существующий меш."

    def serial_section_layers(self):
        return LayerGroup(
            parent="Серия разрезов",
            layers=(
                LayerSpec("lines", "Линии сечений", (140, 140, 140), 0.13),
                LayerSpec("existing", "Существующий рельеф", (90, 60, 30), 0.25),
                LayerSpec("proposed", "Проектный рельеф", (0, 90, 200), 0.35),
            ),
        )

    # -- Topsoil (SP 82.13330.2016) ----------------------------------------
    def topsoil_report(self, strip_depth_m, area_m2, volume_m3):
        return "\n".join(
            [
                "Ведомость снятия растительного слоя",
                "Глубина снятия: {:.3f} м".format(strip_depth_m),
                "Площадь снятия: {:.2f} м2".format(area_m2),
                "Объём растительного слоя: {:.2f} м3".format(volume_m3),
                "Растительный слой подлежит складированию для повторного "
                "использования (СП 82.13330.2016).",
            ]
        )

    def topsoil_label(self, strip_depth_m, area_m2, volume_m3):
        return "Снятие растительного слоя\nh={:.2f} м, S={:.1f} м2, V={:.1f} м3".format(
            strip_depth_m, area_m2, volume_m3
        )

    def topsoil_layers(self):
        return LayerGroup(
            parent="Растительный слой",
            layers=(
                LayerSpec("boundary", "Граница снятия", (0, 0, 0), 0.35),
                LayerSpec("hatch", "Штриховка снятия", (120, 90, 40), 0.13),
                LayerSpec("label", "Ведомость", (0, 0, 0), 0.0),
            ),
        )

    # -- Ditch / swale (SP 32.13330 drainage channels) --------------------
    def ditch_invert_label(self, invert_z_m):
        return "Дк {:.2f}".format(invert_z_m)

    def ditch_report(self, profile, bottom_width_m, side_slope, volume_m3, meters_per_unit):
        lines = [
            "Кювет / лоток водоотвода",
            "Ширина по дну: {:.2f} м".format(bottom_width_m),
            "Заложение откоса: 1:{:.2f}".format(side_slope),
            "Глубина: {:.2f}..{:.2f} м".format(
                profile.min_depth * meters_per_unit, profile.max_depth * meters_per_unit
            ),
            "Объём выемки: {:.2f} м3".format(volume_m3),
            "Отметки дна: Дк (дно кювета).",
        ]
        if profile.daylight_count:
            lines.append(
                "Предупреждение: дно выше земли на {} станции(ях) — "
                "требуется заглубление или досыпка.".format(profile.daylight_count)
            )
        return "\n".join(lines)

    def ditch_layers(self):
        return LayerGroup(
            parent="Водоотвод",
            layers=(
                LayerSpec("invert", "Дно кювета", (0, 120, 210), 0.30),
                LayerSpec("edges", "Бровки кювета", (90, 140, 200), 0.13),
                LayerSpec("marks", "Отметки дна", (20, 20, 20), 0.0),
            ),
        )

    # -- Drainage (flow traces, ponding) ----------------------------------
    def drainage_report(self, grid_size_m, flow_count, low_count, high_count):
        lines = [
            "Водоотвод и сток",
            "Шаг сетки: {:.3f} м".format(grid_size_m),
            "Линий стока: {}".format(flow_count),
            "Локальных понижений (застой воды): {}".format(low_count),
            "Локальных повышений: {}".format(high_count),
        ]
        if low_count:
            lines.append(
                "Предупреждение: возможен застой воды в {} точке(ах) — "
                "предусмотреть водоотвод (СП 82.13330.2016).".format(low_count)
            )
        return "\n".join(lines)

    def drainage_layers(self):
        return LayerGroup(
            parent="Водоотвод",
            layers=(
                LayerSpec("flow", "Линии стока", (0, 120, 210), 0.18),
                LayerSpec("low", "Понижения (застой)", (210, 50, 50), 0.0),
                LayerSpec("high", "Повышения", (130, 130, 130), 0.0),
            ),
        )

    # -- Vertical-planning authoring --------------------------------------
    def grading_report(self, point_count, datum_m, min_z_m, max_z_m):
        return "\n".join(
            [
                "Проектная поверхность (вертикальная планировка)",
                "Опорных отметок: {}".format(point_count),
                "Отметка +-0.000 (датум): {:.3f} м".format(datum_m),
                "Диапазон отметок: {:.2f}..{:.2f} м".format(min_z_m, max_z_m),
            ]
        )

    def grading_layers(self):
        return LayerGroup(
            parent="Вертикальная планировка",
            layers=(
                LayerSpec("surface", "Проектная поверхность", (73, 156, 84), 0.0),
            ),
        )

    def blind_area_report(self, width_m, slope_percent, perimeter_m, area_m2):
        return "\n".join(
            [
                "Отмостка",
                "Ширина: {:.2f} м".format(width_m),
                "Уклон от здания: {:.1f} %".format(slope_percent),
                "Периметр: {:.2f} м, площадь: {:.2f} м2".format(perimeter_m, area_m2),
                "Уклон отмостки принимать 1-10 % от здания (СП 82.13330.2016).",
            ]
        )

    def mass_haul_report(self, balanced_m, platform_m, cut_m3, fill_m3):
        return "\n".join(
            [
                "Подбор отметки площадки (+-0.000)",
                "Отметка нулевого баланса: {:.3f} м".format(balanced_m),
                "Принятая отметка площадки: {:.3f} м".format(platform_m),
                "При принятой отметке — выемка: {:.2f} м3, насыпь: {:.2f} м3".format(
                    cut_m3, fill_m3
                ),
                "Баланс (выемка-насыпь): {:.2f} м3".format(cut_m3 - fill_m3),
            ]
        )

    path_default_max_grade_percent = 8.0  # проезды; tighten for footways

    def path_grade_label(self, grade_percent):
        return "{:.0f}‰".format(grade_percent * 10.0)  # промилле (‰)

    def path_grade_report(self, profile, max_allowed_percent, compliant):
        lines = [
            "Продольный профиль проезда/дорожки",
            "Длина: {:.2f} м".format(profile.length),
            "Наибольший уклон: {:.1f} % ({:.0f} промилле)".format(
                profile.max_abs_grade_percent, profile.max_abs_grade_percent * 10.0
            ),
            "Предельный уклон: {:.1f} %".format(max_allowed_percent),
            "Соответствие: {}".format("в норме" if compliant else "ПРЕВЫШЕНИЕ уклона"),
        ]
        if not compliant:
            lines.append(
                "Уклон превышает предельный — пересмотреть трассу или продольный профиль."
            )
        return "\n".join(lines)

    def path_layers(self):
        return LayerGroup(
            parent="Проезды и дорожки",
            layers=(
                LayerSpec("edges", "Кромки проезда", (90, 90, 90), 0.18),
                LayerSpec("marks", "Уклоны", (0, 90, 200), 0.0),
            ),
        )

    def blind_area_layers(self):
        return LayerGroup(
            parent="Вертикальная планировка",
            layers=(
                LayerSpec("outer", "Отмостка (контур)", (0, 0, 0), 0.25),
                LayerSpec("inner", "Отмостка (у здания)", (120, 120, 120), 0.13),
            ),
        )

    # -- Contours (organization of relief) --------------------------------
    def contour_report(self, interval_m, minor_count, major_count, levels_m):
        low = min(levels_m) if levels_m else 0.0
        high = max(levels_m) if levels_m else 0.0
        return "\n".join(
            [
                "Горизонтали (организация рельефа)",
                "Сечение рельефа: {:.3f} м".format(interval_m),
                "Горизонталей: {} (основных {})".format(minor_count + major_count, major_count),
                "Диапазон отметок: {:.2f}..{:.2f} м".format(low, high),
            ]
        )

    def contour_layers(self):
        return LayerGroup(
            parent="Рельеф",
            layers=(
                LayerSpec("minor", "Горизонтали", (140, 110, 60), 0.13),
                LayerSpec("major", "Горизонтали основные", (110, 80, 40), 0.30),
            ),
        )

    # -- Relief preview (slope arrows + spot elevations) -------------------
    def relief_report(self, grid_size_m, sample_count, max_slope_percent, arrow_count):
        return "\n".join(
            [
                "Рельеф: уклоны и отметки",
                "Шаг сетки: {:.3f} м".format(grid_size_m),
                "Точек рельефа: {}".format(sample_count),
                "Стрелок уклона: {}".format(arrow_count),
                "Наибольший уклон: {:.1f} %".format(max_slope_percent),
            ]
        )

    def relief_layers(self):
        return LayerGroup(
            parent="Рельеф",
            layers=(
                LayerSpec("arrows", "Стрелки уклонов", (0, 90, 200), 0.13),
                LayerSpec("spots", "Отметки рельефа", (20, 20, 20), 0.0),
            ),
        )

    # -- Foundation bedding / backfill (SP 45.13330.2017, раздел 7) ---------
    working_space_default = 0.6
    bedding_thickness_default = 0.1
    lift_thickness_default = 0.3

    def backfill_schedule_table(self, estimate):
        header = ("Слой", "Низ, м", "Верх, м", "Толщина, м", "Объём, м3")
        rows = [
            (
                str(layer.index),
                "{:.2f}".format(layer.bottom_m),
                "{:.2f}".format(layer.top_m),
                "{:.2f}".format(layer.thickness_m),
                _format_m3(estimate.annulus_area_m2 * layer.thickness_m),
            )
            for layer in estimate.layers
        ]
        rows.append(("Итого", "", "", "", _format_m3(estimate.backfill_volume_m3)))
        return QuantityTable(header=header, rows=tuple(rows))

    def backfill_report(self, estimate, working_space_m, depth_m, bedding_thickness_m):
        return "\n".join(
            [
                "Обратная засыпка и подготовка основания",
                "Рабочее пространство: {:.2f} м".format(working_space_m),
                "Площадь основания (с рабочим пространством): {:.2f} м2".format(
                    estimate.excavation_area_m2
                ),
                "Объём подготовки (подушки), h={:.2f} м: {:.2f} м3".format(
                    bedding_thickness_m, estimate.bedding_volume_m3
                ),
                "Объём обратной засыпки, h={:.2f} м: {:.2f} м3".format(
                    depth_m, estimate.backfill_volume_m3
                ),
                "Засыпка послойно с уплотнением (СП 45.13330.2017, раздел 7).",
                "",
                self.backfill_schedule_table(estimate).render_text(),
            ]
        )

    def working_space_layers(self):
        return LayerGroup(
            parent="Котлован",
            layers=(
                LayerSpec("excavation", "Контур котлована (низ)", (0, 0, 0), 0.35),
                LayerSpec("structure", "Контур сооружения", (0, 90, 200), 0.25),
            ),
        )

    # -- Sheet frame + title block (ГОСТ Р 21.101) ------------------------
    _sheet_sizes_mm = {
        "A4": (210.0, 297.0),
        "A3": (420.0, 297.0),
        "A2": (594.0, 420.0),
        "A1": (841.0, 594.0),
        "A0": (1189.0, 841.0),
    }

    def sheet_size_mm(self, code):
        return self._sheet_sizes_mm.get(str(code).upper(), (420.0, 297.0))

    def titleblock_rows(self, values):
        """(label, value) rows, top to bottom, for a simplified main title block."""
        return (
            ("Объект", values.get("object", "")),
            ("Наименование листа", values.get("title", "")),
            ("Стадия / Масштаб", values.get("stage_scale", "")),
            ("Лист", values.get("sheet_number", "")),
            ("Разработал, дата", values.get("author", "")),
        )

    def titleblock_layers(self):
        return LayerGroup(
            parent="Оформление листа",
            layers=(
                LayerSpec("frame", "Рамка", (0, 0, 0), 0.50),
                LayerSpec("titleblock", "Штамп", (0, 0, 0), 0.35),
                LayerSpec("text", "Текст штампа", (0, 0, 0), 0.0),
            ),
        )

    # -- Site area balance (ТЭП) ------------------------------------------
    _tep_labels = {
        "building": "Застройка",
        "paving": "Покрытия (проезды, дорожки)",
        "other": "Прочее (террасы, площадки)",
        "free": "Озеленение (свободная территория)",
    }

    def tep_table(self, plot_area_m2, item_areas):
        items = area_balance(plot_area_m2, item_areas, free_key="free")
        header = ("Показатель", "Площадь, м2", "%")
        rows = [("Площадь участка", "{:.2f}".format(plot_area_m2), "100.0")]
        rows += [
            (
                self._tep_labels.get(item.key, item.key),
                "{:.2f}".format(item.area_m2),
                "{:.1f}".format(item.percent),
            )
            for item in items
        ]
        return QuantityTable(header=header, rows=tuple(rows))

    def tep_report(self, table):
        return "Технико-экономические показатели (ТЭП)\n" + table.render_text()

    # -- Frost-depth foundation check (SP 22.13330.2016) ------------------
    # Soil coefficient d0 (m) for dfn = d0 * sqrt(Mt), per soil class.
    _frost_d0 = {1: 0.28, 2: 0.30, 3: 0.28, 4: 0.23, 5: 0.23, 6: 0.28}

    def frost_d0(self, soil_class):
        return self._frost_d0.get(int(soil_class), 0.23) if soil_class else 0.23

    def assess_foundation_frost(
        self, base_depth_m, frost_depth_m=None, soil_class=None, freezing_index=None,
        thermal_factor=1.1, heaving=True, groundwater=False, geotech_confirmed=False,
    ):
        base_depth_m = float(base_depth_m)
        design_frost = None if frost_depth_m is None else float(frost_depth_m)
        if design_frost is None and freezing_index is not None:
            design_frost = float(thermal_factor) * frost_depth(
                self.frost_d0(soil_class), freezing_index
            )

        notes = []
        adequate = False
        if design_frost is None:
            status = "ТРЕБУЕТСЯ ПРОВЕРКА (нет глубины промерзания)"
            notes.append(
                "Задайте frost_depth_m или индекс промерзания Mt и класс грунта."
            )
        elif not heaving:
            status = "Грунт непучинистый — заглубление по расчёту основания, не по промерзанию"
            adequate = True
        elif base_depth_m + 1e-9 >= design_frost:
            status = "Подошва ниже глубины промерзания"
            adequate = True
        else:
            status = (
                "ПОДОШВА ВЫШЕ ПРОМЕРЗАНИЯ ({:.2f} < {:.2f} м) — на пучинистом грунте "
                "нужны заглубление или мероприятия (утепление, замена грунта)".format(
                    base_depth_m, design_frost
                )
            )

        if groundwater:
            notes.append("Грунтовые воды усиливают морозное пучение — учесть в расчёте.")
        if not geotech_confirmed:
            adequate = False
            notes.append("Геологические данные не подтверждены (geotech_confirmed=false).")
        notes.append(
            "Инструмент не сертифицирует основание. Решение — по СП 22.13330.2016 "
            "(морозное пучение) с геологией и проектом."
        )
        return FoundationCheck(base_depth_m, design_frost, status, adequate, tuple(notes))

    def foundation_check_report(self, check, heaving, groundwater, geotech_confirmed):
        def yes_no(flag):
            return "да" if flag else "нет"

        lines = [
            "Проверка заложения фундамента по промерзанию",
            "Глубина заложения подошвы: {:.2f} м".format(check.base_depth_m),
            "Расчётная глубина промерзания: {}".format(
                "не задана" if check.frost_depth_m is None
                else "{:.2f} м".format(check.frost_depth_m)
            ),
            "Результат: {}".format(check.status),
            "",
            "Исходные данные:",
            " - Грунт пучинистый: {}".format(yes_no(heaving)),
            " - Грунтовые воды: {}".format(yes_no(groundwater)),
            " - Геология подтверждена: {}".format(yes_no(geotech_confirmed)),
            "",
            "Примечания:",
        ]
        lines.extend(" - {}".format(note) for note in check.notes)
        return "\n".join(lines)

    def foundation_drain_report(self, offset_m, depth_below_m, length_m, invert_m):
        return "\n".join(
            [
                "Пристенный (кольцевой) дренаж фундамента",
                "Отступ от стены: {:.2f} м".format(offset_m),
                "Заглубление дрены ниже подошвы/отметки: {:.2f} м".format(depth_below_m),
                "Отметка лотка дрены: {:.3f} м".format(invert_m),
                "Длина дрены: {:.2f} м".format(length_m),
                "Уклон дрены к выпуску принимать не менее 0,5 % (СП 22.13330.2016).",
            ]
        )

    def foundation_drain_layers(self):
        return LayerGroup(
            parent="Дренаж",
            layers=(
                LayerSpec("drain", "Дренажная линия", (0, 150, 200), 0.30),
            ),
        )

    # -- Earthwork accounting (bulking / soil balance) --------------------
    # (initial bulking Kp, residual bulking Kor) per soil class - indicative,
    # from СНиП/ГЭСН ranges; confirm against the project soil report.
    _bulking = {
        1: (1.15, 1.03),
        2: (1.12, 1.03),
        3: (1.15, 1.04),
        4: (1.20, 1.05),
        5: (1.27, 1.06),
        6: (1.20, 1.05),
    }

    def bulking_factors(self, soil_class):
        return self._bulking.get(int(soil_class), (1.2, 1.05)) if soil_class else (1.2, 1.05)

    def soil_balance_report(self, balance, soil_class, initial_bulking, residual_bulking):
        lines = [
            "Баланс земляных масс",
            "Грунт: {} (класс {})".format(
                self.soil_name(soil_class), "—" if not soil_class else soil_class
            ),
            "Кр (первонач. разрыхление): {:.2f}; Кор (остаточное): {:.2f}".format(
                initial_bulking, residual_bulking
            ),
            "Выемка (плотное тело): {:.2f} м3".format(balance.cut_bank_m3),
            "Насыпь (уплотнённая): {:.2f} м3".format(balance.fill_compacted_m3),
            "Грунта на насыпь (плотное тело): {:.2f} м3".format(balance.bank_for_fill_m3),
        ]
        if balance.export_bank_m3 > 1e-9:
            lines.append(
                "Избыток (вывоз): {:.2f} м3 плотн. ({:.2f} м3 в разрыхл.)".format(
                    balance.export_bank_m3, balance.export_loose_m3
                )
            )
        elif balance.import_bank_m3 > 1e-9:
            lines.append(
                "Недостаток (привоз): {:.2f} м3 плотн. ({:.2f} м3 в разрыхл.)".format(
                    balance.import_bank_m3, balance.import_loose_m3
                )
            )
        else:
            lines.append("Баланс нулевой (грунт уравновешен).")
        lines.append(
            "Объём разработки в разрыхлённом виде (транспорт): {:.2f} м3".format(
                balance.cut_loose_m3
            )
        )
        return "\n".join(lines)

    _bill_labels = {
        "topsoil": "Срезка растительного слоя",
        "cut": "Разработка выемки (котлован/планировка)",
        "fill": "Устройство насыпи",
        "backfill": "Обратная засыпка",
        "ditch": "Разработка кюветов и лотков",
    }

    def bill_label(self, key):
        return self._bill_labels.get(key, key)

    def bill_of_quantities_table(self, items):
        header = ("Наименование работ", "Объём, м3")
        rows = [(item.name, _format_m3(item.volume_m3)) for item in items]
        total = sum(item.volume_m3 for item in items)
        rows.append(("Итого", _format_m3(total)))
        return QuantityTable(header=header, rows=tuple(rows))

    # -- Temporary slope assessment (SP 45.13330.2017, прил. В) -------------
    _soils = {
        1: "Насыпные неслежавшиеся",
        2: "Песчаные",
        3: "Супесь",
        4: "Суглинок",
        5: "Глина",
        6: "Лёссовые",
    }
    # (max_depth_m, allowable заложение m in 1:m) - indicative, reference only.
    _temp_slope_table = {
        1: ((1.5, 0.67), (3.0, 1.0), (5.0, 1.25)),
        2: ((1.5, 0.5), (3.0, 1.0), (5.0, 1.0)),
        3: ((1.5, 0.25), (3.0, 0.67), (5.0, 0.85)),
        4: ((1.5, 0.0), (3.0, 0.5), (5.0, 0.75)),
        5: ((1.5, 0.0), (3.0, 0.25), (5.0, 0.5)),
        6: ((1.5, 0.0), (3.0, 0.5), (5.0, 0.5)),
    }

    def soil_name(self, soil_class):
        return self._soils.get(soil_class, "не задан") if soil_class else "не задан"

    def indicative_allowable_slope(self, soil_class, depth_m):
        brackets = self._temp_slope_table.get(int(soil_class)) if soil_class else None
        if brackets is None:
            return None
        for max_depth, allowable_m in brackets:
            if float(depth_m) <= max_depth + 1e-9:
                return allowable_m
        return None

    def assess_temporary_slope(
        self, proposed_1_to, depth_m, soil_class=None, allowable_override_1_to=None,
        groundwater=False, surcharge=False, geotech_confirmed=False,
    ):
        proposed_1_to = float(proposed_1_to)
        depth_m = float(depth_m)
        soil_class = None if soil_class is None else int(soil_class)
        indicative = (
            None if soil_class is None
            else self.indicative_allowable_slope(soil_class, depth_m)
        )
        governing = (
            float(allowable_override_1_to)
            if allowable_override_1_to is not None
            else indicative
        )

        notes = []
        review_required = False
        if depth_m > 5.0:
            review_required = True
            notes.append(
                "Глубина свыше 5 м — табличные откосы не применяются, нужен расчёт устойчивости."
            )
        if groundwater:
            review_required = True
            notes.append(
                "Грунтовые воды у выработки — нужны водопонижение и расчёт; табличные откосы неприменимы."
            )
        if surcharge:
            review_required = True
            notes.append("Нагрузка у бровки — требуется учёт пригрузки и расчёт.")
        if governing is None:
            review_required = True
            notes.append(
                "Допустимый откос не определён: задайте soil_class или allowable_slope_1_to из геологического отчёта."
            )

        within_allowable = False
        if review_required:
            status = "ТРЕБУЕТСЯ ПРОВЕРКА (расчёт/геология)"
        elif proposed_1_to + 1e-9 >= governing:
            status = "В пределах допустимого (подтвердить геологией)"
            within_allowable = True
        else:
            status = "СЛИШКОМ КРУТО — положе допустимого 1:{:.2f}".format(governing)

        if not geotech_confirmed:
            within_allowable = False
            notes.append("Геологические данные не подтверждены (geotech_confirmed=false).")

        notes.append(
            "Инструмент не сертифицирует откос. Решение — по СП 45.13330.2017 "
            "(раздел 6, приложение В) с геологией и проектом."
        )

        return SlopeCheck(
            soil_class=soil_class,
            soil_name=self.soil_name(soil_class),
            depth_m=depth_m,
            proposed_1_to=proposed_1_to,
            indicative_allowable_1_to=indicative,
            governing_allowable_1_to=governing,
            status=status,
            within_allowable=within_allowable,
            notes=tuple(notes),
        )

    def slope_check_report(self, check, groundwater, surcharge, geotech_confirmed):
        def yes_no(flag):
            return "да" if flag else "нет"

        def fmt_slope(value):
            return "не определён" if value is None else "1:{:.2f}".format(value)

        lines = [
            "Оценка крутизны временного откоса",
            "Грунт: {} (класс {})".format(
                check.soil_name, "—" if check.soil_class is None else check.soil_class
            ),
            "Глубина выработки: {:.2f} м".format(check.depth_m),
            "Принятый откос: 1:{:.2f}".format(check.proposed_1_to),
            "Ориентировочный допустимый (таблица): {}".format(
                fmt_slope(check.indicative_allowable_1_to)
            ),
            "Принятый к проверке допустимый: {}".format(
                fmt_slope(check.governing_allowable_1_to)
            ),
            "Результат: {}".format(check.status),
            "",
            "Чек-лист исходных данных:",
            " - Грунтовые воды у выработки: {}".format(yes_no(groundwater)),
            " - Пригрузка/нагрузка у бровки: {}".format(yes_no(surcharge)),
            " - Геология подтверждена: {}".format(yes_no(geotech_confirmed)),
            "",
            "Примечания:",
        ]
        lines.extend(" - {}".format(note) for note in check.notes)
        return "\n".join(lines)


class GenericStandard(RussianStandard):
    """A metric, English starter standard - proves a second country plugs in.

    Identity, units, grid validation, the cut/fill report/table and the layer
    names are English/generic; the remaining report strings inherit the Russian
    text and are a localisation to-do (override per method to fully localise).
    """

    code = "INT"
    name = "International (generic, metric)"
    locale = "en"
    allowed_grid_sides_m = ()
    volume_label = "m3"
    regulations = ("generic metric defaults - no national code encoded",)
    checked_on = "2026-06"

    _EN = {
        "Картограмма земляных масс": "Earthwork cut/fill plan",
        "Котлован": "Excavation pit",
        "Разрез": "Section",
        "Серия разрезов": "Cross-sections",
        "Растительный слой": "Topsoil",
        "Рельеф": "Relief",
        "Водоотвод": "Drainage",
        "Вертикальная планировка": "Grading",
        "Проезды и дорожки": "Driveways & paths",
        "Дренаж": "Subsoil drainage",
        "Оформление листа": "Sheet",
        "Граница участка": "Site boundary",
        "Сетка квадратов": "Square grid",
        "Линия нулевых работ": "Zero-work line",
        "Штриховка выемки": "Cut hatch",
        "Отметки углов": "Corner marks",
        "Объёмы ячеек": "Cell volumes",
        "Ведомость объёмов": "Volume table",
        "Анализ (предпросмотр)": "Analysis (preview)",
        "Откосы": "Slopes",
        "Контур откосов": "Slope outline",
        "Существующий рельеф": "Existing ground",
        "Проектный рельеф": "Proposed ground",
        "Выемка": "Cut",
        "Насыпь": "Fill",
        "Линии сечений": "Section lines",
        "Граница снятия": "Strip boundary",
        "Штриховка снятия": "Strip hatch",
        "Ведомость": "Schedule",
        "Стрелки уклонов": "Slope arrows",
        "Отметки рельефа": "Spot elevations",
        "Горизонтали": "Contours",
        "Горизонтали основные": "Index contours",
        "Линии стока": "Flow lines",
        "Понижения (застой)": "Low points (ponding)",
        "Повышения": "High points",
        "Дно кювета": "Ditch invert",
        "Бровки кювета": "Ditch edges",
        "Отметки дна": "Invert marks",
        "Проектная поверхность": "Proposed surface",
        "Отмостка (контур)": "Apron (outer)",
        "Отмостка (у здания)": "Apron (inner)",
        "Кромки проезда": "Path edges",
        "Уклоны": "Grades",
        "Дренажная линия": "Drain line",
        "Контур котлована (низ)": "Excavation outline (bottom)",
        "Контур сооружения": "Structure outline",
        "Рамка": "Frame",
        "Штамп": "Title block",
        "Текст штампа": "Title block text",
    }

    def _en_group(self, group):
        return LayerGroup(
            self._EN.get(group.parent, group.parent),
            tuple(
                LayerSpec(s.key, self._EN.get(s.name, s.name), s.color, s.plot_weight_mm)
                for s in group.layers
            ),
        )

    def cartogram_warnings(self, grid_size_m):
        return (
            "Cell volumes near the boundary are sub-sampled; verify boundary "
            "figures before issuing documentation.",
        )

    def cartogram_report(self, result):
        lines = [
            "Earthwork cut/fill plan (square-grid method)",
            "Grid step: {:.3f} m".format(result.grid_size_m),
            "Fill (+): {:.3f} m3".format(result.fill_m3),
            "Cut (-): {:.3f} m3".format(result.cut_m3),
            "Balance: {:.3f} m3".format(result.balance_m3),
            "Cells: {}".format(len(result.cells)),
        ]
        return "\n".join(lines + ["Notes:"] + ["- " + w for w in self.cartogram_warnings(result.grid_size_m)])

    def earth_mass_table(self, result):
        header = ("Column", "Fill, m3", "Cut, m3", "Balance, m3")
        rows = [
            (str(t.column), _format_m3(t.fill_m3), _format_m3(t.cut_m3),
             _format_m3(t.fill_m3 - t.cut_m3))
            for t in result.column_totals
        ]
        rows.append(("Total", _format_m3(result.fill_m3), _format_m3(result.cut_m3),
                     _format_m3(result.balance_m3)))
        return QuantityTable(header=header, rows=tuple(rows))

    def soil_name(self, soil_class):
        names = {1: "Fill (uncompacted)", 2: "Sand", 3: "Sandy loam",
                 4: "Loam", 5: "Clay", 6: "Loess"}
        return names.get(soil_class, "unspecified") if soil_class else "unspecified"


# English layer-group overrides for GenericStandard (translate the RU groups).
for _layer_method in (
    "cartogram_layers", "pit_slope_layers", "section_layers", "serial_section_layers",
    "topsoil_layers", "relief_layers", "contour_layers", "drainage_layers",
    "ditch_layers", "grading_layers", "blind_area_layers", "path_layers",
    "foundation_drain_layers", "working_space_layers", "titleblock_layers",
):
    def _make_layer_override(method_name):
        def override(self):
            return self._en_group(getattr(RussianStandard, method_name)(self))
        return override

    setattr(GenericStandard, _layer_method, _make_layer_override(_layer_method))


class USStandard(GenericStandard):
    """United States standard - imperial units (cubic yards, feet) and US codes.

    Volumes are reported in cubic yards (CY), areas in square feet (SF), lengths
    in feet (ft); excavation slopes use OSHA Type A/B/C; frost depth follows the
    local frost line (IBC); driveway/accessibility grades reference ADA. Inherits
    English layer names from GenericStandard. The analysis grid and elevation
    inputs are still entered in metres (a deeper change); the imperial conversion
    is applied to all reported quantities and the baked cell tags.
    """

    code = "US"
    name = "United States (imperial)"
    locale = "en-US"
    allowed_grid_sides_m = ()
    volume_label = "CY"
    volume_factor = 1.307950619  # m3 -> cubic yards
    regulations = (
        "OSHA 29 CFR 1926 Subpart P",
        "IBC 2021 (frost line)",
        "IRC R401/R403",
        "ADA / ICC A117.1",
    )
    checked_on = "2026-06"

    # -- imperial conversions (internal SI -> display) ---------------------
    def _v(self, cubic_metres):
        return float(cubic_metres) * 1.307950619  # CY

    def _a(self, square_metres):
        return float(square_metres) * 10.763910417  # SF

    def _l(self, metres):
        return float(metres) * 3.280839895  # ft

    # -- cartogram (imperial) ----------------------------------------------
    def cartogram_report(self, result):
        return "\n".join([
            "Earthwork cut/fill plan (grid method)",
            "Grid step: {:.1f} ft".format(self._l(result.grid_size_m)),
            "Fill (+): {:.1f} CY".format(self._v(result.fill_m3)),
            "Cut (-): {:.1f} CY".format(self._v(result.cut_m3)),
            "Balance: {:.1f} CY".format(self._v(result.balance_m3)),
            "Cells: {}".format(len(result.cells)),
        ])

    def earth_mass_table(self, result):
        header = ("Column", "Fill, CY", "Cut, CY", "Balance, CY")
        rows = [
            (str(t.column), _format_m3(self._v(t.fill_m3)), _format_m3(self._v(t.cut_m3)),
             _format_m3(self._v(t.fill_m3 - t.cut_m3)))
            for t in result.column_totals
        ]
        rows.append(("Total", _format_m3(self._v(result.fill_m3)),
                     _format_m3(self._v(result.cut_m3)), _format_m3(self._v(result.balance_m3))))
        return QuantityTable(header=header, rows=tuple(rows))

    # -- grading pad -------------------------------------------------------
    def grade_pad_report(self, pad_elevation_m, slope_ratio, resolution_m, edited):
        warnings = [
            "Side slope {:.2f}H:1V set by user.".format(slope_ratio),
            "Verify cut/fill slopes per OSHA 29 CFR 1926 Subpart P with the geotechnical report.",
        ]
        report = "\n".join([
            "Grading pad",
            "Pad elevation: {:.2f} ft".format(self._l(pad_elevation_m)),
            "Side slope: {:.2f}H:1V".format(slope_ratio),
            "Resample step: {:.2f} ft".format(self._l(resolution_m)),
            "Grid nodes edited: {}".format(edited),
        ])
        return report, warnings

    # -- pit slopes (OSHA) -------------------------------------------------
    def slope_report(self, grid_size_m, columns, rows, slope_cells, min_slope_1_to,
                     max_slope_1_to, hachure_count):
        lines = [
            "Excavation slopes",
            "Analysis step: {:.2f} ft".format(self._l(grid_size_m)),
            "Analysis cells: {} ({} x {})".format(columns * rows, columns, rows),
            "Slope cells: {}".format(slope_cells),
            "Threshold: steeper than {:.2f}H:1V".format(min_slope_1_to),
        ]
        if max_slope_1_to > 0.0:
            lines.append("Steepest slope: {:.2f}H:1V".format(max_slope_1_to))
        else:
            lines.append("Steepest slope: flat or no data on the grid")
        lines.append("Slope hachures: {}".format(hachure_count))
        lines.append("Slopes are not certified: verify per OSHA 29 CFR 1926 "
                     "Subpart P with soil type, water and surcharge.")
        return "\n".join(lines)

    # -- sections ----------------------------------------------------------
    def section_report(self, length_m, station_count, cut_area_m2, fill_area_m2, has_proposed):
        lines = [
            "Section along line",
            "Section length: {:.1f} ft".format(self._l(length_m)),
            "Stations: {}".format(station_count),
        ]
        if has_proposed:
            lines.append("Cut (section area): {:.1f} SF".format(self._a(cut_area_m2)))
            lines.append("Fill (section area): {:.1f} SF".format(self._a(fill_area_m2)))
        else:
            lines.append("No proposed mesh: existing ground only.")
        return "\n".join(lines)

    def serial_section_table(self, result):
        header = ("Section", "Dist, ft", "Cut, SF", "Fill, SF")
        rows = [
            (str(index + 1), "{:.1f}".format(self._l(distance)),
             _format_m3(self._a(cut_area)), _format_m3(self._a(fill_area)))
            for index, (distance, cut_area, fill_area) in enumerate(result.stations)
        ]
        rows.append(("Volume, CY", "", _format_m3(self._v(result.cut_volume)),
                     _format_m3(self._v(result.fill_volume))))
        return QuantityTable(header=header, rows=tuple(rows))

    def serial_section_report(self, result, spacing_m):
        return "\n".join([
            "Cross-sections",
            "Section spacing: {:.1f} ft".format(self._l(spacing_m)),
            "Method: average end area",
            "",
            self.serial_section_table(result).render_text(),
        ])

    def serial_section_empty_report(self):
        return "No section crosses the existing mesh."

    # -- topsoil -----------------------------------------------------------
    def topsoil_report(self, strip_depth_m, area_m2, volume_m3):
        return "\n".join([
            "Topsoil stripping",
            "Strip depth: {:.2f} ft".format(self._l(strip_depth_m)),
            "Strip area: {:.0f} SF".format(self._a(area_m2)),
            "Topsoil volume: {:.1f} CY".format(self._v(volume_m3)),
            "Stockpile topsoil for reuse and protect per the SWPPP / local code.",
        ])

    def topsoil_label(self, strip_depth_m, area_m2, volume_m3):
        return "Topsoil strip\nh={:.2f} ft, A={:.0f} SF, V={:.1f} CY".format(
            self._l(strip_depth_m), self._a(area_m2), self._v(volume_m3))

    # -- ditch -------------------------------------------------------------
    def ditch_invert_label(self, invert_z_m):
        return "INV {:.1f}".format(self._l(invert_z_m))

    def ditch_report(self, profile, bottom_width_m, side_slope, volume_m3, meters_per_unit):
        lines = [
            "Ditch / swale",
            "Bottom width: {:.2f} ft".format(self._l(bottom_width_m)),
            "Side slope: {:.2f}H:1V".format(side_slope),
            "Depth: {:.2f}..{:.2f} ft".format(
                self._l(profile.min_depth * meters_per_unit),
                self._l(profile.max_depth * meters_per_unit)),
            "Excavation volume: {:.1f} CY".format(self._v(volume_m3)),
            "Invert marks: INV.",
        ]
        if profile.daylight_count:
            lines.append("Warning: invert above ground at {} station(s) - lower the "
                         "invert or add fill.".format(profile.daylight_count))
        return "\n".join(lines)

    # -- drainage / relief / contours --------------------------------------
    def drainage_report(self, grid_size_m, flow_count, low_count, high_count):
        lines = [
            "Drainage and runoff",
            "Grid step: {:.1f} ft".format(self._l(grid_size_m)),
            "Flow paths: {}".format(flow_count),
            "Local low points (ponding): {}".format(low_count),
            "Local high points: {}".format(high_count),
        ]
        if low_count:
            lines.append("Warning: possible ponding at {} point(s) - provide positive "
                         "drainage.".format(low_count))
        return "\n".join(lines)

    def relief_report(self, grid_size_m, sample_count, max_slope_percent, arrow_count):
        return "\n".join([
            "Relief: slopes and spot elevations",
            "Grid step: {:.1f} ft".format(self._l(grid_size_m)),
            "Spot points: {}".format(sample_count),
            "Slope arrows: {}".format(arrow_count),
            "Steepest slope: {:.1f} %".format(max_slope_percent),
        ])

    def contour_report(self, interval_m, minor_count, major_count, levels_m):
        low = min(levels_m) if levels_m else 0.0
        high = max(levels_m) if levels_m else 0.0
        return "\n".join([
            "Proposed contours",
            "Contour interval: {:.2f} ft".format(self._l(interval_m)),
            "Contours: {} (index {})".format(minor_count + major_count, major_count),
            "Elevation range: {:.2f}..{:.2f} ft".format(self._l(low), self._l(high)),
        ])

    # -- grading / blind area / driveway / mass haul -----------------------
    def grading_report(self, point_count, datum_m, min_z_m, max_z_m):
        return "\n".join([
            "Proposed grading surface",
            "Design spot elevations: {}".format(point_count),
            "Datum (0.00): {:.2f} ft".format(self._l(datum_m)),
            "Elevation range: {:.2f}..{:.2f} ft".format(self._l(min_z_m), self._l(max_z_m)),
        ])

    def blind_area_report(self, width_m, slope_percent, perimeter_m, area_m2):
        return "\n".join([
            "Foundation perimeter grading (apron)",
            "Width: {:.2f} ft".format(self._l(width_m)),
            "Slope away from building: {:.1f} %".format(slope_percent),
            "Perimeter: {:.1f} ft, area: {:.0f} SF".format(self._l(perimeter_m), self._a(area_m2)),
            "Grade away from the building >= 5% for the first 10 ft (IRC R401.3).",
        ])

    def mass_haul_report(self, balanced_m, platform_m, cut_m3, fill_m3):
        return "\n".join([
            "Balanced platform (0.00)",
            "Zero-balance elevation: {:.2f} ft".format(self._l(balanced_m)),
            "Chosen platform elevation: {:.2f} ft".format(self._l(platform_m)),
            "At this elevation - cut: {:.1f} CY, fill: {:.1f} CY".format(
                self._v(cut_m3), self._v(fill_m3)),
            "Balance (cut-fill): {:.1f} CY".format(self._v(cut_m3 - fill_m3)),
        ])

    path_default_max_grade_percent = 12.0  # typical residential driveway max

    def path_grade_label(self, grade_percent):
        return "{:.1f}%".format(grade_percent)

    def path_grade_report(self, profile, max_allowed_percent, compliant):
        lines = [
            "Driveway / path profile",
            "Length: {:.1f} ft".format(self._l(profile.length)),
            "Steepest grade: {:.1f} %".format(profile.max_abs_grade_percent),
            "Max allowed grade: {:.1f} %".format(max_allowed_percent),
            "Compliance: {}".format("OK" if compliant else "EXCEEDS max grade"),
        ]
        if not compliant:
            lines.append("Grade exceeds the limit - revise the alignment or profile. "
                         "(ADA accessible route <= 5%, ramp <= 8.33%.)")
        return "\n".join(lines)

    # -- bedding / backfill ------------------------------------------------
    working_space_default = 0.6
    bedding_thickness_default = 0.1
    lift_thickness_default = 0.2

    def backfill_schedule_table(self, estimate):
        header = ("Lift", "Bottom, ft", "Top, ft", "Thick, ft", "Volume, CY")
        rows = [
            (str(layer.index), "{:.2f}".format(self._l(layer.bottom_m)),
             "{:.2f}".format(self._l(layer.top_m)), "{:.2f}".format(self._l(layer.thickness_m)),
             _format_m3(self._v(estimate.annulus_area_m2 * layer.thickness_m)))
            for layer in estimate.layers
        ]
        rows.append(("Total", "", "", "", _format_m3(self._v(estimate.backfill_volume_m3))))
        return QuantityTable(header=header, rows=tuple(rows))

    def backfill_report(self, estimate, working_space_m, depth_m, bedding_thickness_m):
        return "\n".join([
            "Bedding and backfill",
            "Working space: {:.2f} ft".format(self._l(working_space_m)),
            "Excavation footprint (with working space): {:.0f} SF".format(
                self._a(estimate.excavation_area_m2)),
            "Bedding volume, h={:.2f} ft: {:.1f} CY".format(
                self._l(bedding_thickness_m), self._v(estimate.bedding_volume_m3)),
            "Backfill volume, h={:.2f} ft: {:.1f} CY".format(
                self._l(depth_m), self._v(estimate.backfill_volume_m3)),
            "Place backfill in compacted lifts (per spec / OSHA Subpart P).",
            "",
            self.backfill_schedule_table(estimate).render_text(),
        ])

    # -- sheet sizes (ANSI / ARCH) + title block ---------------------------
    _sheet_sizes_mm = {
        "ARCH A": (304.8, 228.6), "ARCH B": (457.2, 304.8), "ARCH C": (609.6, 457.2),
        "ARCH D": (914.4, 609.6), "ARCH E": (1219.2, 914.4),
        "ANSI A": (279.4, 215.9), "ANSI B": (431.8, 279.4), "ANSI C": (558.8, 431.8),
        "ANSI D": (863.6, 558.8), "ANSI E": (1117.6, 863.6),
        "A4": (210.0, 297.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
        "A1": (841.0, 594.0), "A0": (1189.0, 841.0),
    }

    def sheet_size_mm(self, code):
        return self._sheet_sizes_mm.get(str(code).upper(), (914.4, 609.6))  # ARCH D

    def titleblock_rows(self, values):
        return (
            ("Project", values.get("object", "")),
            ("Sheet title", values.get("title", "")),
            ("Phase / Scale", values.get("stage_scale", "")),
            ("Sheet", values.get("sheet_number", "")),
            ("Drawn by, date", values.get("author", "")),
        )

    # -- site area / lot coverage ------------------------------------------
    _tep_labels = {
        "building": "Building footprint",
        "paving": "Paving (drives, walks)",
        "other": "Other (decks, patios)",
        "free": "Landscape (pervious)",
    }

    def tep_table(self, plot_area_m2, item_areas):
        items = area_balance(plot_area_m2, item_areas, free_key="free")
        header = ("Item", "Area, SF", "%")
        rows = [("Lot area", "{:.0f}".format(self._a(plot_area_m2)), "100.0")]
        rows += [
            (self._tep_labels.get(item.key, item.key), "{:.0f}".format(self._a(item.area_m2)),
             "{:.1f}".format(item.percent))
            for item in items
        ]
        return QuantityTable(header=header, rows=tuple(rows))

    def tep_report(self, table):
        return "Site area / lot coverage\n" + table.render_text()

    # -- frost-depth foundation check (IBC) --------------------------------
    def assess_foundation_frost(self, base_depth_m, frost_depth_m=None, soil_class=None,
                                freezing_index=None, thermal_factor=1.1, heaving=True,
                                groundwater=False, geotech_confirmed=False):
        base_depth_m = float(base_depth_m)
        design_frost = None if frost_depth_m is None else float(frost_depth_m)
        if design_frost is None and freezing_index is not None:
            design_frost = float(thermal_factor) * frost_depth(
                self.frost_d0(soil_class), freezing_index)

        notes = []
        adequate = False
        if design_frost is None:
            status = "REVIEW REQUIRED (no frost depth)"
            notes.append("Enter the local frost line depth (IBC / local code), or a "
                         "freezing index and soil class.")
        elif not heaving:
            status = "Non-frost-susceptible soil - depth governed by bearing, not frost"
            adequate = True
        elif base_depth_m + 1e-9 >= design_frost:
            status = "Footing below the frost line"
            adequate = True
        else:
            status = ("FOOTING ABOVE FROST LINE ({:.2f} < {:.2f} ft) - extend below the "
                      "frost depth or mitigate".format(self._l(base_depth_m), self._l(design_frost)))

        if groundwater:
            notes.append("Groundwater increases frost heave - account for it.")
        if not geotech_confirmed:
            adequate = False
            notes.append("Geotechnical data not confirmed (geotech_confirmed=false).")
        notes.append("This tool does not certify the foundation. Decide per IBC 1809 / "
                     "the local frost line with the geotechnical report.")
        return FoundationCheck(base_depth_m, design_frost, status, adequate, tuple(notes))

    def foundation_check_report(self, check, heaving, groundwater, geotech_confirmed):
        def yes_no(flag):
            return "yes" if flag else "no"

        lines = [
            "Foundation frost-depth check",
            "Footing depth: {:.2f} ft".format(self._l(check.base_depth_m)),
            "Design frost line: {}".format(
                "not set" if check.frost_depth_m is None
                else "{:.2f} ft".format(self._l(check.frost_depth_m))),
            "Result: {}".format(check.status),
            "",
            "Inputs:",
            " - Frost-susceptible soil: {}".format(yes_no(heaving)),
            " - Groundwater: {}".format(yes_no(groundwater)),
            " - Geotech confirmed: {}".format(yes_no(geotech_confirmed)),
            "",
            "Notes:",
        ]
        lines.extend(" - {}".format(note) for note in check.notes)
        return "\n".join(lines)

    def foundation_drain_report(self, offset_m, depth_below_m, length_m, invert_m):
        return "\n".join([
            "Foundation perimeter (footing) drain",
            "Offset from wall: {:.2f} ft".format(self._l(offset_m)),
            "Depth below footing/reference: {:.2f} ft".format(self._l(depth_below_m)),
            "Drain invert elevation: {:.2f} ft".format(self._l(invert_m)),
            "Drain length: {:.1f} ft".format(self._l(length_m)),
            "Slope the drain to outfall at >= 0.5% (IRC R405).",
        ])

    # -- earthwork accounting ----------------------------------------------
    _bulking = {
        1: (1.15, 1.03), 2: (1.12, 1.03), 3: (1.18, 1.05),
        4: (1.25, 1.08), 5: (1.30, 1.10), 6: (1.20, 1.05),
    }

    def soil_balance_report(self, balance, soil_class, initial_bulking, residual_bulking):
        lines = [
            "Earthwork soil balance",
            "Soil: {} (class {})".format(
                self.soil_name(soil_class), "-" if not soil_class else soil_class),
            "Swell {:.2f}; shrinkage {:.2f}".format(initial_bulking, residual_bulking),
            "Cut (bank): {:.1f} CY".format(self._v(balance.cut_bank_m3)),
            "Fill (compacted): {:.1f} CY".format(self._v(balance.fill_compacted_m3)),
            "Bank needed for fill: {:.1f} CY".format(self._v(balance.bank_for_fill_m3)),
        ]
        if balance.export_bank_m3 > 1e-9:
            lines.append("Export: {:.1f} CY bank ({:.1f} CY loose)".format(
                self._v(balance.export_bank_m3), self._v(balance.export_loose_m3)))
        elif balance.import_bank_m3 > 1e-9:
            lines.append("Import: {:.1f} CY bank ({:.1f} CY loose)".format(
                self._v(balance.import_bank_m3), self._v(balance.import_loose_m3)))
        else:
            lines.append("Balanced (no import/export).")
        lines.append("Haul (loose): {:.1f} CY".format(self._v(balance.cut_loose_m3)))
        return "\n".join(lines)

    _bill_labels = {
        "topsoil": "Strip topsoil",
        "cut": "Excavation (cut)",
        "fill": "Embankment (fill)",
        "backfill": "Backfill",
        "ditch": "Ditch / swale excavation",
    }

    def bill_of_quantities_table(self, items):
        header = ("Work item", "Volume, CY")
        rows = [(item.name, _format_m3(self._v(item.volume_m3))) for item in items]
        total = sum(item.volume_m3 for item in items)
        rows.append(("Total", _format_m3(self._v(total))))
        return QuantityTable(header=header, rows=tuple(rows))

    # -- temporary slope (OSHA Type A/B/C) ---------------------------------
    _soils = {
        1: "OSHA Type A (cohesive, stable)",
        2: "OSHA Type B (medium)",
        3: "OSHA Type C (granular / unstable)",
        4: "Type C (conservative)",
        5: "Type C (conservative)",
        6: "Type C (conservative)",
    }
    # Max allowable slope H:V for excavations up to 20 ft (~6.10 m),
    # OSHA 1926 Subpart P, Appendix B: A 3/4:1, B 1:1, C 1-1/2:1.
    _temp_slope_table = {
        1: ((6.10, 0.75),),
        2: ((6.10, 1.0),),
        3: ((6.10, 1.5),),
        4: ((6.10, 1.5),),
        5: ((6.10, 1.5),),
        6: ((6.10, 1.5),),
    }

    def soil_name(self, soil_class):
        return self._soils.get(soil_class, "unspecified") if soil_class else "unspecified"

    def assess_temporary_slope(self, proposed_1_to, depth_m, soil_class=None,
                               allowable_override_1_to=None, groundwater=False,
                               surcharge=False, geotech_confirmed=False):
        proposed_1_to = float(proposed_1_to)
        depth_m = float(depth_m)
        soil_class = None if soil_class is None else int(soil_class)
        indicative = (
            None if soil_class is None
            else self.indicative_allowable_slope(soil_class, depth_m)
        )
        governing = (
            float(allowable_override_1_to)
            if allowable_override_1_to is not None
            else indicative
        )

        notes = []
        review_required = False
        if depth_m > 6.096:
            review_required = True
            notes.append("Excavation over 20 ft - tabulated slopes do not apply; a "
                         "registered PE must design the protective system (OSHA 1926.652).")
        if groundwater:
            review_required = True
            notes.append("Groundwater at the excavation - dewatering and analysis "
                         "required; tabulated slopes do not apply.")
        if surcharge:
            review_required = True
            notes.append("Surcharge near the edge - account for the load and analyze.")
        if governing is None:
            review_required = True
            notes.append("Allowable slope undefined: set soil_class (OSHA Type) or "
                         "allowable_slope_1_to from the geotechnical report.")

        within_allowable = False
        if review_required:
            status = "REVIEW REQUIRED (engineering / soils)"
        elif proposed_1_to + 1e-9 >= governing:
            status = "Within allowable (confirm with soils)"
            within_allowable = True
        else:
            status = "TOO STEEP - flatter than allowable {:.2f}H:1V".format(governing)

        if not geotech_confirmed:
            within_allowable = False
            notes.append("Geotechnical data not confirmed (geotech_confirmed=false).")

        notes.append("This tool does not certify the slope. Decide per OSHA 29 CFR 1926 "
                     "Subpart P with soils and design.")

        return SlopeCheck(
            soil_class=soil_class,
            soil_name=self.soil_name(soil_class),
            depth_m=depth_m,
            proposed_1_to=proposed_1_to,
            indicative_allowable_1_to=indicative,
            governing_allowable_1_to=governing,
            status=status,
            within_allowable=within_allowable,
            notes=tuple(notes),
        )

    def slope_check_report(self, check, groundwater, surcharge, geotech_confirmed):
        def yes_no(flag):
            return "yes" if flag else "no"

        def fmt_slope(value):
            return "undefined" if value is None else "{:.2f}H:1V".format(value)

        lines = [
            "Temporary excavation slope check",
            "Soil: {} (class {})".format(
                check.soil_name, "-" if check.soil_class is None else check.soil_class),
            "Excavation depth: {:.2f} ft".format(self._l(check.depth_m)),
            "Proposed slope: {:.2f}H:1V".format(check.proposed_1_to),
            "Indicative allowable (table): {}".format(fmt_slope(check.indicative_allowable_1_to)),
            "Governing allowable: {}".format(fmt_slope(check.governing_allowable_1_to)),
            "Result: {}".format(check.status),
            "",
            "Input checklist:",
            " - Groundwater at excavation: {}".format(yes_no(groundwater)),
            " - Surcharge near edge: {}".format(yes_no(surcharge)),
            " - Geotech confirmed: {}".format(yes_no(geotech_confirmed)),
            "",
            "Notes:",
        ]
        lines.extend(" - {}".format(note) for note in check.notes)
        return "\n".join(lines)


RU = RussianStandard()
INT = GenericStandard()
US = USStandard()
STANDARDS = {RU.code: RU, INT.code: INT, US.code: US}
DEFAULT = RU
_ACTIVE_CODE = None  # process fallback when scriptcontext.sticky is unavailable


def available_standards():
    """Return ``(code, name)`` for every registered standard."""

    return tuple((standard.code, standard.name) for standard in STANDARDS.values())


def set_active_standard(code):
    """Set the active standard (persists across components via scriptcontext)."""

    global _ACTIVE_CODE
    _ACTIVE_CODE = str(code).upper() if code else None
    try:
        import scriptcontext

        if _ACTIVE_CODE:
            scriptcontext.sticky["earthwork_standard"] = _ACTIVE_CODE
        else:
            scriptcontext.sticky.pop("earthwork_standard", None)
    except Exception:
        pass
    return get_standard()


def _active_code():
    try:
        import scriptcontext

        code = scriptcontext.sticky.get("earthwork_standard")
        if code:
            return code
    except Exception:
        pass
    return _ACTIVE_CODE


def get_standard(code=None):
    """Return the chosen standard, the active one (sticky), or the default.

    Components call this with no argument; whatever the selector set (persisted in
    scriptcontext.sticky) is honoured, so the country is chosen in one place.
    """

    chosen = code or _active_code()
    if chosen:
        return STANDARDS.get(str(chosen).upper(), DEFAULT)
    return DEFAULT
