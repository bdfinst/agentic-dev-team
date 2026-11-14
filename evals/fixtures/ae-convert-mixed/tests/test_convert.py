import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convert import c_to_f, f_to_c


class ConvertTest(unittest.TestCase):
    def test_boiling_point_in_fahrenheit(self):
        self.assertEqual(c_to_f(100), 212)

    def test_freezing_point_in_celsius(self):
        self.assertEqual(f_to_c(32), 0)


if __name__ == "__main__":
    unittest.main()
