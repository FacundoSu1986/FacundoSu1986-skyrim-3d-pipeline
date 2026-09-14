import unittest

from skyrim_3d_pipeline import (
    AssetReport,
    AssetType,
    PipelinePhase,
    SkyrimEdition,
    build_plan,
)


class AssetReportTests(unittest.TestCase):
    def test_rejects_negative_triangle_count(self) -> None:
        with self.assertRaises(ValueError):
            AssetReport(
                source_format="glb",
                asset_type=AssetType.STATIC,
                vertices=100,
                triangles=-1,
                dimensions=(1.0, 2.0, 3.0),
                material_count=1,
                has_uv=True,
                has_normal_map=True,
                has_metallic_map=True,
                has_roughness_map=True,
            )


class PlanningTests(unittest.TestCase):
    def test_static_se_ae_is_the_non_experimental_mvp(self) -> None:
        plan = build_plan()

        self.assertEqual(plan.asset_type, AssetType.STATIC)
        self.assertEqual(plan.edition, SkyrimEdition.SE_AE)
        self.assertFalse(plan.experimental)
        self.assertEqual(plan.phases[0], PipelinePhase.INSPECT)
        self.assertEqual(plan.phases[-1], PipelinePhase.IN_GAME_TEST)

    def test_weapon_is_explicitly_experimental(self) -> None:
        plan = build_plan(asset_type=AssetType.WEAPON)

        self.assertTrue(plan.experimental)
        self.assertTrue(any("outside the static-prop MVP" in note for note in plan.notes))

    def test_le_is_verification_gated(self) -> None:
        plan = build_plan(edition=SkyrimEdition.LE)

        self.assertTrue(any("LE-specific" in note for note in plan.notes))


if __name__ == "__main__":
    unittest.main()
