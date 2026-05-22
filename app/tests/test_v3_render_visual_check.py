import unittest

from PIL import Image, ImageDraw

from app.backend.render_visual_check import check_rendered_image


class V3RenderVisualCheckTest(unittest.TestCase):
    def test_flags_formula_ink_touching_highlight_edge(self):
        image = Image.new("RGB", (220, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, 180, 78), fill=(255, 255, 0))
        draw.rectangle((30, 38, 45, 70), fill=(0, 0, 0))

        result = check_rendered_image(image, page_number=1)

        self.assertFalse(result["passed"])
        self.assertTrue(any("墨迹贴近左侧边界" in warning for warning in result["warnings"]))

    def test_passes_formula_with_safe_inner_margin(self):
        image = Image.new("RGB", (220, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, 180, 78), fill=(255, 255, 0))
        draw.rectangle((62, 42, 132, 60), fill=(0, 0, 200))

        result = check_rendered_image(image, page_number=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["warnings"], [])

    def test_merges_formula_ink_with_highlight_before_edge_check(self):
        image = Image.new("RGB", (240, 130), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 34, 210, 88), fill=(255, 255, 0))
        for x in range(72, 160, 22):
            draw.line((x, 42, x + 18, 80), fill=(0, 0, 200), width=5)
            draw.line((x + 18, 42, x, 80), fill=(0, 0, 200), width=5)
        draw.line((70, 64, 176, 64), fill=(0, 0, 200), width=3)

        result = check_rendered_image(image, page_number=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["warnings"], [])

    def test_passes_formula_close_to_highlight_edge_without_touching_border(self):
        image = Image.new("RGB", (220, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, 180, 78), fill=(255, 255, 0))
        draw.rectangle((34, 38, 48, 70), fill=(0, 0, 0))

        result = check_rendered_image(image, page_number=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["warnings"], [])

    def test_flags_dense_ink_collision(self):
        image = Image.new("RGB", (220, 160), "white")
        draw = ImageDraw.Draw(image)
        for offset in range(0, 56, 4):
            color = (0, 0, 0) if offset % 8 == 0 else (0, 0, 200)
            draw.rectangle((70 + offset, 70, 72 + offset, 125), fill=color)
            draw.rectangle((70, 70 + offset, 125, 72 + offset), fill=(180, 0, 0))

        result = check_rendered_image(image, page_number=1)

        self.assertFalse(result["passed"])
        self.assertIn("局部墨迹密度异常，疑似文字/公式叠压", result["warnings"])

    def test_formula_regions_ignore_highlighted_text_outside_formula(self):
        image = Image.new("RGB", (260, 160), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 20, 190, 52), fill=(255, 255, 0))
        draw.rectangle((10, 28, 38, 46), fill=(0, 0, 0))
        draw.rectangle((80, 90, 180, 126), fill=(255, 255, 0))
        draw.rectangle((112, 102, 148, 114), fill=(0, 0, 200))

        result = check_rendered_image(
            image,
            page_number=1,
            formula_regions=[{"x0": 80, "y0": 90, "x1": 180, "y1": 126}],
        )

        self.assertTrue(result["passed"])

    def test_formula_region_does_not_treat_antialias_halo_as_background(self):
        image = Image.new("RGB", (220, 80), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((46, 16, 66, 62), fill=(0, 0, 180))
        draw.rectangle((48, 18, 64, 60), fill=(230, 245, 255))

        result = check_rendered_image(
            image,
            page_number=1,
            formula_regions=[{"x0": 0, "y0": 0, "x1": 220, "y1": 80}],
        )

        self.assertTrue(result["passed"])

    def test_flags_single_color_formula_crowding_inside_region(self):
        image = Image.new("RGB", (260, 110), "white")
        draw = ImageDraw.Draw(image)
        for y in range(42, 54, 2):
            draw.line((20, y, 235, y), fill=(0, 0, 220), width=1)
        for x in range(24, 238, 18):
            draw.rectangle((x, 30, x + 14, 68), fill=(0, 0, 220))

        result = check_rendered_image(
            image,
            page_number=1,
            formula_regions=[{"x0": 0, "y0": 0, "x1": 260, "y1": 110}],
        )

        self.assertFalse(result["passed"])
        self.assertTrue(any("公式墨迹拥挤" in warning for warning in result["warnings"]))

    def test_passes_legitimate_fraction_bars_inside_formula_region(self):
        image = Image.new("RGB", (180, 90), "white")
        draw = ImageDraw.Draw(image)
        draw.line((32, 36, 152, 36), fill=(0, 0, 220), width=2)
        draw.line((32, 48, 152, 48), fill=(0, 0, 220), width=2)
        draw.rectangle((42, 24, 50, 62), fill=(0, 0, 220))
        draw.rectangle((94, 24, 102, 62), fill=(0, 0, 220))

        result = check_rendered_image(
            image,
            page_number=1,
            formula_regions=[{"x0": 0, "y0": 0, "x1": 180, "y1": 90}],
        )

        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
