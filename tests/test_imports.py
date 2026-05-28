import subprocess
import sys
import unittest


class ImportSurfaceTest(unittest.TestCase):
    def test_public_symbols_importable(self):
        # The whole curated surface imports from the top-level package.
        from gradeit import (  # noqa: F401
            BridgeFilter,
            Coordinate,
            ElevationFilter,
            ElevationModel,
            GradeitError,
            GradeResult,
            SavitzkyGolayFilter,
            USGSApi,
            USGSLocal,
            gradeit,
        )

    def test_import_does_not_pull_pandas_or_requests(self):
        # `import gradeit` must not eagerly import heavy deps. pandas is optional
        # (so the "pandas is optional" promise must not be hollow); requests is a
        # core dependency but is still imported lazily inside USGSApi so a plain
        # `import gradeit` stays cheap. Check in a fresh interpreter so the test
        # runner's own imports don't pollute sys.modules.
        code = (
            "import sys; import gradeit; "
            "assert 'pandas' not in sys.modules, 'pandas imported eagerly'; "
            "assert 'requests' not in sys.modules, 'requests imported eagerly'"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
