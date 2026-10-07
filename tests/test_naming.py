import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "EasyMatID"))
from easy_mat_id import naming  # noqa: E402


class NamingTest(unittest.TestCase):
    def test_mesh_prefix_replaced(self):
        self.assertEqual(naming.material_name("SM_Factory_Pipe_A", "Red"), "MT_Factory_Pipe_A_Red")
        self.assertEqual(naming.material_name("RM_Laboratory_Wall", "Blue"), "MT_Laboratory_Wall_Blue")
        self.assertEqual(naming.material_name("sk_Spider", "Red"), "MT_Spider_Red")

    def test_no_prefix_and_junk(self):
        self.assertEqual(naming.material_name("Box001", "Red"), "MT_Box001_Red")
        self.assertEqual(naming.material_name("my pipe (1)", "Red"), "MT_my_pipe_1_Red")
        self.assertEqual(naming.material_name("SM_", "Red"), "MT_Mesh_Red")

    def test_names_pass_validation(self):
        for node in ("SM_Factory_Pipe_A", "Box001", "my pipe (1)", "SM_"):
            self.assertRegex(naming.material_name(node, "Red2"), naming.VALID_NAME)

    def test_next_color(self):
        self.assertEqual(naming.next_color([])[0], "Red")
        self.assertEqual(naming.next_color(["Red"])[0], "Yellow")
        self.assertEqual(naming.next_color(["Yellow"])[0], "Red")
        all_first = [c for c, _ in naming.COLORS]
        self.assertEqual(naming.next_color(all_first)[0], "Red2")

    def test_color_of(self):
        self.assertEqual(naming.color_of("MT_Factory_Pipe_A_Red"), "Red")


if __name__ == "__main__":
    unittest.main()
